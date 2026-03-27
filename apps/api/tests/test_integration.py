"""
Test plan de integración pre-producción.

Nivel 1 — Integridad de datos (9 tests)
Nivel 2 — Flujos E2E (3 tests)
Nivel 3 — Benchmark (6 tests)
Nivel 4 — Multi-tenant (7 tests)
"""
import pytest
from decimal import Decimal

from django.test.utils import override_settings

from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product, Category, Recipe, RecipeLine
from inventory.models import StockItem, StockMove
from sales.models import Sale, SaleLine, SalePayment
from sales.services import create_sale, StockShortageError

D = Decimal
Q2 = Decimal("0.01")
Q3 = Decimal("0.001")


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _receive(client, warehouse_id, product_id, qty, unit_cost=None):
    body = {"warehouse_id": warehouse_id, "product_id": product_id, "qty": str(qty)}
    if unit_cost is not None:
        body["unit_cost"] = str(unit_cost)
    return client.post("/api/inventory/receive/", body, format="json")


def _sell(client, warehouse_id, lines, payments=None, sale_type="VENTA"):
    body = {
        "warehouse_id": warehouse_id,
        "lines": lines,
        "payments": payments or [],
        "sale_type": sale_type,
    }
    return client.post("/api/sales/sales/", body, format="json")


def _adjust(client, warehouse_id, product_id, qty, note="test", new_avg_cost=None):
    body = {"warehouse_id": warehouse_id, "product_id": product_id, "qty": str(qty), "note": note}
    if new_avg_cost is not None:
        body["new_avg_cost"] = str(new_avg_cost)
    return client.post("/api/inventory/adjust/", body, format="json")


def _stock(tenant_id, warehouse_id, product_id):
    return StockItem.objects.get(tenant_id=tenant_id, warehouse_id=warehouse_id, product_id=product_id)


# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 1 — INTEGRIDAD DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDataIntegrity:

    # ── 1. PPP (weighted avg cost) al recibir mercadería ───────────────────
    def test_ppp_receive(self, api_client, warehouse, product, tenant):
        # Receive 10 @ $100
        r = _receive(api_client, warehouse.id, product.id, 10, 100)
        assert r.status_code == 201
        si = _stock(tenant.id, warehouse.id, product.id)
        assert si.avg_cost == D("100.000")
        assert si.on_hand == D("10.000")

        # Receive 10 more @ $200 → PPP = (10*100 + 10*200)/20 = 150
        r = _receive(api_client, warehouse.id, product.id, 10, 200)
        assert r.status_code == 201
        si.refresh_from_db()
        assert si.avg_cost == D("150.000")
        assert si.on_hand == D("20.000")
        assert si.stock_value == (si.on_hand * si.avg_cost).quantize(Q3)

    # ── 2. Vender NO altera avg_cost ──────────────────────────────────────
    def test_sale_does_not_alter_avg_cost(self, api_client, warehouse, product, tenant):
        _receive(api_client, warehouse.id, product.id, 10, 100)
        si = _stock(tenant.id, warehouse.id, product.id)
        avg_before = si.avg_cost

        r = _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "3", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 4500}])
        assert r.status_code == 201

        si.refresh_from_db()
        assert si.avg_cost == avg_before
        assert si.on_hand == D("7.000")

    # ── 3. stock_value = on_hand × avg_cost siempre ──────────────────────
    def test_stock_value_consistency(self, api_client, warehouse, product, tenant):
        _receive(api_client, warehouse.id, product.id, 20, 150)
        _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "5", "unit_price": "1000"},
        ], [{"method": "cash", "amount": 5000}])

        si = _stock(tenant.id, warehouse.id, product.id)
        expected = (si.on_hand * si.avg_cost).quantize(Q3)
        assert si.stock_value == expected

    # ── 4. Venta multilínea descuenta todos los productos ────────────────
    def test_multiline_sale_decrements_all(self, api_client, warehouse, product, product_b, tenant):
        _receive(api_client, warehouse.id, product.id, 10, 100)
        _receive(api_client, warehouse.id, product_b.id, 10, 50)

        r = _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "3", "unit_price": "1000"},
            {"product_id": product_b.id, "qty": "4", "unit_price": "500"},
        ], [{"method": "cash", "amount": 5000}])
        assert r.status_code == 201

        si_a = _stock(tenant.id, warehouse.id, product.id)
        si_b = _stock(tenant.id, warehouse.id, product_b.id)
        assert si_a.on_hand == D("7.000")
        assert si_b.on_hand == D("6.000")

    # ── 5. Void restaura stock_value exacto ──────────────────────────────
    def test_void_restores_stock_value(self, api_client, warehouse, product, tenant):
        _receive(api_client, warehouse.id, product.id, 10, 200)
        si_before = _stock(tenant.id, warehouse.id, product.id)
        sv_before = si_before.stock_value
        oh_before = si_before.on_hand

        res = _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "4", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 6000}])
        sale_id = res.data["id"]

        # Void the sale
        v = api_client.post(f"/api/sales/sales/{sale_id}/void/", format="json")
        assert v.status_code == 200
        assert v.data["status"] == "VOID"

        si_after = _stock(tenant.id, warehouse.id, product.id)
        assert si_after.on_hand == oh_before
        assert si_after.stock_value == sv_before

    # ── 6. Pagos mixtos se registran completos ───────────────────────────
    def test_mixed_payments(self, api_client, warehouse, product, tenant):
        _receive(api_client, warehouse.id, product.id, 10, 100)
        payments = [
            {"method": "cash", "amount": 2000},
            {"method": "card", "amount": 1500},
            {"method": "transfer", "amount": 500},
        ]
        r = _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "4", "unit_price": "1000"},
        ], payments)
        assert r.status_code == 201

        sale = Sale.objects.get(id=r.data["id"])
        db_payments = list(sale.payments.order_by("method"))
        assert len(db_payments) == 3
        total_paid = sum(p.amount for p in db_payments)
        assert total_paid == D("4000.00")

        methods = {p.method for p in db_payments}
        assert methods == {"cash", "card", "transfer"}

    # ── 7. Receta descuenta ingredientes (no el producto padre) ──────────
    def test_recipe_decrements_ingredients(self, api_client, warehouse, tenant):
        # Create parent product (e.g. "Hamburguesa")
        parent = Product.objects.create(tenant=tenant, name="Hamburguesa", price=D("5000"), is_active=True)
        ing_a = Product.objects.create(tenant=tenant, name="Pan", price=D("200"), is_active=True)
        ing_b = Product.objects.create(tenant=tenant, name="Carne", price=D("1500"), is_active=True)

        recipe = Recipe.objects.create(tenant=tenant, product=parent, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ing_a, qty=D("1"))
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ing_b, qty=D("1"))

        # Stock ingredients, NOT parent
        _receive(api_client, warehouse.id, ing_a.id, 10, 200)
        _receive(api_client, warehouse.id, ing_b.id, 10, 1500)

        r = _sell(api_client, warehouse.id, [
            {"product_id": parent.id, "qty": "2", "unit_price": "5000"},
        ], [{"method": "cash", "amount": 10000}])
        assert r.status_code == 201

        # Ingredients decremented
        si_pan = _stock(tenant.id, warehouse.id, ing_a.id)
        si_carne = _stock(tenant.id, warehouse.id, ing_b.id)
        assert si_pan.on_hand == D("8.000")
        assert si_carne.on_hand == D("8.000")

        # Parent has no stock entry (or zero)
        assert not StockItem.objects.filter(
            tenant=tenant, warehouse=warehouse, product=parent, on_hand__gt=0
        ).exists()

    # ── 8. Costo de venta con receta calculado desde ingredientes ────────
    def test_recipe_sale_cost(self, api_client, warehouse, tenant):
        parent = Product.objects.create(tenant=tenant, name="Combo", price=D("8000"), is_active=True)
        ing_a = Product.objects.create(tenant=tenant, name="Bebida", price=D("500"), is_active=True)
        ing_b = Product.objects.create(tenant=tenant, name="Snack", price=D("300"), is_active=True)

        recipe = Recipe.objects.create(tenant=tenant, product=parent, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ing_a, qty=D("1"))
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ing_b, qty=D("2"))

        _receive(api_client, warehouse.id, ing_a.id, 20, 400)   # avg_cost = 400
        _receive(api_client, warehouse.id, ing_b.id, 20, 250)   # avg_cost = 250

        r = _sell(api_client, warehouse.id, [
            {"product_id": parent.id, "qty": "3", "unit_price": "8000"},
        ], [{"method": "cash", "amount": 24000}])
        assert r.status_code == 201

        sale = Sale.objects.get(id=r.data["id"])
        # Cost per unit = 400*1 + 250*2 = 900
        # Total cost = 3 * 900 = 2700
        assert sale.total_cost == D("2700.000")
        assert sale.gross_profit == (sale.total - sale.total_cost).quantize(Q2)

    # ── 9. Receta con ingrediente insuficiente rechaza la venta ──────────
    def test_recipe_insufficient_ingredient(self, api_client, warehouse, tenant):
        parent = Product.objects.create(tenant=tenant, name="Pizza", price=D("6000"), is_active=True)
        ing = Product.objects.create(tenant=tenant, name="Masa", price=D("800"), is_active=True)

        recipe = Recipe.objects.create(tenant=tenant, product=parent, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ing, qty=D("1"))

        # Only 2 masa in stock, try to sell 5 pizzas
        _receive(api_client, warehouse.id, ing.id, 2, 800)

        r = _sell(api_client, warehouse.id, [
            {"product_id": parent.id, "qty": "5", "unit_price": "6000"},
        ], [{"method": "cash", "amount": 30000}])
        assert r.status_code == 409
        assert "shortages" in r.data or "stock" in str(r.data).lower()


# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 2 — FLUJOS E2E
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestE2EFlows:

    # ── 1. Ciclo completo: crear producto → recibir → vender → dashboard ─
    def test_full_cycle(self, api_client, warehouse, tenant, owner):
        # Create product via API
        r = api_client.post("/api/catalog/products/", {
            "name": "Galleta Premium", "price": "1500", "sku": "GAL-001",
        }, format="json")
        assert r.status_code == 201
        pid = r.data["id"]

        # Receive stock
        r = _receive(api_client, warehouse.id, pid, 50, 800)
        assert r.status_code == 201

        # Sell
        r = _sell(api_client, warehouse.id, [
            {"product_id": pid, "qty": "10", "unit_price": "1500"},
        ], [{"method": "cash", "amount": 15000}])
        assert r.status_code == 201
        sale_id = r.data["id"]

        # Verify stock
        si = _stock(tenant.id, warehouse.id, pid)
        assert si.on_hand == D("40.000")

        # Dashboard should reflect the sale
        r = api_client.get("/api/dashboard/summary/")
        assert r.status_code == 200
        kpis = r.data.get("kpis", {})
        today = kpis.get("sales_today", {})
        assert D(today.get("total", today.get("revenue", "0"))) >= D("15000")

    # ── 2. Flujo de ajuste (merma) → verificar consistencia ──────────────
    def test_shrinkage_adjustment(self, api_client, warehouse, product, tenant):
        _receive(api_client, warehouse.id, product.id, 100, 500)
        si = _stock(tenant.id, warehouse.id, product.id)
        assert si.on_hand == D("100.000")

        # Merma: -5 units
        r = _adjust(api_client, warehouse.id, product.id, -5, "Merma por vencimiento")
        assert r.status_code == 201

        si.refresh_from_db()
        assert si.on_hand == D("95.000")
        assert si.stock_value == (si.on_hand * si.avg_cost).quantize(Q3)

        # Verify StockMove was created
        move = StockMove.objects.filter(
            tenant=tenant, warehouse=warehouse, product=product,
            move_type=StockMove.ADJ, ref_type="ADJUST",
        ).last()
        assert move is not None
        assert move.qty == D("-5.000") or move.qty == D("5.000")

    # ── 3. Detalle de venta con líneas, pagos y costos ───────────────────
    def test_sale_detail_complete(self, api_client, warehouse, product, product_b, tenant):
        _receive(api_client, warehouse.id, product.id, 20, 300)
        _receive(api_client, warehouse.id, product_b.id, 20, 150)

        r = _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "2", "unit_price": "1000"},
            {"product_id": product_b.id, "qty": "3", "unit_price": "500"},
        ], [
            {"method": "cash", "amount": 2000},
            {"method": "card", "amount": 1500},
        ])
        assert r.status_code == 201
        sale_id = r.data["id"]

        # GET detail
        r = api_client.get(f"/api/sales/sales/{sale_id}/")
        assert r.status_code == 200

        data = r.data
        assert len(data["lines"]) == 2
        assert len(data["payments"]) == 2
        assert data["status"] == "COMPLETED"

        # Verify cost snapshot exists
        for line in data["lines"]:
            assert "unit_cost_snapshot" in line or "line_cost" in line

        # Verify totals
        assert D(data["subtotal"]) == D("3500.00")
        assert D(data["total_cost"]) > D("0")


# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 3 — BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBenchmark:

    @pytest.fixture
    def bulk_products(self, tenant, warehouse, owner):
        """Create 200 products with stock."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=owner)

        products = Product.objects.bulk_create([
            Product(tenant=tenant, name=f"Prod {i:03d}", price=D("1000"), is_active=True)
            for i in range(200)
        ])
        StockItem.objects.bulk_create([
            StockItem(
                tenant=tenant, warehouse=warehouse, product=p,
                on_hand=D("50"), avg_cost=D("500"), stock_value=D("25000"),
            )
            for p in products
        ])
        # Create some sales for dashboard
        from sales.services import create_sale
        for i in range(5):
            p = products[i]
            create_sale(
                user=owner, tenant_id=tenant.id, store_id=owner.active_store_id,
                warehouse_id=warehouse.id,
                lines_in=[{"product_id": p.id, "qty": "2", "unit_price": "1000"}],
                payments_in=[{"method": "cash", "amount": 2000}],
            )
        return products

    # ── 1. Dashboard: máximo 15 queries con 200 productos ────────────────
    def test_dashboard_max_queries(self, api_client, bulk_products):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            r = api_client.get("/api/dashboard/summary/")
        assert r.status_code == 200
        assert len(ctx) <= 15, f"Dashboard used {len(ctx)} queries (max 15)"

    # ── 2. Dashboard: responde en menos de 500ms ─────────────────────────
    def test_dashboard_response_time(self, api_client, bulk_products):
        import time
        start = time.perf_counter()
        r = api_client.get("/api/dashboard/summary/")
        elapsed = time.perf_counter() - start
        assert r.status_code == 200
        assert elapsed < 0.5, f"Dashboard took {elapsed:.3f}s (max 0.5s)"

    # ── 3. Listado productos: máximo 5 queries ───────────────────────────
    def test_product_list_max_queries(self, api_client, bulk_products):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            r = api_client.get("/api/catalog/products/?page_size=50")
        assert r.status_code == 200
        # Budget: 1 count + 1 products (join recipe+category+unit) + 1 prefetch barcodes = 3
        assert len(ctx) <= 5, f"Product list used {len(ctx)} queries (max 5)"

    # ── 4. Crear venta: máximo 20 queries ────────────────────────────────
    def test_create_sale_max_queries(self, api_client, warehouse, bulk_products):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        p = bulk_products[0]
        with CaptureQueriesContext(connection) as ctx:
            r = _sell(api_client, warehouse.id, [
                {"product_id": p.id, "qty": "1", "unit_price": "1000"},
            ], [{"method": "cash", "amount": 1000}])
        assert r.status_code == 201
        assert len(ctx) <= 20, f"Create sale used {len(ctx)} queries (max 20)"

    # ── 5. Listado ventas: máximo 5 queries ──────────────────────────────
    def test_sale_list_max_queries(self, api_client, bulk_products):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            r = api_client.get("/api/sales/sales/list/")
        assert r.status_code == 200
        assert len(ctx) <= 5, f"Sale list used {len(ctx)} queries (max 5)"

    # ── 6. Crear venta: responde en menos de 300ms ───────────────────────
    def test_create_sale_response_time(self, api_client, warehouse, bulk_products):
        import time
        p = bulk_products[10]
        start = time.perf_counter()
        r = _sell(api_client, warehouse.id, [
            {"product_id": p.id, "qty": "1", "unit_price": "1000"},
        ], [{"method": "cash", "amount": 1000}])
        elapsed = time.perf_counter() - start
        assert r.status_code == 201
        assert elapsed < 0.3, f"Create sale took {elapsed:.3f}s (max 0.3s)"


# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 4 — MULTI-TENANT
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMultiTenant:

    @pytest.fixture
    def tenant_b(self, db):
        return Tenant.objects.create(name="Otra Empresa", slug="otra-empresa")

    @pytest.fixture
    def store_b(self, tenant_b):
        return Store.objects.create(tenant=tenant_b, name="Sucursal B")

    @pytest.fixture
    def warehouse_b(self, tenant_b, store_b):
        return Warehouse.objects.create(tenant=tenant_b, store=store_b, name="Bodega B")

    @pytest.fixture
    def owner_b(self, tenant_b, store_b):
        user = User.objects.create_user(
            username="owner_b", password="testpass123",
            tenant=tenant_b, active_store=store_b, role=User.Role.OWNER,
        )
        return user

    @pytest.fixture
    def client_b(self, owner_b):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=owner_b)
        return c

    @pytest.fixture
    def product_in_b(self, tenant_b):
        return Product.objects.create(tenant=tenant_b, name="Prod Tenant B", price=D("999"), is_active=True)

    # ── 1. Productos aislados entre tenants ──────────────────────────────
    def test_products_isolated(self, api_client, client_b, product, product_in_b):
        # Tenant A only sees its products
        r = api_client.get("/api/catalog/products/")
        ids_a = {p["id"] for p in (r.data.get("results", r.data) if isinstance(r.data, (dict, list)) else [])}
        assert product.id in ids_a
        assert product_in_b.id not in ids_a

        # Tenant B only sees its products
        r = client_b.get("/api/catalog/products/")
        ids_b = {p["id"] for p in (r.data.get("results", r.data) if isinstance(r.data, (dict, list)) else [])}
        assert product_in_b.id in ids_b
        assert product.id not in ids_b

    # ── 2. Ventas aisladas entre tenants ─────────────────────────────────
    def test_sales_isolated(self, api_client, client_b, warehouse, warehouse_b, product, product_in_b, tenant, tenant_b):
        _receive(api_client, warehouse.id, product.id, 10, 100)
        _receive(client_b, warehouse_b.id, product_in_b.id, 10, 100)

        _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "1", "unit_price": "1000"},
        ], [{"method": "cash", "amount": 1000}])

        _sell(client_b, warehouse_b.id, [
            {"product_id": product_in_b.id, "qty": "1", "unit_price": "999"},
        ], [{"method": "cash", "amount": 999}])

        # Tenant A sees only its sales
        r = api_client.get("/api/sales/sales/list/")
        sales_a = r.data.get("results", r.data)
        assert all(s.get("store_id") != warehouse_b.store_id for s in sales_a)

        # Tenant B sees only its sales
        r = client_b.get("/api/sales/sales/list/")
        sales_b = r.data.get("results", r.data)
        assert all(s.get("store_id") != warehouse.store_id for s in sales_b)

    # ── 3. Dashboard aislado (no muestra datos cruzados) ─────────────────
    def test_dashboard_isolated(self, api_client, client_b, warehouse, warehouse_b, product, product_in_b, tenant, tenant_b):
        _receive(api_client, warehouse.id, product.id, 10, 100)
        _receive(client_b, warehouse_b.id, product_in_b.id, 10, 100)

        _sell(api_client, warehouse.id, [
            {"product_id": product.id, "qty": "5", "unit_price": "1000"},
        ], [{"method": "cash", "amount": 5000}])

        r_a = api_client.get("/api/dashboard/summary/")
        r_b = client_b.get("/api/dashboard/summary/")
        assert r_a.status_code == 200
        assert r_b.status_code == 200

        today_a = r_a.data["kpis"]["sales_today"]
        today_b = r_b.data["kpis"]["sales_today"]
        rev_a = D(today_a.get("total", today_a.get("revenue", "0")))
        rev_b = D(today_b.get("total", today_b.get("revenue", "0")))
        assert rev_a >= D("5000")
        assert rev_b == D("0")

    # ── 4. No se puede operar en bodega de otro tenant ───────────────────
    def test_cannot_use_other_tenant_warehouse(self, api_client, warehouse_b, product, tenant):
        r = _receive(api_client, warehouse_b.id, product.id, 10, 100)
        assert r.status_code in (400, 403, 404, 409)

    # ── 5. No se puede ver detalle de venta de otro tenant ───────────────
    def test_cannot_view_other_tenant_sale(self, api_client, client_b, warehouse, warehouse_b, product, product_in_b, tenant_b):
        _receive(client_b, warehouse_b.id, product_in_b.id, 10, 100)
        res = _sell(client_b, warehouse_b.id, [
            {"product_id": product_in_b.id, "qty": "1", "unit_price": "999"},
        ], [{"method": "cash", "amount": 999}])
        sale_id = res.data["id"]

        # Tenant A tries to access Tenant B's sale
        r = api_client.get(f"/api/sales/sales/{sale_id}/")
        assert r.status_code == 404

    # ── 6. No se puede ajustar stock de producto de otro tenant ──────────
    def test_cannot_adjust_other_tenant_stock(self, api_client, warehouse_b, product_in_b):
        r = _adjust(api_client, warehouse_b.id, product_in_b.id, -1, "hack")
        assert r.status_code in (400, 403, 404, 409)

    # ── 7. Categorías aisladas ───────────────────────────────────────────
    def test_categories_isolated(self, api_client, client_b, tenant, tenant_b):
        Category.objects.create(tenant=tenant, name="Cat Tenant A")
        Category.objects.create(tenant=tenant_b, name="Cat Tenant B")

        r_a = api_client.get("/api/catalog/categories/")
        names_a = {c["name"] for c in (r_a.data.get("results", r_a.data) if isinstance(r_a.data, (dict, list)) else [])}
        assert "Cat Tenant A" in names_a
        assert "Cat Tenant B" not in names_a

        r_b = client_b.get("/api/catalog/categories/")
        names_b = {c["name"] for c in (r_b.data.get("results", r_b.data) if isinstance(r_b.data, (dict, list)) else [])}
        assert "Cat Tenant B" in names_b
        assert "Cat Tenant A" not in names_b
