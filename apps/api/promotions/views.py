import logging
from decimal import Decimal, InvalidOperation

from django.db.models import Count
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.http_cache import browser_cache
from core.permissions import HasTenant, IsManager

logger = logging.getLogger(__name__)

from catalog.models import Product
from .models import Promotion, PromotionProduct
from .serializers import (
    PromotionListSerializer,
    PromotionDetailSerializer,
    PromotionCreateSerializer,
)

PERMS = [IsAuthenticated, HasTenant, IsManager]


def tenant_id(request):
    return request.user.tenant_id


# ── List + Create ──────────────────────────────────────────────────────────

class PromotionListCreateView(APIView):
    permission_classes = PERMS

    PAGE_SIZE = 50

    def get(self, request):
        qs = Promotion.objects.filter(tenant_id=tenant_id(request)).annotate(
            product_count=Count("items"),
        ).order_by("-created_at")

        # Filtros opcionales
        active = request.query_params.get("active")
        if active == "true":
            now = timezone.now()
            qs = qs.filter(is_active=True, start_date__lte=now, end_date__gte=now)

        # Paginación
        total = qs.count()
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        start = (page - 1) * self.PAGE_SIZE
        page_qs = qs[start:start + self.PAGE_SIZE]

        data = PromotionListSerializer(page_qs, many=True).data
        return Response({"results": data, "total": total, "page": page, "page_size": self.PAGE_SIZE})

    def post(self, request):
        ser = PromotionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        product_items = d.pop("product_items", [])
        product_ids = d.pop("product_ids", [])

        # Build items list — product_items takes priority over product_ids
        items_to_create = []
        if product_items:
            for item in product_items:
                pid = int(item.get("product_id", 0))
                override = item.get("override_discount_value")
                if pid:
                    items_to_create.append({"product_id": pid, "override": override})
        elif product_ids:
            items_to_create = [{"product_id": pid, "override": None} for pid in product_ids]

        pids = [i["product_id"] for i in items_to_create]
        products = Product.objects.filter(
            tenant_id=tenant_id(request), id__in=pids, is_active=True,
        )
        if products.count() != len(set(pids)):
            return Response(
                {"detail": "Algunos productos no existen o no están activos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        promo = Promotion.objects.create(
            tenant_id=tenant_id(request),
            created_by=request.user,
            **d,
        )
        pp_objs = []
        for item in items_to_create:
            kwargs = {"promotion": promo, "product_id": item["product_id"]}
            if item["override"] is not None:
                try:
                    kwargs["override_discount_value"] = Decimal(str(item["override"]))
                except (InvalidOperation, ValueError, TypeError):
                    logger.warning("Override discount value inválido: %s", item["override"])
            pp_objs.append(PromotionProduct(**kwargs))
        PromotionProduct.objects.bulk_create(pp_objs)

        return Response(
            PromotionDetailSerializer(promo).data,
            status=status.HTTP_201_CREATED,
        )


# ── Detail / Update / Delete ──────────────────────────────────────────────

class PromotionDetailView(APIView):
    permission_classes = PERMS

    def _get(self, request, pk):
        try:
            return Promotion.objects.prefetch_related("items__product").get(
                pk=pk, tenant_id=tenant_id(request),
            )
        except Promotion.DoesNotExist:
            return None

    def get(self, request, pk):
        promo = self._get(request, pk)
        if not promo:
            return Response({"detail": "No encontrado."}, status=404)
        return Response(PromotionDetailSerializer(promo).data)

    def patch(self, request, pk):
        promo = self._get(request, pk)
        if not promo:
            return Response({"detail": "No encontrado."}, status=404)

        from decimal import Decimal, InvalidOperation
        from django.utils.dateparse import parse_datetime

        # Validar discount_type contra los choices del modelo.
        # ANTES: setattr blind aceptaba cualquier string (ej: "invalid")
        # y quedaba guardado en DB. Mario podía corromper datos editando
        # una promo con un discount_type inválido. Bug detectado en QA
        # 07/05/26.
        if "discount_type" in request.data:
            new_dt = request.data["discount_type"]
            valid_dts = {c[0] for c in Promotion.DISCOUNT_TYPE_CHOICES}
            if new_dt not in valid_dts:
                return Response(
                    {"detail": f"discount_type debe ser uno de: {sorted(valid_dts)}"},
                    status=400,
                )
            promo.discount_type = new_dt

        # name e is_active son strings/bool simples — setattr OK
        for field in ("name", "is_active"):
            if field in request.data:
                setattr(promo, field, request.data[field])

        # Validar discount_value:
        #   - Tiene que ser numérico válido
        #   - > 0
        #   - Si la promo es 'pct' (después del posible cambio arriba),
        #     no puede pasar de 100. ANTES dejaba grabar 150% silencioso.
        if "discount_value" in request.data:
            try:
                dv = Decimal(str(request.data["discount_value"]))
                if dv <= 0:
                    return Response({"detail": "discount_value debe ser mayor a 0."}, status=400)
                if promo.discount_type == "pct" and dv > 100:
                    return Response(
                        {"detail": "El porcentaje no puede ser mayor a 100."},
                        status=400,
                    )
                promo.discount_value = dv
            except (InvalidOperation, ValueError, TypeError):
                return Response({"detail": "discount_value inválido."}, status=400)

        # Fechas — parsear y validar que end > start usando los valores
        # FINALES (los nuevos si se mandaron, los viejos si no). ANTES
        # se podía dejar end_date < start_date editando un solo campo.
        if "start_date" in request.data:
            sd = parse_datetime(str(request.data["start_date"]))
            if not sd:
                return Response({"detail": "start_date con formato inválido."}, status=400)
            promo.start_date = sd
        if "end_date" in request.data:
            ed = parse_datetime(str(request.data["end_date"]))
            if not ed:
                return Response({"detail": "end_date con formato inválido."}, status=400)
            promo.end_date = ed
        if promo.end_date <= promo.start_date:
            return Response(
                {"detail": "La fecha de fin debe ser posterior a la de inicio."},
                status=400,
            )

        _update_fields = ["name", "discount_type", "is_active", "discount_value", "start_date", "end_date"]
        promo.save(update_fields=_update_fields)

        # Handle product updates — product_items (with overrides) or product_ids (simple)
        product_items = request.data.get("product_items")
        product_ids = request.data.get("product_ids")

        if product_items is not None:
            t_id = tenant_id(request)
            items_to_create = []
            for item in product_items:
                pid = int(item.get("product_id", 0))
                override = item.get("override_discount_value")
                if pid:
                    items_to_create.append({"product_id": pid, "override": override})
            pids = [i["product_id"] for i in items_to_create]
            valid = Product.objects.filter(tenant_id=t_id, id__in=pids, is_active=True)
            if valid.count() != len(set(pids)):
                return Response({"detail": "Algunos productos no existen o no están activos."}, status=400)
            promo.items.all().delete()
            pp_objs = []
            for item in items_to_create:
                kwargs = {"promotion": promo, "product_id": item["product_id"]}
                if item["override"] is not None:
                    try:
                        kwargs["override_discount_value"] = Decimal(str(item["override"]))
                    except (InvalidOperation, ValueError, TypeError):
                        logger.warning("Override discount value inválido en patch: %s", item["override"])
                pp_objs.append(PromotionProduct(**kwargs))
            PromotionProduct.objects.bulk_create(pp_objs)
        elif product_ids is not None:
            t_id = tenant_id(request)
            valid = Product.objects.filter(
                tenant_id=t_id, id__in=product_ids, is_active=True,
            )
            if valid.count() != len(product_ids):
                return Response(
                    {"detail": "Algunos productos no existen o no están activos."},
                    status=400,
                )
            promo.items.all().delete()
            PromotionProduct.objects.bulk_create([
                PromotionProduct(promotion=promo, product_id=pid)
                for pid in product_ids
            ])

        return Response(PromotionDetailSerializer(promo).data)

    def delete(self, request, pk):
        promo = self._get(request, pk)
        if not promo:
            return Response({"detail": "No encontrado."}, status=404)
        # Soft delete — desactivar en vez de borrar
        promo.is_active = False
        promo.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Active promotions for POS ─────────────────────────────────────────────

class ActivePromotionsForProductsView(APIView):
    """GET /api/promotions/active-for-products/?product_ids=1,2,3

    Cache: 60s privado. Las promociones cambian poco (Mario las crea/edita
    desde admin, no en caliente). Mejora notoria en panel POS / mesas que
    consultan este endpoint en cada apertura.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    @browser_cache(max_age=60)
    def get(self, request):
        raw = request.query_params.get("product_ids", "")
        try:
            product_ids = [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            return Response({"detail": "product_ids inválidos."}, status=400)

        if not product_ids:
            return Response({"results": []})

        now = timezone.now()
        pp_qs = PromotionProduct.objects.filter(
            product_id__in=product_ids,
            promotion__tenant_id=tenant_id(request),
            promotion__is_active=True,
            promotion__start_date__lte=now,
            promotion__end_date__gte=now,
        ).select_related("promotion", "product")

        # Agrupar por producto, tomar la mejor promo (menor precio)
        best = {}
        for pp in pp_qs:
            promo = pp.promotion
            promo_price = promo.compute_promo_price(pp.product.price, pp.override_discount_value)
            pid = pp.product_id
            if pid not in best or promo_price < best[pid]["promo_price"]:
                best[pid] = {
                    "product_id": pid,
                    "promotion_id": promo.id,
                    "promotion_name": promo.name,
                    "discount_type": promo.discount_type,
                    "discount_value": str(promo.discount_value),
                    "original_price": str(pp.product.price),
                    "promo_price": str(promo_price),
                }

        return Response({"results": list(best.values())})


# ── Conflict detection ───────────────────────────────────────────────────

class PromotionConflictCheckView(APIView):
    """POST /api/promotions/check-conflicts/
    Body: { product_ids, start_date, end_date, exclude_promotion_id? }
    Returns conflicting promotions for the given products and date range.
    """
    permission_classes = PERMS

    def post(self, request):
        product_ids = request.data.get("product_ids", [])
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        exclude_id = request.data.get("exclude_promotion_id")

        if not product_ids or not start_date or not end_date:
            return Response({"conflicts": []})

        from django.utils.dateparse import parse_datetime
        sd = parse_datetime(str(start_date))
        ed = parse_datetime(str(end_date))
        if not sd or not ed:
            return Response({"conflicts": []})

        t_id = tenant_id(request)

        # Find overlapping active promotions
        pp_qs = PromotionProduct.objects.filter(
            product_id__in=product_ids,
            promotion__tenant_id=t_id,
            promotion__is_active=True,
            promotion__start_date__lt=ed,  # overlap condition
            promotion__end_date__gt=sd,
        ).select_related("promotion", "product")

        if exclude_id:
            pp_qs = pp_qs.exclude(promotion_id=int(exclude_id))

        conflicts = []
        seen = set()
        for pp in pp_qs:
            key = (pp.product_id, pp.promotion_id)
            if key in seen:
                continue
            seen.add(key)
            conflicts.append({
                "product_id": pp.product_id,
                "product_name": pp.product.name,
                "conflicting_promotion_id": pp.promotion_id,
                "conflicting_promotion_name": pp.promotion.name,
                "conflicting_start": pp.promotion.start_date.isoformat(),
                "conflicting_end": pp.promotion.end_date.isoformat(),
            })

        return Response({"conflicts": conflicts})
