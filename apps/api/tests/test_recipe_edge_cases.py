"""
Tests para edge cases de recetas anidadas detectados en auditoría posterior
al fix recursivo (PR #86):

- §4 ALTO: receta activa con 0 líneas → venta sin descontar nada (silent)
- §3 BAJO/MEDIO: receta intermedia INACTIVA en cadena → mensaje confuso
- §1 MEDIO: CSV import sin validación de ciclos → A→B + B→A pasan al DB
"""
import io
import pytest
from decimal import Decimal

from catalog.models import Product, Recipe, RecipeLine, Unit
from inventory.models import StockItem
from sales.recipes import expand_recipes
from sales.services import SaleValidationError


def _u(tenant, code, family="COUNT"):
    return Unit.objects.create(
        tenant=tenant, code=code, name=code,
        family=family, is_base=True, conversion_factor=Decimal("1"),
    )


def _p(tenant, name, unit_obj):
    return Product.objects.create(
        tenant=tenant, name=name, sku=name.replace(" ", "_").upper(),
        price=Decimal("1000"), unit_obj=unit_obj,
    )


def _stock(tenant, warehouse, product, qty="100"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(qty)), avg_cost=Decimal("1"),
        stock_value=Decimal(str(qty)),
    )


@pytest.mark.django_db
class TestEmptyActiveRecipe:
    """§4: si Recipe(is_active=True) existe pero sin RecipeLines, vender el
    producto antes pasaba sin descontar NADA (silent bug). Ahora debe dar
    error claro."""

    def test_sale_of_product_with_empty_active_recipe_raises(self, tenant, warehouse):
        un = _u(tenant, "UN")
        p = _p(tenant, "Cafe Empty", un)
        # Crear Recipe activo PERO sin lines
        Recipe.objects.create(tenant=tenant, product=p, is_active=True)

        agg = {p.id: {"qty": Decimal("1"), "unit_price": Decimal("100"),
                      "discount_type": "none", "discount_value": Decimal("0"),
                      "promotion_id": None}}
        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(agg, tenant.id)
        msg = str(exc.value.detail).lower()
        assert "no tiene ingredientes" in msg or "sin ingredientes" in msg, \
            f"Mensaje debería mencionar ingredientes faltantes: {msg}"
        assert "cafe empty" in str(exc.value.detail).lower(), \
            "Mensaje debería nombrar el producto problemático"

    def test_sale_skips_empty_recipe_via_api_returns_400(
        self, api_client, tenant, warehouse,
    ):
        """E2E: la venta vía /api/sales/sales/ debe devolver 400, NO 201
        con descuento silente."""
        un = _u(tenant, "UN")
        p = _p(tenant, "Producto Empty", un)
        _stock(tenant, warehouse, p, qty="50")
        Recipe.objects.create(tenant=tenant, product=p, is_active=True)

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "1", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 1000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 400, r.data
        assert "ingredientes" in str(r.data).lower()


@pytest.mark.django_db
class TestInactiveRecipeInChain:
    """§3: si A vende con receta activa, y A usa B como ingrediente, pero la
    receta de B está INACTIVA, antes la venta fallaba con shortage confuso.
    Ahora debe dar error claro indicando que la receta intermedia está inactiva."""

    def test_inactive_intermediate_recipe_raises_clear_error(self, tenant, warehouse):
        un = _u(tenant, "UN")
        ml = _u(tenant, "ML", family="VOLUME")
        leche = _p(tenant, "Leche", ml)
        b = _p(tenant, "B Intermedio", un)
        a = _p(tenant, "A Vendido", un)

        # Receta de B (200 ML leche) — INACTIVA
        rb = Recipe.objects.create(tenant=tenant, product=b, is_active=False)
        RecipeLine.objects.create(tenant=tenant, recipe=rb, ingredient=leche, qty=Decimal("200"), unit=ml)

        # Receta de A (1 UN B) — ACTIVA
        ra = Recipe.objects.create(tenant=tenant, product=a, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=ra, ingredient=b, qty=Decimal("1"), unit=un)

        agg = {a.id: {"qty": Decimal("1"), "unit_price": Decimal("100"),
                      "discount_type": "none", "discount_value": Decimal("0"),
                      "promotion_id": None}}
        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(agg, tenant.id)
        msg = str(exc.value.detail).lower()
        assert "desactivada" in msg or "inactiva" in msg, \
            f"Mensaje debería mencionar receta desactivada: {msg}"
        assert "b intermedio" in str(exc.value.detail).lower()
        assert "a vendido" in str(exc.value.detail).lower(), \
            "Mensaje debería nombrar al padre que la usa"

    def test_inactive_recipe_for_directly_sold_product_works_as_raw(
        self, tenant, warehouse,
    ):
        """Si el producto vendido DIRECTAMENTE tiene receta inactiva,
        debe tratarse como producto raw (sin expandir). NO debe lanzar
        error — el dueño desactivó la receta a propósito."""
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche directa", un)
        Recipe.objects.create(tenant=tenant, product=leche, is_active=False)

        agg = {leche.id: {"qty": Decimal("1"), "unit_price": Decimal("100"),
                          "discount_type": "none", "discount_value": Decimal("0"),
                          "promotion_id": None}}
        expanded, _ = expand_recipes(agg, tenant.id)
        # Se trata como raw → aparece en expanded_agg con su qty
        assert leche.id in expanded
        assert expanded[leche.id]["qty"] == Decimal("1")


@pytest.mark.django_db
class TestRecipeImportCycleDetection:
    """§1: el endpoint /api/catalog/recipes/import/ (CSV bulk) antes no
    chequeaba ciclos. Si el archivo trae A→B y B→A, todas las ventas
    posteriores estallan en runtime. Ahora el import los detecta y aborta."""

    def _make_csv(self, rows):
        """Construye un CSV en memoria con header y rows."""
        out = io.StringIO()
        out.write("product_sku,ingredient_sku,qty\n")
        for parent, ing, qty in rows:
            out.write(f"{parent},{ing},{qty}\n")
        return io.BytesIO(out.getvalue().encode("utf-8"))

    def test_csv_with_direct_cycle_aborts(
        self, api_client, tenant, warehouse,
    ):
        """A → B y B → A en el mismo CSV → import debe abortar con 400."""
        un = _u(tenant, "UN")
        a = _p(tenant, "A", un)
        b = _p(tenant, "B", un)

        csv = self._make_csv([
            ("A", "B", "1"),
            ("B", "A", "1"),
        ])
        r = api_client.post(
            "/api/catalog/recipes/import-csv/",
            {"file": csv},
            format="multipart",
        )
        assert r.status_code == 400, r.data
        # Debe nombrar el producto problemático y mencionar ciclo
        body = str(r.data).lower()
        assert "circular" in body or "ciclo" in body
        # Y NO debe haber creado nada
        assert not Recipe.objects.filter(tenant=tenant).exists()

    def test_csv_without_cycle_works(
        self, api_client, tenant, warehouse,
    ):
        """Caso normal: CSV sin ciclos → import funciona."""
        un = _u(tenant, "UN")
        a = _p(tenant, "Avainilla", un)
        b = _p(tenant, "Base", un)
        leche = _p(tenant, "Lechecita", un)

        csv = self._make_csv([
            ("Avainilla", "Base", "1"),
            ("Base", "Lechecita", "200"),
        ])
        r = api_client.post(
            "/api/catalog/recipes/import-csv/",
            {"file": csv},
            format="multipart",
        )
        assert r.status_code == 200, r.data
        assert r.data["created"] == 2
        assert Recipe.objects.filter(tenant=tenant, product=a).exists()
        assert Recipe.objects.filter(tenant=tenant, product=b).exists()

    def test_csv_creates_cycle_with_existing_recipe(
        self, api_client, tenant, warehouse,
    ):
        """Receta A→B ya existe en DB. CSV trae B→A → ciclo creado en
        combinación → debe abortar."""
        un = _u(tenant, "UN")
        a = _p(tenant, "X", un)
        b = _p(tenant, "Y", un)

        # Receta existente: A → B
        ra = Recipe.objects.create(tenant=tenant, product=a, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=ra, ingredient=b, qty=Decimal("1"), unit=un)

        # CSV añade: B → A → ciclo
        csv = self._make_csv([("Y", "X", "1")])
        r = api_client.post(
            "/api/catalog/recipes/import-csv/",
            {"file": csv},
            format="multipart",
        )
        assert r.status_code == 400, r.data
        # No debe haber tocado la receta existente
        assert ra.lines.count() == 1
