"""
Tests de regresión para el bug del clamping + void que infla stock fantasma.

Bug encontrado en Marbrava 28/04/26 al hacer dry-run e2e:
- Leche en 0 ML, allow_negative_stock=True
- Vender Latte vainilla (necesita 200 ML) → venta OK, descuento real=0 (clampeado)
- StockMove se creaba con qty=200 (qty solicitada) en vez de qty=0 (qty real)
- Al voidear, el void usaba la qty del StockMove para restaurar → leche
  pasaba de 0 a 200 ML "fantasmas" que nunca existieron físicamente.

Fix: el StockMove ahora registra `actual_decrement` (qty real descontada)
y se omite si actual_decrement=0. El void restaura exactamente lo descontado.
"""
import pytest
from decimal import Decimal

from catalog.models import Product, Recipe, RecipeLine, Unit
from inventory.models import StockItem, StockMove
from sales.models import Sale


def _seed_basic(tenant, warehouse, name, unit_obj, on_hand, allow_neg=False, cost="0"):
    p = Product.objects.create(
        tenant=tenant, name=name, sku=name.replace(" ", "_"),
        price=Decimal("1000"), cost=Decimal(cost),
        unit_obj=unit_obj, allow_negative_stock=allow_neg,
    )
    StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=p,
        on_hand=Decimal(str(on_hand)),
        avg_cost=Decimal(str(cost)),
        stock_value=(Decimal(str(on_hand)) * Decimal(str(cost))).quantize(Decimal("0.001")),
    )
    return p


@pytest.mark.django_db
class TestClampedSaleStockMove:
    """El StockMove generado por una venta clampeada debe reflejar la qty
    REAL descontada, no la qty solicitada."""

    def test_clamped_to_zero_creates_no_stockmove(
        self, api_client, tenant, warehouse,
    ):
        """Stock=0 + allow_negative=True + venta de qty=10 → descuento real=0
        → NO se debe crear StockMove (no hubo movimiento físico)."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Producto X", un, on_hand="0",
                        allow_neg=True, cost="100")

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "10", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 10000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        # Stock sigue en 0 (no había nada que descontar)
        si = StockItem.objects.get(product=p, warehouse=warehouse)
        assert si.on_hand == Decimal("0.000")

        # NO debe existir StockMove para esta venta porque actual_decrement=0
        moves = StockMove.objects.filter(ref_type="SALE", ref_id=sale_id, product=p)
        assert not moves.exists(), \
            "No debe crearse StockMove con qty=0 (sin movimiento físico)"

    def test_clamped_partial_creates_stockmove_with_actual_qty(
        self, api_client, tenant, warehouse,
    ):
        """Stock=3 + allow_negative=True + venta de qty=10 → descuento real=3
        → StockMove debe tener qty=3 (no qty=10)."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Producto Y", un, on_hand="3",
                        allow_neg=True, cost="100")

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "10", "unit_price": "500"}],
            "payments": [{"method": "cash", "amount": 5000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        si = StockItem.objects.get(product=p, warehouse=warehouse)
        assert si.on_hand == Decimal("0.000")  # clampeado a 0

        moves = list(StockMove.objects.filter(ref_type="SALE", ref_id=sale_id, product=p))
        assert len(moves) == 1
        assert moves[0].qty == Decimal("3.000"), \
            f"StockMove debe registrar qty REAL descontada (3), no solicitada (10). Got {moves[0].qty}"

    def test_no_clamping_keeps_normal_qty(
        self, api_client, tenant, warehouse,
    ):
        """Stock=100 + venta de qty=5 → sin clamping → StockMove qty=5 (igual que antes)."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Producto Z", un, on_hand="100", cost="50")

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "5", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 5000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201
        sale_id = r.data["id"]

        moves = list(StockMove.objects.filter(ref_type="SALE", ref_id=sale_id, product=p))
        assert len(moves) == 1
        assert moves[0].qty == Decimal("5.000")
        assert StockItem.objects.get(product=p, warehouse=warehouse).on_hand == Decimal("95.000")


@pytest.mark.django_db
class TestVoidDoesNotInflatePhantomStock:
    """El void de una venta clampeada NO debe restaurar más stock del que
    se descontó realmente. Antes del fix: leche pasaba de 0 → void → 200 ML
    fantasmas."""

    def test_void_after_full_clamp_keeps_stock_at_zero(
        self, api_client, tenant, warehouse, owner,
    ):
        """Stock=0 + venta clampeada (descuento real=0) → void → stock sigue en 0."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Pan", un, on_hand="0",
                        allow_neg=True, cost="200")

        # Vender 5 unidades
        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "5", "unit_price": "500"}],
            "payments": [{"method": "cash", "amount": 2500}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201
        sale_id = r.data["id"]

        # Stock sigue en 0
        assert StockItem.objects.get(product=p, warehouse=warehouse).on_hand == Decimal("0.000")

        # Void
        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200, rv.data

        # Stock DEBE seguir en 0 (no inflarse a 5)
        si = StockItem.objects.get(product=p, warehouse=warehouse)
        assert si.on_hand == Decimal("0.000"), \
            f"BUG: void infló stock fantasma. Esperado 0, obtuvo {si.on_hand}"

    def test_void_after_partial_clamp_restores_only_actual_decrement(
        self, api_client, tenant, warehouse, owner,
    ):
        """Stock=3 + venta de 10 (descuento real=3) → void → stock vuelve a 3."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Café paq", un, on_hand="3",
                        allow_neg=True, cost="100")

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "10", "unit_price": "500"}],
            "payments": [{"method": "cash", "amount": 5000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201
        sale_id = r.data["id"]
        assert StockItem.objects.get(product=p, warehouse=warehouse).on_hand == Decimal("0.000")

        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200

        # Stock vuelve a 3 (NO a 10 que era lo solicitado)
        si = StockItem.objects.get(product=p, warehouse=warehouse)
        assert si.on_hand == Decimal("3.000"), \
            f"Esperado 3 (qty real descontada), obtuvo {si.on_hand}"

    def test_void_normal_sale_still_works(
        self, api_client, tenant, warehouse, owner,
    ):
        """Sin clamping: void debe restaurar exactamente lo descontado (igual que antes)."""
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))
        p = _seed_basic(tenant, warehouse, "Galleta", un, on_hand="50", cost="100")

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "5", "unit_price": "500"}],
            "payments": [{"method": "cash", "amount": 2500}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        sale_id = r.data["id"]
        assert StockItem.objects.get(product=p, warehouse=warehouse).on_hand == Decimal("45.000")

        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200
        assert StockItem.objects.get(product=p, warehouse=warehouse).on_hand == Decimal("50.000")


@pytest.mark.django_db
class TestRecipeWithMixedClamping:
    """Caso real Marbrava: vendo Latte vainilla. Leche está en 0 (clampeada),
    café y syrup tienen stock suficiente. El void debe restaurar SOLO café
    y syrup, no inflar leche."""

    def test_recipe_partial_clamp_void_restores_correctly(
        self, api_client, tenant, warehouse, owner,
    ):
        ml = Unit.objects.create(tenant=tenant, code="ML", name="ml",
                                  family="VOLUME", is_base=True, conversion_factor=Decimal("1"))
        gr = Unit.objects.create(tenant=tenant, code="GR", name="gr",
                                  family="MASS", is_base=True, conversion_factor=Decimal("1"))
        un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad",
                                  family="COUNT", is_base=True, conversion_factor=Decimal("1"))

        # Leche: 0 ML, allow_neg=True (caso clamp)
        leche = _seed_basic(tenant, warehouse, "Leche", ml, on_hand="0",
                             allow_neg=True, cost="1.2")
        # Café: 100 GR, sin clamp
        cafe = _seed_basic(tenant, warehouse, "Cafe", gr, on_hand="100",
                            allow_neg=True, cost="30")
        # Syrup: 50 ML, sin clamp
        syrup = _seed_basic(tenant, warehouse, "Syrup", ml, on_hand="50",
                             allow_neg=True, cost="5")

        # Latte (intermedio): receta = 200 ML leche + 8 GR café
        latte = _seed_basic(tenant, warehouse, "Latte", un, on_hand="0", allow_neg=True)
        latte_recipe = Recipe.objects.create(tenant=tenant, product=latte, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=latte_recipe, ingredient=leche, qty=Decimal("200"), unit=ml)
        RecipeLine.objects.create(tenant=tenant, recipe=latte_recipe, ingredient=cafe, qty=Decimal("8"), unit=gr)

        # Latte vainilla: 1 UN Latte + 15 ML syrup
        latte_v = _seed_basic(tenant, warehouse, "Latte Van", un, on_hand="0", allow_neg=True)
        lv_recipe = Recipe.objects.create(tenant=tenant, product=latte_v, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=lv_recipe, ingredient=latte, qty=Decimal("1"), unit=un)
        RecipeLine.objects.create(tenant=tenant, recipe=lv_recipe, ingredient=syrup, qty=Decimal("15"), unit=ml)

        # Vender 1 Latte vainilla
        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": latte_v.id, "qty": "1", "unit_price": "4500"}],
            "payments": [{"method": "cash", "amount": 4500}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        # Stock después de la venta
        assert StockItem.objects.get(product=leche, warehouse=warehouse).on_hand == Decimal("0.000")  # clampeado
        assert StockItem.objects.get(product=cafe, warehouse=warehouse).on_hand == Decimal("92.000")  # 100-8
        assert StockItem.objects.get(product=syrup, warehouse=warehouse).on_hand == Decimal("35.000")  # 50-15

        # Void
        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200, rv.data

        # Después del void:
        # - Leche: NO debe inflarse (sigue en 0)
        # - Café y syrup: vuelven a su valor original
        assert StockItem.objects.get(product=leche, warehouse=warehouse).on_hand == Decimal("0.000"), \
            "BUG: leche se infló en void aunque la venta había clampeado"
        assert StockItem.objects.get(product=cafe, warehouse=warehouse).on_hand == Decimal("100.000")
        assert StockItem.objects.get(product=syrup, warehouse=warehouse).on_hand == Decimal("50.000")
