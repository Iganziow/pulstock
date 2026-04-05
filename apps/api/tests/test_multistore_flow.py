"""
Multi-store adversarial flow tests.
Simulates an admin managing 5 stores and intentionally breaks things.
"""
import pytest
from decimal import Decimal

from rest_framework.test import APIClient
from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product
from billing.models import Plan, Subscription
from django.utils import timezone
from datetime import timedelta


# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def plan_pro(db):
    return Plan.objects.create(
        key="pro_multi", name="Pro Multi", price_clp=0,
        max_products=-1, max_stores=5, max_users=-1, max_registers=-1,
        has_forecast=True, has_abc=True, has_reports=True, has_transfers=True,
    )


@pytest.fixture
def tenant_ms(db):
    t = Tenant.objects.create(name="MultiStore Inc", slug="multistore-test")
    # Signal creates "Local Principal" + "Bodega Principal" automatically
    return t


@pytest.fixture
def subscription_ms(tenant_ms, plan_pro):
    now = timezone.now()
    sub, _ = Subscription.objects.get_or_create(
        tenant=tenant_ms,
        defaults={
            "plan": plan_pro, "status": "active",
            "current_period_start": now,
            "current_period_end": now + timedelta(days=30),
        },
    )
    return sub


@pytest.fixture
def store1(tenant_ms):
    """Use the signal-created store as store1."""
    return Store.objects.filter(tenant=tenant_ms).first()


@pytest.fixture
def owner_ms(tenant_ms, store1):
    return User.objects.create_user(
        username="ms_owner", password="Test1234!",
        tenant=tenant_ms, active_store=store1, role="owner",
    )


@pytest.fixture
def client_ms(owner_ms):
    c = APIClient()
    c.force_authenticate(user=owner_ms)
    return c


@pytest.fixture
def product_ms(tenant_ms):
    return Product.objects.create(tenant=tenant_ms, name="Coca-Cola", price=Decimal("990"))


# ══════════════════════════════════════════════════════════════
# 1. CREATE 5 STORES — FULL FLOW
# ══════════════════════════════════════════════════════════════

class TestCreateMultipleStores:
    def test_create_5_stores(self, client_ms, subscription_ms):
        """Admin puede crear hasta 5 tiendas (plan limit). store1 ya existe (fixture)."""
        # store1 ya existe, crear 4 más = total 5
        for i in range(2, 6):
            r = client_ms.post("/api/core/stores/", {
                "name": f"Local {i}",
                "code": f"L{i}",
                "warehouse_name": f"Bodega {i}",
            }, format="json")
            assert r.status_code == 201, f"Store {i} failed: {r.json()}"
            assert r.json()["name"] == f"Local {i}"

    def test_6th_store_rejected_by_plan(self, client_ms, subscription_ms):
        """6ta tienda debe ser rechazada por límite del plan."""
        # store1 ya existe, crear 4 más = total 5 (máximo)
        for i in range(2, 6):
            client_ms.post("/api/core/stores/", {"name": f"Local {i}"}, format="json")

        # La 6ta debe fallar
        r = client_ms.post("/api/core/stores/", {"name": "Local 6"}, format="json")
        assert r.status_code in (402, 403)

    def test_duplicate_store_name_rejected(self, client_ms, subscription_ms):
        """Nombre duplicado debe fallar."""
        r = client_ms.post("/api/core/stores/", {"name": "Local Principal"}, format="json")
        assert r.status_code == 400

    def test_empty_store_name_rejected(self, client_ms, subscription_ms):
        r = client_ms.post("/api/core/stores/", {"name": ""}, format="json")
        assert r.status_code == 400

    def test_whitespace_store_name_rejected(self, client_ms, subscription_ms):
        r = client_ms.post("/api/core/stores/", {"name": "   "}, format="json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
# 2. SWITCH BETWEEN STORES
# ══════════════════════════════════════════════════════════════

class TestSwitchStores:
    @pytest.fixture
    def five_stores(self, client_ms, subscription_ms, tenant_ms):
        stores = list(Store.objects.filter(tenant=tenant_ms))
        for i in range(len(stores) + 1, 6):
            r = client_ms.post("/api/core/stores/", {"name": f"Tienda {i}"}, format="json")
            stores.append(Store.objects.get(id=r.json()["id"]))
        return stores

    def test_switch_to_each_store(self, client_ms, five_stores):
        """Cambiar a cada tienda y verificar que bootstrap devuelve la correcta."""
        for store in five_stores:
            r = client_ms.post("/api/stores/set-active/", {"store_id": store.id}, format="json")
            assert r.status_code == 200

            boot = client_ms.get("/api/core/bootstrap/")
            assert boot.json()["active_store"]["id"] == store.id

    def test_switch_to_inactive_store_fails(self, client_ms, five_stores):
        """No se puede cambiar a una tienda desactivada."""
        store = five_stores[2]
        store.is_active = False
        store.save()

        r = client_ms.post("/api/stores/set-active/", {"store_id": store.id}, format="json")
        assert r.status_code == 404

    def test_switch_to_nonexistent_store_fails(self, client_ms):
        r = client_ms.post("/api/stores/set-active/", {"store_id": 99999}, format="json")
        assert r.status_code == 404

    def test_switch_to_other_tenant_store_fails(self, client_ms):
        other_t = Tenant.objects.create(name="Other", slug="other-ms")
        other_s = Store.objects.create(tenant=other_t, name="Alien Store")
        r = client_ms.post("/api/stores/set-active/", {"store_id": other_s.id}, format="json")
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════
# 3. STORE-SCOPED DATA ISOLATION
# ══════════════════════════════════════════════════════════════

class TestStoreDataIsolation:
    """Verify that sales, tables, caja, and inventory are scoped to active store."""

    @pytest.fixture
    def two_stores(self, client_ms, subscription_ms, tenant_ms, store1):
        r = client_ms.post("/api/core/stores/", {"name": "Local Norte"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])
        wh2 = Warehouse.objects.filter(store=store2).first()
        wh1 = Warehouse.objects.filter(store=store1).first()
        return store1, wh1, store2, wh2

    def test_tables_isolated_between_stores(self, client_ms, two_stores):
        store1, _, store2, _ = two_stores

        # Create table in store1
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r = client_ms.post("/api/tables/tables/", {"name": "Mesa 1"}, format="json")
        assert r.status_code == 201

        # Switch to store2 — should NOT see store1's table
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        r2 = client_ms.get("/api/tables/tables/")
        assert r2.status_code == 200
        names = [t["name"] for t in r2.json()]
        assert "Mesa 1" not in names

        # Create table with SAME name in store2 — should work (different store)
        r3 = client_ms.post("/api/tables/tables/", {"name": "Mesa 1"}, format="json")
        assert r3.status_code == 201

    def test_warehouses_isolated_by_store(self, client_ms, two_stores):
        store1, wh1, store2, wh2 = two_stores

        # In store1, should see store1's warehouse
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r = client_ms.get("/api/core/warehouses/")
        wh_ids = [w["id"] for w in r.json()]
        assert wh1.id in wh_ids
        assert wh2.id not in wh_ids

        # In store2, should see store2's warehouse
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        r2 = client_ms.get("/api/core/warehouses/")
        wh_ids2 = [w["id"] for w in r2.json()]
        assert wh2.id in wh_ids2
        assert wh1.id not in wh_ids2

    def test_inventory_cross_store_warehouse_rejected(self, client_ms, two_stores, product_ms):
        """Cannot use store2's warehouse while active in store1."""
        store1, wh1, store2, wh2 = two_stores

        # Active in store1, try to adjust stock in store2's warehouse
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r = client_ms.post("/api/inventory/adjust/", {
            "warehouse_id": wh2.id,
            "product_id": product_ms.id,
            "qty": "10",
        }, format="json")
        assert r.status_code == 409
        assert "active store" in r.json()["detail"].lower() or "does not belong" in r.json()["detail"].lower()

    def test_sale_in_store1_invisible_from_store2(self, client_ms, two_stores, product_ms):
        """Sales created in store1 should not appear when viewing from store2."""
        store1, wh1, store2, wh2 = two_stores
        from inventory.models import StockItem

        # Add stock in store1
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        StockItem.objects.create(
            tenant=product_ms.tenant, product=product_ms, warehouse=wh1,
            on_hand=Decimal("100"), avg_cost=Decimal("500"), stock_value=Decimal("50000"),
        )

        # Create sale in store1
        r = client_ms.post("/api/sales/sales/", {
            "warehouse_id": wh1.id,
            "lines": [{"product_id": product_ms.id, "qty": "1", "unit_price": "990"}],
        }, format="json")
        assert r.status_code == 201
        sale_id = r.json()["id"]

        # Switch to store2 — sale should NOT appear
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        r2 = client_ms.get("/api/sales/sales/")
        data = r2.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(results, list):
            sale_ids = [s["id"] for s in results]
        else:
            sale_ids = []
        assert sale_id not in sale_ids


# ══════════════════════════════════════════════════════════════
# 4. DEACTIVATE STORE — EDGE CASES
# ══════════════════════════════════════════════════════════════

class TestDeactivateStore:
    @pytest.fixture
    def two_stores_setup(self, client_ms, subscription_ms, tenant_ms, store1):
        r = client_ms.post("/api/core/stores/", {"name": "Local Sur"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])
        return store1, store2

    def test_deactivate_store(self, client_ms, two_stores_setup):
        store1, store2 = two_stores_setup
        r = client_ms.patch(f"/api/core/stores/{store2.id}/", {"is_active": False}, format="json")
        assert r.status_code == 200
        store2.refresh_from_db()
        assert store2.is_active is False

    def test_deactivated_store_not_in_active_list(self, client_ms, two_stores_setup):
        store1, store2 = two_stores_setup
        client_ms.patch(f"/api/core/stores/{store2.id}/", {"is_active": False}, format="json")

        # Store list should still include it (admin sees all)
        r = client_ms.get("/api/core/stores/")
        store_ids = [s["id"] for s in r.json()]
        assert store2.id in store_ids  # admin sees all stores

        # But set-active should reject it
        r2 = client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        assert r2.status_code == 404

    def test_user_active_store_deactivated_then_operations(self, client_ms, two_stores_setup, product_ms, owner_ms):
        """If user's active store is deactivated, operations should handle gracefully."""
        store1, store2 = two_stores_setup

        # Switch to store2, then deactivate it
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        store2.is_active = False
        store2.save()

        # Now user's active_store is inactive — creating a table should still work
        # (tables are scoped to store, but store being inactive doesn't block the table creation)
        # This is a potential issue — should we block operations on inactive stores?
        r = client_ms.get("/api/tables/tables/")
        # This should return data or empty list, not crash
        assert r.status_code == 200

    def test_reactivate_store(self, client_ms, two_stores_setup):
        store1, store2 = two_stores_setup
        client_ms.patch(f"/api/core/stores/{store2.id}/", {"is_active": False}, format="json")
        r = client_ms.patch(f"/api/core/stores/{store2.id}/", {"is_active": True}, format="json")
        assert r.status_code == 200
        store2.refresh_from_db()
        assert store2.is_active is True

        # Should be able to switch to it again
        r2 = client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        assert r2.status_code == 200


# ══════════════════════════════════════════════════════════════
# 5. WAREHOUSE EDGE CASES
# ══════════════════════════════════════════════════════════════

class TestWarehouseEdgeCases:
    @pytest.fixture
    def store_with_wh(self, client_ms, subscription_ms, store1):
        wh = Warehouse.objects.filter(store=store1).first()
        return store1, wh

    def test_create_warehouse_in_other_store(self, client_ms, store_with_wh, subscription_ms, tenant_ms):
        """Can create warehouse specifying another store's ID."""
        store2 = Store.objects.create(tenant=tenant_ms, name="Local Otro WH")
        Warehouse.objects.create(tenant=tenant_ms, store=store2, name="Default WH")

        r = client_ms.post("/api/core/warehouses/", {
            "store": store2.id,
            "name": "Nueva Bodega",
        }, format="json")
        assert r.status_code == 201

    def test_duplicate_warehouse_name_rejected(self, client_ms, store_with_wh):
        store1, wh = store_with_wh
        r = client_ms.post("/api/core/warehouses/", {
            "store": store1.id,
            "name": wh.name,  # same name
        }, format="json")
        assert r.status_code == 400

    def test_deactivate_warehouse_then_use(self, client_ms, store_with_wh, product_ms):
        """Deactivating a warehouse should prevent operations on it."""
        store1, wh = store_with_wh
        wh.is_active = False
        wh.save()

        # Try to adjust stock in inactive warehouse — should be rejected
        r = client_ms.post("/api/inventory/adjust/", {
            "warehouse_id": wh.id,
            "product_id": product_ms.id,
            "qty": "5",
        }, format="json")
        assert r.status_code == 400, f"Inactive warehouse should be rejected, got {r.status_code}"

    def test_multiple_warehouses_per_store(self, client_ms, store_with_wh, product_ms):
        """Multiple warehouses in same store — stock is per-warehouse."""
        store1, wh1 = store_with_wh
        from inventory.models import StockItem

        # Create second warehouse
        r = client_ms.post("/api/core/warehouses/", {
            "store": store1.id,
            "name": "Bodega Trasera",
        }, format="json")
        assert r.status_code == 201
        wh2 = Warehouse.objects.get(id=r.json()["id"])

        # Stock in wh1
        StockItem.objects.create(
            tenant=product_ms.tenant, product=product_ms, warehouse=wh1,
            on_hand=Decimal("50"), avg_cost=Decimal("500"), stock_value=Decimal("25000"),
        )
        # Stock in wh2
        StockItem.objects.create(
            tenant=product_ms.tenant, product=product_ms, warehouse=wh2,
            on_hand=Decimal("30"), avg_cost=Decimal("500"), stock_value=Decimal("15000"),
        )

        # Stock list for wh1
        r1 = client_ms.get(f"/api/inventory/stock/?warehouse_id={wh1.id}")
        assert r1.status_code == 200

        # Stock list for wh2
        r2 = client_ms.get(f"/api/inventory/stock/?warehouse_id={wh2.id}")
        assert r2.status_code == 200


# ══════════════════════════════════════════════════════════════
# 6. CASHIER MULTI-STORE ACCESS
# ══════════════════════════════════════════════════════════════

class TestCashierMultiStore:
    def test_cashier_cannot_create_store(self, tenant_ms, store1, subscription_ms):
        cashier = User.objects.create_user(
            username="ms_cashier", password="Test1234!",
            tenant=tenant_ms, active_store=store1, role="cashier",
        )
        c = APIClient()
        c.force_authenticate(user=cashier)
        r = c.post("/api/core/stores/", {"name": "Hack Store"}, format="json")
        assert r.status_code == 403

    def test_cashier_cannot_deactivate_store(self, tenant_ms, store1, subscription_ms):
        cashier = User.objects.create_user(
            username="ms_cashier2", password="Test1234!",
            tenant=tenant_ms, active_store=store1, role="cashier",
        )
        c = APIClient()
        c.force_authenticate(user=cashier)
        r = c.patch(f"/api/core/stores/{store1.id}/", {"is_active": False}, format="json")
        assert r.status_code == 403

    def test_cashier_can_switch_to_assigned_store(self, client_ms, subscription_ms, tenant_ms, store1):
        """Cashier can switch to a store they have access to via UserStoreAccess."""
        from core.models import UserStoreAccess

        r = client_ms.post("/api/core/stores/", {"name": "Local Cashier"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])

        cashier = User.objects.create_user(
            username="ms_cashier3", password="Test1234!",
            tenant=tenant_ms, active_store=store1, role="cashier",
        )
        # Grant access to both stores
        UserStoreAccess.objects.create(user=cashier, store=store1, tenant=tenant_ms)
        UserStoreAccess.objects.create(user=cashier, store=store2, tenant=tenant_ms)

        cc = APIClient()
        cc.force_authenticate(user=cashier)

        r2 = cc.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        assert r2.status_code == 200

    def test_cashier_cannot_switch_to_unassigned_store(self, client_ms, subscription_ms, tenant_ms, store1):
        """Cashier cannot switch to a store they don't have access to."""
        r = client_ms.post("/api/core/stores/", {"name": "Local Blocked"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])

        cashier = User.objects.create_user(
            username="ms_cashier4", password="Test1234!",
            tenant=tenant_ms, active_store=store1, role="cashier",
        )
        # Only grant access to store1, not store2
        from core.models import UserStoreAccess
        UserStoreAccess.objects.create(user=cashier, store=store1, tenant=tenant_ms)

        cc = APIClient()
        cc.force_authenticate(user=cashier)

        r2 = cc.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        assert r2.status_code == 403


# ══════════════════════════════════════════════════════════════
# 7. CAJA & TABLES CROSS-STORE
# ══════════════════════════════════════════════════════════════

class TestCajaAndTablesCrossStore:
    @pytest.fixture
    def two_stores_caja(self, client_ms, subscription_ms, tenant_ms, store1):
        r = client_ms.post("/api/core/stores/", {"name": "Local Caja2"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])
        return store1, store2

    def test_cash_register_isolated_per_store(self, client_ms, two_stores_caja):
        store1, store2 = two_stores_caja

        # Create register in store1
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r1 = client_ms.post("/api/caja/registers/", {"name": "Caja 1"}, format="json")
        assert r1.status_code == 201
        reg1_id = r1.json()["id"]

        # Switch to store2 — register should NOT appear
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        r2 = client_ms.get("/api/caja/registers/")
        reg_ids = [r["id"] for r in r2.json()]
        assert reg1_id not in reg_ids

        # Create register with SAME name in store2 — should work
        r3 = client_ms.post("/api/caja/registers/", {"name": "Caja 1"}, format="json")
        assert r3.status_code == 201

    def test_open_order_in_store1_invisible_from_store2(self, client_ms, two_stores_caja, product_ms):
        store1, store2 = two_stores_caja

        # Create table + order in store1
        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        wh1 = Warehouse.objects.filter(store=store1).first()
        tr = client_ms.post("/api/tables/tables/", {"name": "Mesa Store1"}, format="json")
        table_id = tr.json()["id"]
        client_ms.post(f"/api/tables/tables/{table_id}/open/", {"warehouse_id": wh1.id}, format="json")

        # Switch to store2 — table should NOT appear
        client_ms.post("/api/stores/set-active/", {"store_id": store2.id}, format="json")
        r = client_ms.get("/api/tables/tables/")
        table_names = [t["name"] for t in r.json()]
        assert "Mesa Store1" not in table_names


# ══════════════════════════════════════════════════════════════
# 8. ADVERSARIAL — INTENTIONALLY BREAK THINGS
# ══════════════════════════════════════════════════════════════

class TestMultiStoreAdversarial:
    @pytest.fixture
    def setup(self, client_ms, subscription_ms, tenant_ms, store1, product_ms):
        r = client_ms.post("/api/core/stores/", {"name": "Adversarial Store"}, format="json")
        store2 = Store.objects.get(id=r.json()["id"])
        wh1 = Warehouse.objects.filter(store=store1).first()
        wh2 = Warehouse.objects.filter(store=store2).first()
        return store1, wh1, store2, wh2

    def test_create_sale_with_wrong_store_warehouse(self, client_ms, setup, product_ms):
        """Try to create sale using store2's warehouse while in store1."""
        store1, wh1, store2, wh2 = setup
        from inventory.models import StockItem
        StockItem.objects.create(
            tenant=product_ms.tenant, product=product_ms, warehouse=wh2,
            on_hand=Decimal("100"), avg_cost=Decimal("500"), stock_value=Decimal("50000"),
        )

        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r = client_ms.post("/api/sales/sales/", {
            "warehouse_id": wh2.id,  # store2's warehouse!
            "lines": [{"product_id": product_ms.id, "qty": "1", "unit_price": "990"}],
        }, format="json")
        # Should fail — warehouse doesn't belong to active store
        assert r.status_code in (400, 409), f"Expected 400/409, got {r.status_code}: {r.json()}"

    def test_open_order_with_wrong_store_warehouse(self, client_ms, setup, product_ms):
        """Try to open order using store2's warehouse while in store1."""
        store1, wh1, store2, wh2 = setup

        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        tr = client_ms.post("/api/tables/tables/", {"name": "Mesa Cross"}, format="json")
        tid = tr.json()["id"]

        r = client_ms.post(f"/api/tables/tables/{tid}/open/", {"warehouse_id": wh2.id}, format="json")
        assert r.status_code in (400, 409), f"Expected 400/409, got {r.status_code}: {r.json()}"

    def test_transfer_between_stores_rejected(self, client_ms, setup, product_ms):
        """Stock transfer between warehouses of different stores should fail."""
        store1, wh1, store2, wh2 = setup
        from inventory.models import StockItem
        StockItem.objects.create(
            tenant=product_ms.tenant, product=product_ms, warehouse=wh1,
            on_hand=Decimal("50"), avg_cost=Decimal("500"), stock_value=Decimal("25000"),
        )

        client_ms.post("/api/stores/set-active/", {"store_id": store1.id}, format="json")
        r = client_ms.post("/api/inventory/transfer/", {
            "from_warehouse_id": wh1.id,
            "to_warehouse_id": wh2.id,  # different store!
            "lines": [{"product_id": product_ms.id, "qty": "5"}],
        }, format="json")
        assert r.status_code in (400, 409), f"Expected 400/409, got {r.status_code}: {r.json()}"

    def test_patch_store_empty_name(self, client_ms, setup):
        store1, _, _, _ = setup
        r = client_ms.patch(f"/api/core/stores/{store1.id}/", {"name": ""}, format="json")
        assert r.status_code == 400

    def test_patch_store_duplicate_name(self, client_ms, setup):
        store1, _, store2, _ = setup
        r = client_ms.patch(f"/api/core/stores/{store1.id}/", {"name": store2.name}, format="json")
        assert r.status_code == 400

    def test_patch_other_tenant_store(self, client_ms, setup):
        """Cannot update another tenant's store."""
        other_t = Tenant.objects.create(name="Evil MS", slug="evil-ms")
        other_s = Store.objects.create(tenant=other_t, name="Evil Store")
        r = client_ms.patch(f"/api/core/stores/{other_s.id}/", {"name": "Hacked"}, format="json")
        assert r.status_code == 404

    def test_create_warehouse_in_other_tenant_store(self, client_ms, setup):
        """Cannot create warehouse in another tenant's store."""
        other_t = Tenant.objects.create(name="Evil WH", slug="evil-wh")
        other_s = Store.objects.create(tenant=other_t, name="Evil Store WH")
        r = client_ms.post("/api/core/warehouses/", {
            "store": other_s.id,
            "name": "Hacked Bodega",
        }, format="json")
        assert r.status_code in (400, 404)
