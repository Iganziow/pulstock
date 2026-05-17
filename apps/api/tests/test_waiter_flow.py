"""
tests/test_waiter_flow.py — Tests del sistema de Garzón (Mario 16/05/26).

Verifica el flujo Fudo-style:
  1. Abrir mesa con waiter_id → OpenOrder.waiter queda asignado
  2. Pedido para llevar con waiter_id → idem
  3. Endpoint /core/staff/ lista usuarios activos del tenant
  4. Filtro ?waiter= en /sales/sales/list/ funciona
  5. Filtro ?waiter= en /sales/tips-list/ funciona
  6. Response de sales/tips incluye waiter_id + waiter_name
  7. Si no se manda waiter_id → OpenOrder.waiter queda null (compat)
  8. Si waiter_id apunta a usuario de OTRO tenant → 400 (no info leak)
"""
import pytest
from decimal import Decimal

from core.models import User
from tables.models import Table, OpenOrder
from sales.models import Sale, SalePayment, SaleTip
from inventory.models import StockItem


URL_STAFF = "/api/core/staff/"
URL_TABLES = "/api/tables/tables/"
URL_COUNTER = "/api/tables/counter-order/"
URL_SALES_LIST = "/api/sales/sales/list/"
URL_TIPS_LIST = "/api/sales/tips-list/"


def _create_table(api_client, name="Mesa 1"):
    r = api_client.post(URL_TABLES, {"name": name, "capacity": 4}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _make_waiter(tenant, store, username="garzon1", first_name="Pedro", last_name="Garzón"):
    u = User.objects.create_user(
        username=username, password="pass123",
        first_name=first_name, last_name=last_name,
    )
    u.tenant = tenant
    u.active_store = store
    u.role = User.Role.CASHIER
    u.save(update_fields=["tenant", "active_store", "role"])
    return u


# ────────────────────────────────────────────────────────────────────────────
# /core/staff/
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_staff_endpoint_lists_active_users(api_client, tenant, store):
    """GET /core/staff/ devuelve usuarios activos del tenant (cualquier rol)."""
    waiter = _make_waiter(tenant, store, "pedro_g", "Pedro", "Garzón")
    # Usuario inactivo NO debe aparecer
    inactive = _make_waiter(tenant, store, "exgarzon", "Ex", "Garzón")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    resp = api_client.get(URL_STAFF)
    assert resp.status_code == 200
    data = resp.json()
    usernames = {u["username"] for u in data}
    assert "pedro_g" in usernames
    assert "exgarzon" not in usernames  # inactivos filtrados
    # owner_test (el cliente autenticado) sí debe aparecer
    assert "owner_test" in usernames

    pedro = next(u for u in data if u["username"] == "pedro_g")
    assert pedro["first_name"] == "Pedro"
    assert pedro["display_name"] == "Pedro Garzón"


@pytest.mark.django_db
def test_staff_endpoint_does_not_leak_other_tenants(api_client, tenant, store):
    """Usuarios de otros tenants NO deben aparecer."""
    other_tenant = type(tenant).objects.create(name="Other", slug="other")
    other_store = type(store).objects.create(tenant=other_tenant, name="Other Store")
    intruso = User.objects.create_user(username="intruso", password="x")
    intruso.tenant = other_tenant
    intruso.active_store = other_store
    intruso.save(update_fields=["tenant", "active_store"])

    resp = api_client.get(URL_STAFF)
    data = resp.json()
    assert all(u["username"] != "intruso" for u in data)


# ────────────────────────────────────────────────────────────────────────────
# Abrir mesa con waiter
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_open_table_with_waiter_assigns(api_client, tenant, store, warehouse):
    """POST /tables/{id}/open/ con waiter_id deja waiter asignado."""
    table = _create_table(api_client)
    waiter = _make_waiter(tenant, store)

    resp = api_client.post(
        f"/api/tables/tables/{table['id']}/open/",
        {"waiter_id": waiter.id, "warehouse_id": warehouse.id},
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    data = resp.json()
    assert data["waiter_id"] == waiter.id
    assert data["waiter"]["id"] == waiter.id
    # En el DB
    order = OpenOrder.objects.get(id=data["id"])
    assert order.waiter_id == waiter.id


@pytest.mark.django_db
def test_open_table_without_waiter_leaves_null(api_client, tenant, store, warehouse):
    """Compat retro: sin waiter_id, OpenOrder.waiter queda null."""
    table = _create_table(api_client)
    resp = api_client.post(
        f"/api/tables/tables/{table['id']}/open/",
        {"warehouse_id": warehouse.id},
        format="json",
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["waiter_id"] is None
    assert data["waiter"] is None


@pytest.mark.django_db
def test_open_table_rejects_waiter_from_other_tenant(api_client, tenant, store, warehouse):
    """Si waiter_id pertenece a OTRO tenant → 400 (no leak ni asignación)."""
    table = _create_table(api_client)
    other_tenant = type(tenant).objects.create(name="Other2", slug="other2")
    other_store = type(store).objects.create(tenant=other_tenant, name="Other Store 2")
    intruso = User.objects.create_user(username="intruso2", password="x")
    intruso.tenant = other_tenant
    intruso.active_store = other_store
    intruso.save(update_fields=["tenant", "active_store"])

    resp = api_client.post(
        f"/api/tables/tables/{table['id']}/open/",
        {"waiter_id": intruso.id, "warehouse_id": warehouse.id},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_open_table_rejects_inactive_waiter(api_client, tenant, store, warehouse):
    """Garzón inactivo → 400 (no se puede asignar)."""
    table = _create_table(api_client)
    waiter = _make_waiter(tenant, store, "exgarzon3")
    waiter.is_active = False
    waiter.save(update_fields=["is_active"])

    resp = api_client.post(
        f"/api/tables/tables/{table['id']}/open/",
        {"waiter_id": waiter.id, "warehouse_id": warehouse.id},
        format="json",
    )
    assert resp.status_code == 400


# ────────────────────────────────────────────────────────────────────────────
# Counter order con waiter
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_counter_order_with_waiter_assigns(api_client, tenant, store, warehouse):
    """POST /tables/counter-order/ con waiter_id queda asignado."""
    waiter = _make_waiter(tenant, store, "garzon_counter")
    resp = api_client.post(
        URL_COUNTER,
        {"customer_name": "Juan", "waiter_id": waiter.id, "warehouse_id": warehouse.id},
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    data = resp.json()
    assert data["waiter_id"] == waiter.id


# ────────────────────────────────────────────────────────────────────────────
# Filtro ?waiter= en sales list
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sales_list_filter_by_waiter_id(api_client, tenant, store, warehouse, owner):
    """GET /sales/sales/list/?waiter=N filtra ventas por waiter del OpenOrder."""
    waiter_a = _make_waiter(tenant, store, "garzon_a", "Ana", "A")
    waiter_b = _make_waiter(tenant, store, "garzon_b", "Beto", "B")
    table = Table.objects.create(tenant=tenant, store=store, name="T1")

    # Order atendida por A
    order_a = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table, opened_by=owner, waiter=waiter_a, status="CLOSED",
    )
    sale_a = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
        status="COMPLETED", open_order=order_a,
    )

    # Order atendida por B (otra mesa para no chocar con unique constraint)
    table2 = Table.objects.create(tenant=tenant, store=store, name="T2")
    order_b = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table2, opened_by=owner, waiter=waiter_b, status="CLOSED",
    )
    sale_b = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal("2000"), total=Decimal("2000"),
        status="COMPLETED", open_order=order_b,
    )

    # Sin filtro: debe traer ambas
    resp = api_client.get(URL_SALES_LIST)
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()["results"]}
    assert sale_a.id in ids and sale_b.id in ids

    # Con ?waiter=A: solo sale_a
    resp = api_client.get(f"{URL_SALES_LIST}?waiter={waiter_a.id}")
    assert resp.status_code == 200
    rows = resp.json()["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == sale_a.id
    assert rows[0]["waiter_id"] == waiter_a.id
    assert rows[0]["waiter_name"] == "Ana A"


@pytest.mark.django_db
def test_sales_list_filter_by_waiter_username(api_client, tenant, store, warehouse, owner):
    """?waiter=garzon_x filtra por username (no solo id)."""
    waiter = _make_waiter(tenant, store, "pedro_search", "Pedro", "S")
    table = Table.objects.create(tenant=tenant, store=store, name="T-search")
    order = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table, opened_by=owner, waiter=waiter, status="CLOSED",
    )
    Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal("500"), total=Decimal("500"),
        status="COMPLETED", open_order=order,
    )
    resp = api_client.get(f"{URL_SALES_LIST}?waiter=pedro_search")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


# ────────────────────────────────────────────────────────────────────────────
# Filtro ?waiter= en tips-list
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_tips_list_filter_by_waiter(api_client, tenant, store, warehouse, owner):
    """GET /sales/tips-list/?waiter=N filtra propinas por garzon."""
    waiter_a = _make_waiter(tenant, store, "garzon_tips_a")
    waiter_b = _make_waiter(tenant, store, "garzon_tips_b")

    t1 = Table.objects.create(tenant=tenant, store=store, name="TipT1")
    o1 = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=t1, opened_by=owner, waiter=waiter_a, status="CLOSED",
    )
    sale_a = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal("3000"), total=Decimal("3000"),
        tip=Decimal("500"), status="COMPLETED", open_order=o1,
    )
    SaleTip.objects.create(sale=sale_a, tenant=tenant, method="cash", amount=Decimal("500"))

    t2 = Table.objects.create(tenant=tenant, store=store, name="TipT2")
    o2 = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=t2, opened_by=owner, waiter=waiter_b, status="CLOSED",
    )
    sale_b = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal("2000"), total=Decimal("2000"),
        tip=Decimal("300"), status="COMPLETED", open_order=o2,
    )
    SaleTip.objects.create(sale=sale_b, tenant=tenant, method="cash", amount=Decimal("300"))

    # Sin filtro: 2 propinas
    resp = api_client.get(URL_TIPS_LIST)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    # Filtrado por waiter_a: solo 1
    resp = api_client.get(f"{URL_TIPS_LIST}?waiter={waiter_a.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["sale_id"] == sale_a.id
    assert data["results"][0]["waiter_id"] == waiter_a.id
    assert data["results"][0]["tip_amount"] == "500.00"
    assert data["totals"]["total_tips"] == "500"
