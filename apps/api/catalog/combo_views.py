"""
catalog/combo_views.py — Combos / packs (Mario 28/05/26).

Un combo es un PRODUCTO cuya "receta" son otros productos vendibles a un
precio fijo de pack (ej: "Combo Capu + Brownie" = 1 Capuccino amaretto +
1 Brownie = $5.600). Se modela reutilizando la infraestructura de recetas:
el Product combo tiene precio fijo, y su Recipe lista los componentes. Al
vender el combo, la expansión de recetas (sales/recipes.py) descuenta el
stock de cada componente y calcula el costo/margen. El combo aparece en el
buscador de mesas y POS como cualquier producto (porque ES un producto).

Endpoints:
  GET    /api/catalog/combos/        → lista combos con componentes + ahorro
  POST   /api/catalog/combos/        → crear combo (producto + receta) atómico
  PATCH  /api/catalog/combos/<pk>/   → editar combo
  DELETE /api/catalog/combos/<pk>/   → borrar combo (soft delete del producto)
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.permissions import HasTenant, IsManagerOrReadOnly
from .models import Product, Category, Recipe, RecipeLine


def _tid(request):
    return request.user.tenant_id


def _combo_data(product, lines):
    """Serializa un combo: producto + componentes + precio normal/ahorro."""
    components = []
    normal_total = Decimal("0")
    for l in lines:
        ing = l.ingredient
        qty = l.qty
        line_normal = (ing.price or Decimal("0")) * qty
        normal_total += line_normal
        components.append({
            "product_id": ing.id,
            "name": ing.name,
            "qty": str(qty),
            "unit_price": str(ing.price or Decimal("0")),
        })
    combo_price = product.price or Decimal("0")
    normal_total = normal_total.quantize(Decimal("0.01"))
    savings = (normal_total - combo_price).quantize(Decimal("0.01"))
    return {
        "id": product.id,
        "name": product.name,
        "price": str(combo_price),
        "category_id": product.category_id,
        "is_active": product.is_active,
        "components": components,
        # Referencia para el cajero: cuánto costaría suelto y cuánto ahorra.
        "normal_price": str(normal_total),
        "savings": str(savings if savings > 0 else Decimal("0.00")),
    }


def _parse_components(raw, t_id, exclude_product_id=None):
    """Valida y normaliza la lista de componentes. Devuelve
    (components_list, error_response). components_list = [(Product, qty)]."""
    if not isinstance(raw, list) or len(raw) == 0:
        return None, Response({"detail": "El combo necesita al menos un producto."}, status=400)

    parsed = []
    total_units = Decimal("0")
    seen_ids = set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            return None, Response({"detail": f"Componente #{i+1} inválido."}, status=400)
        pid = c.get("product_id")
        try:
            qty = Decimal(str(c.get("qty") or 1))
        except (InvalidOperation, ValueError, TypeError):
            return None, Response({"detail": f"Componente #{i+1}: cantidad inválida."}, status=400)
        if qty <= 0:
            return None, Response({"detail": f"Componente #{i+1}: la cantidad debe ser mayor a 0."}, status=400)
        if pid in seen_ids:
            return None, Response({"detail": "Un producto está repetido en el combo. Súmalo en la cantidad."}, status=400)
        seen_ids.add(pid)
        total_units += qty
        parsed.append((pid, qty))

    # Un combo debe agrupar MÁS de 1 unidad (sino es un producto renombrado).
    if len(parsed) == 1 and total_units <= 1:
        return None, Response(
            {"detail": "Un combo debe agrupar 2 o más productos (o varias unidades de uno)."},
            status=400,
        )

    # Cargar productos del tenant, activos, no combos (un combo no puede
    # contener otro combo — evita anidamiento confuso y posibles ciclos).
    ids = [pid for pid, _ in parsed]
    products = {
        p.id: p for p in Product.objects.filter(tenant_id=t_id, id__in=ids, is_active=True)
    }
    missing = set(ids) - set(products.keys())
    if missing:
        return None, Response(
            {"detail": "Algunos productos no existen o están inactivos."},
            status=400,
        )
    if exclude_product_id and exclude_product_id in products:
        return None, Response(
            {"detail": "Un combo no puede incluirse a sí mismo."},
            status=400,
        )
    nested = [p.name for p in products.values() if p.is_combo]
    if nested:
        return None, Response(
            {"detail": f"Un combo no puede contener otros combos: {', '.join(nested)}."},
            status=400,
        )

    return [(products[pid], qty) for pid, qty in parsed], None


def _parse_price(raw):
    try:
        price = Decimal(str(raw if raw is not None else 0))
    except (InvalidOperation, ValueError, TypeError):
        return None, Response({"detail": "Precio inválido."}, status=400)
    if price < 0:
        return None, Response({"detail": "El precio no puede ser negativo."}, status=400)
    return price, None


class ComboListCreate(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsManagerOrReadOnly]

    def get(self, request):
        t_id = _tid(request)
        combos = (
            Product.objects.filter(tenant_id=t_id, is_combo=True)
            .select_related("category")
            .order_by("name")
        )
        # Prefetch recipe lines por combo
        recipes = {
            r.product_id: list(r.lines.select_related("ingredient").all())
            for r in Recipe.objects.filter(tenant_id=t_id, product__in=combos)
            .prefetch_related("lines__ingredient")
        }
        data = [_combo_data(p, recipes.get(p.id, [])) for p in combos]
        return Response(data)

    @transaction.atomic
    def post(self, request):
        t_id = _tid(request)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "El nombre es obligatorio."}, status=400)

        price, err = _parse_price(request.data.get("price"))
        if err:
            return err

        components, err = _parse_components(request.data.get("components"), t_id)
        if err:
            return err

        category_id = request.data.get("category_id")
        if category_id is not None:
            if not Category.objects.filter(tenant_id=t_id, id=category_id).exists():
                return Response({"detail": "Categoría no válida."}, status=400)

        # Crear el producto-combo
        combo = Product.objects.create(
            tenant_id=t_id,
            name=name,
            price=price,
            category_id=category_id,
            is_combo=True,
            is_active=True,
            cost=Decimal("0"),  # el costo real se calcula desde la receta al vender
        )
        # Crear la receta con los componentes (unit=None → usa unidad del
        # ingrediente; para productos terminados es UN).
        recipe = Recipe.objects.create(tenant_id=t_id, product=combo, is_active=True, notes="Combo")
        RecipeLine.objects.bulk_create([
            RecipeLine(tenant_id=t_id, recipe=recipe, ingredient=prod, qty=qty)
            for prod, qty in components
        ])

        lines = list(recipe.lines.select_related("ingredient").all())
        return Response(_combo_data(combo, lines), status=201)


class ComboDetail(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsManagerOrReadOnly]

    def _get(self, pk, t_id):
        try:
            return Product.objects.get(pk=pk, tenant_id=t_id, is_combo=True)
        except Product.DoesNotExist:
            return None

    def get(self, request, pk):
        t_id = _tid(request)
        combo = self._get(pk, t_id)
        if not combo:
            return Response({"detail": "Combo no encontrado."}, status=404)
        try:
            recipe = Recipe.objects.get(tenant_id=t_id, product=combo)
            lines = list(recipe.lines.select_related("ingredient").all())
        except Recipe.DoesNotExist:
            lines = []
        return Response(_combo_data(combo, lines))

    @transaction.atomic
    def patch(self, request, pk):
        t_id = _tid(request)
        combo = self._get(pk, t_id)
        if not combo:
            return Response({"detail": "Combo no encontrado."}, status=404)

        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if not name:
                return Response({"detail": "El nombre es obligatorio."}, status=400)
            combo.name = name

        if "price" in request.data:
            price, err = _parse_price(request.data.get("price"))
            if err:
                return err
            combo.price = price

        if "category_id" in request.data:
            category_id = request.data.get("category_id")
            if category_id is not None and not Category.objects.filter(tenant_id=t_id, id=category_id).exists():
                return Response({"detail": "Categoría no válida."}, status=400)
            combo.category_id = category_id

        if "is_active" in request.data:
            combo.is_active = bool(request.data.get("is_active"))

        combo.save()

        # Reemplazar componentes si vienen
        if "components" in request.data:
            components, err = _parse_components(
                request.data.get("components"), t_id, exclude_product_id=combo.id,
            )
            if err:
                return err
            recipe, _ = Recipe.objects.update_or_create(
                tenant_id=t_id, product=combo,
                defaults={"is_active": True, "notes": "Combo"},
            )
            RecipeLine.objects.filter(recipe=recipe).delete()
            RecipeLine.objects.bulk_create([
                RecipeLine(tenant_id=t_id, recipe=recipe, ingredient=prod, qty=qty)
                for prod, qty in components
            ])

        try:
            recipe = Recipe.objects.get(tenant_id=t_id, product=combo)
            lines = list(recipe.lines.select_related("ingredient").all())
        except Recipe.DoesNotExist:
            lines = []
        return Response(_combo_data(combo, lines))

    @transaction.atomic
    def delete(self, request, pk):
        t_id = _tid(request)
        combo = self._get(pk, t_id)
        if not combo:
            return Response({"detail": "Combo no encontrado."}, status=404)
        # Soft delete consistente con productos: marca deleted_at y desactiva.
        # La receta queda pero el producto desaparece del catálogo/mesas.
        combo.deleted_at = timezone.now()
        combo.is_active = False
        combo.save(update_fields=["deleted_at", "is_active"])
        return Response(status=204)
