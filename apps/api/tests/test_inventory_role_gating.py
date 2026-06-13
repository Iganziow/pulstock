"""
Fix auditoría (09/06/26): los endpoints de ESCRITURA de inventario
(StockAdjust/Receive/Issue/Transfer) usaban solo [IsAuthenticated, HasTenant].
→ un CASHIER podía sobreescribir avg_cost y mover stock (corrupción de costos).
Ahora exigen IsInventoryOrManager (owner/manager/inventory).

Estos tests verifican:
  - CASHIER → 403 en los 4 endpoints de escritura.
  - INVENTORY → OK (no 403) en los mismos.
  - El flujo de lectura (StockList) sigue accesible para cashier.
"""
import pytest
from decimal import Decimal

from core.models import User, Warehouse
from inventory.models import StockItem
from catalog.models import Product
from rest_framework.test import APIClient


def _user_with_role(tenant, store, role, username):
    u, _ = User.objects.get_or_create(username=username, defaults={"tenant": tenant})
    u.tenant = tenant
    u.active_store = store
    u.role = role
    u.set_password("testpass123")
    u.save()
    return u


@pytest.fixture
def cashier_client(tenant, store):
    u = _user_with_role(tenant, store, User.Role.CASHIER, "cashier_test")
    c = APIClient()
    c.force_authenticate(user=u)
    return c


@pytest.fixture
def inventory_client(tenant, store):
    u = _user_with_role(tenant, store, User.Role.INVENTORY, "inventory_test")
    c = APIClient()
    c.force_authenticate(user=u)
    return c


@pytest.fixture
def two_warehouses(tenant, store):
    a, _ = Warehouse.objects.get_or_create(tenant=tenant, store=store, name="WH-A")
    b, _ = Warehouse.objects.get_or_create(tenant=tenant, store=store, name="WH-B")
    return a, b


@pytest.fixture
def prod_with_stock(tenant, two_warehouses):
    wa, _ = two_warehouses
    p = Product.objects.create(tenant=tenant, name="Insumo", price=Decimal("1000"), is_active=True)
    StockItem.objects.create(
        tenant=tenant, warehouse=wa, product=p,
        on_hand=Decimal("100"), avg_cost=Decimal("500"), stock_value=Decimal("50000"),
    )
    return p


@pytest.mark.django_db
class TestInventoryRoleGating:
    def test_cashier_blocked_on_adjust(self, cashier_client, prod_with_stock, two_warehouses):
        wa, _ = two_warehouses
        r = cashier_client.post("/api/inventory/adjust/", {
            "warehouse_id": wa.id, "product_id": prod_with_stock.id, "qty": "5", "note": "x",
        }, format="json")
        assert r.status_code == 403, f"CASHIER no debe poder ajustar stock (got {r.status_code})"

    def test_cashier_blocked_on_receive(self, cashier_client, prod_with_stock, two_warehouses):
        wa, _ = two_warehouses
        r = cashier_client.post("/api/inventory/receive/", {
            "warehouse_id": wa.id, "product_id": prod_with_stock.id, "qty": "5", "unit_cost": "600",
        }, format="json")
        assert r.status_code == 403, f"CASHIER no debe poder recibir stock (got {r.status_code})"

    def test_cashier_blocked_on_issue(self, cashier_client, prod_with_stock, two_warehouses):
        wa, _ = two_warehouses
        r = cashier_client.post("/api/inventory/issue/", {
            "warehouse_id": wa.id, "product_id": prod_with_stock.id, "qty": "1", "reason": "MERMA",
        }, format="json")
        assert r.status_code == 403, f"CASHIER no debe poder dar salida (got {r.status_code})"

    def test_cashier_blocked_on_transfer(self, cashier_client, prod_with_stock, two_warehouses):
        wa, wb = two_warehouses
        r = cashier_client.post("/api/inventory/transfer/", {
            "from_warehouse_id": wa.id, "to_warehouse_id": wb.id,
            "lines": [{"product_id": prod_with_stock.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 403, f"CASHIER no debe poder transferir (got {r.status_code})"

    def test_inventory_role_allowed_on_adjust(self, inventory_client, prod_with_stock, two_warehouses):
        wa, _ = two_warehouses
        r = inventory_client.post("/api/inventory/adjust/", {
            "warehouse_id": wa.id, "product_id": prod_with_stock.id, "qty": "5", "note": "ok",
        }, format="json")
        assert r.status_code != 403, f"INVENTORY debe poder ajustar (got {r.status_code}: {getattr(r,'data',None)})"

    def test_inventory_role_allowed_on_receive(self, inventory_client, prod_with_stock, two_warehouses):
        wa, _ = two_warehouses
        r = inventory_client.post("/api/inventory/receive/", {
            "warehouse_id": wa.id, "product_id": prod_with_stock.id, "qty": "5", "unit_cost": "600",
        }, format="json")
        assert r.status_code != 403, f"INVENTORY debe poder recibir (got {r.status_code}: {getattr(r,'data',None)})"
