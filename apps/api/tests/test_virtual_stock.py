"""
Tests para `catalog.virtual_stock.compute_virtual_stock_map` y su integración
en el reporte ABC.

Bug detectado en auditoría: productos compuestos (con receta activa) no
tienen StockItem propio, así que los reportes los mostraban con "Stock: 0",
engañoso porque sí se pueden vender mientras los ingredientes raw tengan
stock. Fix: cálculo recursivo de "max producible" basado en stock de
ingredientes raw.
"""
from decimal import Decimal

import pytest

from catalog.models import Product, Recipe, RecipeLine, Unit
from catalog.virtual_stock import compute_virtual_stock_map, is_virtual_product
from inventory.models import StockItem


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


def _stock(tenant, warehouse, product, qty):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(qty)), avg_cost=Decimal("1"),
        stock_value=Decimal(str(qty)),
    )


@pytest.mark.django_db
class TestComputeVirtualStockMap:
    """compute_virtual_stock_map devuelve dict pid → cantidad disponible."""

    def test_raw_product_returns_on_hand(self, tenant, store, warehouse):
        un = _u(tenant, "UN")
        p = _p(tenant, "Galleta", un)
        _stock(tenant, warehouse, p, qty="50")

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[p.id] == Decimal("50")

    def test_simple_recipe_max_producible(self, tenant, store, warehouse):
        """Cap = 200 ML leche; tengo 1000 ML → max producible = 5."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche", ml)
        cap = _p(tenant, "Cap", un)
        _stock(tenant, warehouse, leche, qty="1000")
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche,
                                   qty=Decimal("200"), unit=ml)

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[leche.id] == Decimal("1000")
        assert m[cap.id] == Decimal("5.000"), \
            f"Esperado 5 cap producibles (1000/200), obtuvo {m[cap.id]}"

    def test_recipe_min_of_ingredients(self, tenant, store, warehouse):
        """Cap = 200 ML leche + 8 GR café; leche da para 5, café para 12.5
        → min = 5."""
        ml = _u(tenant, "ML", family="VOLUME")
        gr = _u(tenant, "GR", family="MASS")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche", ml)
        cafe = _p(tenant, "Cafe", gr)
        cap = _p(tenant, "Cap", un)
        _stock(tenant, warehouse, leche, qty="1000")
        _stock(tenant, warehouse, cafe, qty="100")
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche, qty=Decimal("200"), unit=ml)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=cafe, qty=Decimal("8"), unit=gr)

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[cap.id] == Decimal("5.000"), \
            f"min(1000/200=5, 100/8=12.5) = 5, obtuvo {m[cap.id]}"

    def test_nested_recipe_recursive(self, tenant, store, warehouse):
        """Latte = 200 ML leche + 8 GR café; Latte vainilla = 1 UN Latte + 15 ML syrup.
        Stock: leche=1000 ML, café=100 GR, syrup=60 ML.
        Latte producible = min(1000/200, 100/8) = 5
        Latte vainilla producible = min(5/1, 60/15) = min(5, 4) = 4."""
        ml = _u(tenant, "ML", family="VOLUME")
        gr = _u(tenant, "GR", family="MASS")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche", ml)
        cafe = _p(tenant, "Cafe", gr)
        syrup = _p(tenant, "Syrup", ml)
        latte = _p(tenant, "Latte", un)
        latte_v = _p(tenant, "Latte Van", un)
        _stock(tenant, warehouse, leche, qty="1000")
        _stock(tenant, warehouse, cafe, qty="100")
        _stock(tenant, warehouse, syrup, qty="60")
        rl = Recipe.objects.create(tenant=tenant, product=latte, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rl, ingredient=leche, qty=Decimal("200"), unit=ml)
        RecipeLine.objects.create(tenant=tenant, recipe=rl, ingredient=cafe, qty=Decimal("8"), unit=gr)
        rlv = Recipe.objects.create(tenant=tenant, product=latte_v, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rlv, ingredient=latte, qty=Decimal("1"), unit=un)
        RecipeLine.objects.create(tenant=tenant, recipe=rlv, ingredient=syrup, qty=Decimal("15"), unit=ml)

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[latte.id] == Decimal("5.000")
        assert m[latte_v.id] == Decimal("4.000"), \
            f"min(5 Latte, 60/15=4 Syrup) = 4, obtuvo {m[latte_v.id]}"

    def test_zero_stock_in_one_ingredient_blocks_recipe(self, tenant, store, warehouse):
        """Si UN ingrediente está en 0, el producto compuesto queda en 0."""
        ml = _u(tenant, "ML", family="VOLUME")
        gr = _u(tenant, "GR", family="MASS")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche", ml)
        cafe = _p(tenant, "Cafe", gr)
        cap = _p(tenant, "Cap", un)
        _stock(tenant, warehouse, leche, qty="1000")
        _stock(tenant, warehouse, cafe, qty="0")  # ← sin café
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche, qty=Decimal("200"), unit=ml)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=cafe, qty=Decimal("8"), unit=gr)

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[cap.id] == Decimal("0.000"), \
            "Sin café (0 GR) no se puede armar ningún cappuccino"

    def test_warehouse_filter(self, tenant, store, warehouse, warehouse_b=None):
        """Si paso warehouse_id, solo cuento stock de ese warehouse."""
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bod 2")
        un = _u(tenant, "UN")
        leche = _p(tenant, "L", un)
        cap = _p(tenant, "C", un)
        _stock(tenant, warehouse, leche, qty="100")
        _stock(tenant, wh2, leche, qty="500")
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche, qty=Decimal("10"), unit=un)

        # Sin filtro de warehouse: suma ambos = 600 → 60 cap
        m_all = compute_virtual_stock_map(tenant.id, store.id)
        assert m_all[cap.id] == Decimal("60.000")
        # Con filtro warehouse: solo 100 → 10 cap
        m_one = compute_virtual_stock_map(tenant.id, store.id, warehouse_id=warehouse.id)
        assert m_one[cap.id] == Decimal("10.000")

    def test_unit_conversion_in_recipe(self, tenant, store, warehouse):
        """Receta dice 0.2 L de leche, stock está en ML → debe convertir."""
        ml = _u(tenant, "ML", family="VOLUME")
        l = Unit.objects.create(
            tenant=tenant, code="L", name="L",
            family="VOLUME", is_base=False, conversion_factor=Decimal("1000"),
        )
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche", ml)
        cap = _p(tenant, "Cap", un)
        _stock(tenant, warehouse, leche, qty="1000")  # 1000 ML
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche,
                                   qty=Decimal("0.2"), unit=l)  # 0.2 L = 200 ML

        m = compute_virtual_stock_map(tenant.id, store.id)
        assert m[cap.id] == Decimal("5.000")

    def test_inactive_recipe_treats_as_raw(self, tenant, store, warehouse):
        """Si la receta está inactiva, el producto se trata como raw
        (devuelve su on_hand directo, o 0 si no tiene StockItem)."""
        un = _u(tenant, "UN")
        leche = _p(tenant, "L", un)
        cap = _p(tenant, "C", un)
        _stock(tenant, warehouse, leche, qty="100")
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=False)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche, qty=Decimal("10"), unit=un)

        m = compute_virtual_stock_map(tenant.id, store.id)
        # cap está inactivo como compuesto → no entra en all_recipes →
        # se trata como raw → no tiene StockItem → no aparece en m
        assert cap.id not in m
        assert m[leche.id] == Decimal("100")


@pytest.mark.django_db
class TestAllowNegativeStockPropagation:
    """Cuando un producto compuesto (con receta) tiene allow_negative_stock=True,
    sus ingredientes (recursivos) heredan el permiso SOLO durante esa venta.
    Esto matchea la expectativa del dueño: "marco Latte vainilla como vender
    sin stock" → debe poder venderse aunque leche/café estén en 0."""

    def test_parent_flag_propagates_to_raw_ingredient(
        self, api_client, tenant, store, warehouse,
    ):
        """Vender Latte vainilla con la flag, leche en 0, sin flag en leche
        → antes: 409 shortage. Ahora: 201 OK, leche queda en 0 (clampeada)."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche prop", ml)  # SIN flag
        cap = _p(tenant, "Cap prop", un)
        cap.allow_negative_stock = True  # ← solo el padre con flag
        cap.save()
        _stock(tenant, warehouse, leche, qty="0")  # ← stock=0
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche,
                                   qty=Decimal("200"), unit=ml)

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, \
            f"Esperado 201 (flag propagada), obtuvo {r.status_code}: {r.data}"

        # Stock leche queda en 0 (clampeada, no negativa)
        si = StockItem.objects.get(product=leche, warehouse=warehouse)
        assert si.on_hand == Decimal("0.000")

    def test_parent_flag_propagates_through_nested_recipe(
        self, api_client, tenant, store, warehouse,
    ):
        """Latte vainilla → Latte → leche. Marcar Latte vainilla con la flag
        debe permitir vender aunque leche esté en 0 (propagación recursiva)."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche n", ml)  # SIN flag
        latte = _p(tenant, "Latte n", un)  # SIN flag
        latte_v = _p(tenant, "Latte Van n", un)
        latte_v.allow_negative_stock = True  # ← solo el TOP padre
        latte_v.save()
        _stock(tenant, warehouse, leche, qty="0")  # ← sin stock
        rl = Recipe.objects.create(tenant=tenant, product=latte, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rl, ingredient=leche, qty=Decimal("200"), unit=ml)
        rlv = Recipe.objects.create(tenant=tenant, product=latte_v, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rlv, ingredient=latte, qty=Decimal("1"), unit=un)

        r = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": latte_v.id, "qty": "1", "unit_price": "4500"}],
            "payments": [{"method": "cash", "amount": 4500}],
        }, format="json")
        assert r.status_code == 201, \
            f"Propagación recursiva debe permitir venta. Got {r.status_code}: {r.data}"

    def test_no_propagation_to_unrelated_sales(
        self, api_client, tenant, store, warehouse,
    ):
        """Si Latte vainilla tiene la flag, eso NO afecta otras ventas.
        Vender un Cappuccino aparte (que también usa leche pero NO tiene
        la flag) debe seguir bloqueando si leche=0."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche unrel", ml)  # SIN flag
        latte_v = _p(tenant, "Latte unrel", un)
        latte_v.allow_negative_stock = True  # ← flag solo en latte_v
        latte_v.save()
        cap = _p(tenant, "Cap unrel", un)  # SIN flag
        _stock(tenant, warehouse, leche, qty="0")
        rl = Recipe.objects.create(tenant=tenant, product=latte_v, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rl, ingredient=leche,
                                   qty=Decimal("200"), unit=ml)
        rc = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=rc, ingredient=leche,
                                   qty=Decimal("150"), unit=ml)

        # Vender Cappuccino solo (sin Latte vainilla en la misma sale)
        # → la flag de latte_v NO se propaga acá → debe fallar
        r = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }, format="json")
        assert r.status_code == 409, \
            f"Cappuccino sin flag debe bloquear con leche=0. Got {r.status_code}: {r.data}"


@pytest.mark.django_db
class TestIsVirtualProduct:
    def test_true_for_active_recipe(self, tenant):
        un = _u(tenant, "UN")
        p = _p(tenant, "P", un)
        Recipe.objects.create(tenant=tenant, product=p, is_active=True)
        assert is_virtual_product(p.id, tenant.id) is True

    def test_false_for_inactive_recipe(self, tenant):
        un = _u(tenant, "UN")
        p = _p(tenant, "P", un)
        Recipe.objects.create(tenant=tenant, product=p, is_active=False)
        assert is_virtual_product(p.id, tenant.id) is False

    def test_false_for_no_recipe(self, tenant):
        un = _u(tenant, "UN")
        p = _p(tenant, "P", un)
        assert is_virtual_product(p.id, tenant.id) is False


@pytest.mark.django_db
class TestABCAnalysisIncludesVirtualStock:
    """E2E: el endpoint de ABC ahora muestra current_stock de productos
    compuestos calculado vía virtual_stock, y marca is_virtual_stock=True."""

    def test_abc_shows_virtual_stock_for_composed_product(
        self, api_client, tenant, store, warehouse, owner, forecast_subscription,
    ):
        from datetime import datetime, time, timedelta
        from django.utils import timezone
        from sales.models import Sale

        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche abc", ml)
        cap = _p(tenant, "Cap abc", un)
        _stock(tenant, warehouse, leche, qty="2000")  # 2000 ML
        r = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=leche,
                                   qty=Decimal("200"), unit=ml)

        # Hacer una venta para que el producto entre al ABC
        resp = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }, format="json")
        assert resp.status_code == 201
        # Mover sale a una fecha dentro del rango por defecto del ABC (90 días)
        yesterday = (timezone.now() - timedelta(days=1)).date()
        yesterday_noon = timezone.make_aware(datetime.combine(yesterday, time(12, 0)))
        Sale.objects.filter(id=resp.data["id"]).update(created_at=yesterday_noon)

        # Llamar ABC
        r = api_client.get("/api/reports/abc-analysis/")
        assert r.status_code == 200, r.data
        items = r.data.get("results", [])
        # Buscar el cap en la respuesta
        cap_row = next((x for x in items if x["product_id"] == cap.id), None)
        assert cap_row is not None, f"Cap no aparece en ABC: {items}"
        # Stock real era 0 antes del fix; ahora debe ser 9 (2000-200=1800, /200=9)
        # Antes de la venta: 2000 ML; después: 1800 ML; producible = 1800/200 = 9
        assert Decimal(cap_row["current_stock"]) == Decimal("9.000"), \
            f"Esperado 9 caps producibles, obtuvo {cap_row['current_stock']}"
        assert cap_row["is_virtual_stock"] is True, \
            "Cap debe estar marcado como virtual_stock=True"

    def test_abc_raw_product_unchanged(
        self, api_client, tenant, store, warehouse, owner, forecast_subscription,
    ):
        """Producto raw sigue mostrando su on_hand directo, is_virtual_stock=False."""
        from datetime import datetime, time, timedelta
        from django.utils import timezone
        from sales.models import Sale

        un = _u(tenant, "UN")
        p = _p(tenant, "Galletita", un)
        _stock(tenant, warehouse, p, qty="100")

        resp = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "5", "unit_price": "500"}],
            "payments": [{"method": "cash", "amount": 2500}],
        }, format="json")
        assert resp.status_code == 201
        yesterday = (timezone.now() - timedelta(days=1)).date()
        yesterday_noon = timezone.make_aware(datetime.combine(yesterday, time(12, 0)))
        Sale.objects.filter(id=resp.data["id"]).update(created_at=yesterday_noon)

        r = api_client.get("/api/reports/abc-analysis/")
        assert r.status_code == 200
        items = r.data.get("results", [])
        row = next((x for x in items if x["product_id"] == p.id), None)
        assert row is not None
        assert Decimal(row["current_stock"]) == Decimal("95")  # 100 - 5
        assert row["is_virtual_stock"] is False
