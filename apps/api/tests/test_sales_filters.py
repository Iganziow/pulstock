"""
Tests para los filtros nuevos de SaleList (15/05/26).

Mario reportó que en Pulstock no podía filtrar las ventas como en Fudo
para encontrar diferencias en el cuadre de caja. Estos tests garantizan
que cada filtro nuevo funciona y NO devuelve falsos positivos.
"""
from decimal import Decimal

import pytest

from core.models import User
from inventory.models import StockItem
from sales.models import Sale, SalePayment


def _setup_stock(tenant, warehouse, product, qty=100):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={"on_hand": Decimal(qty), "avg_cost": Decimal("100")},
    )
    if si.on_hand < qty:
        si.on_hand = Decimal(qty)
        si.save()


def _create_sale(api_client, warehouse, product, payments, qty=1, tip=0):
    """Helper: crear venta vía endpoint público (no factory directo)."""
    body = {
        "warehouse_id": warehouse.id,
        "lines": [{"product_id": product.id, "qty": qty, "unit_price": "1000"}],
        "payments": payments,
    }
    if tip:
        body["tip"] = str(tip)
    r = api_client.post("/api/sales/sales/", body, format="json")
    assert r.status_code == 201, f"Sale create failed: {r.status_code} {r.content}"
    return r.json()


@pytest.fixture
def cashier_user(db, tenant, store):
    """Segundo usuario (CASHIER) para tests de filtro de cajero."""
    u, _ = User.objects.get_or_create(
        username="nadia_test",
        defaults={
            "tenant": tenant,
            "active_store": store,
            "role": User.Role.CASHIER,
            "email": "nadia@test.cl",
        },
    )
    u.tenant = tenant
    u.active_store = store
    u.set_password("testpass123")
    u.save()
    return u


@pytest.fixture
def cashier_client(cashier_user):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=cashier_user)
    return c


# ─── FILTRO: cashier ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_filter_by_cashier_id(api_client, cashier_client, owner, cashier_user, tenant, warehouse, product):
    """Filtrar por ?cashier=ID devuelve SOLO ventas creadas por ese cajero."""
    _setup_stock(tenant, warehouse, product)
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    _create_sale(cashier_client, warehouse, product, [{"method": "cash", "amount": "1000"}])

    # Sin filtro: 3 ventas
    r = api_client.get("/api/sales/sales/list/")
    assert r.status_code == 200
    assert r.json()["count"] == 3

    # Filtrar por owner: 2
    r = api_client.get(f"/api/sales/sales/list/?cashier={owner.id}")
    assert r.status_code == 200
    assert r.json()["count"] == 2

    # Filtrar por cashier_user: 1
    r = api_client.get(f"/api/sales/sales/list/?cashier={cashier_user.id}")
    assert r.status_code == 200
    assert r.json()["count"] == 1


@pytest.mark.django_db
def test_filter_by_cashier_username(api_client, cashier_client, cashier_user, tenant, warehouse, product):
    """Filtrar por ?cashier=username (string) también funciona."""
    _setup_stock(tenant, warehouse, product)
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    _create_sale(cashier_client, warehouse, product, [{"method": "cash", "amount": "1000"}])

    r = api_client.get("/api/sales/sales/list/?cashier=nadia")
    assert r.status_code == 200
    assert r.json()["count"] == 1


# ─── FILTRO: payment_method ─────────────────────────────────────────────


@pytest.mark.django_db
def test_filter_by_payment_method_cash(api_client, tenant, warehouse, product):
    """?payment_method=cash devuelve SOLO ventas con al menos un SalePayment cash."""
    _setup_stock(tenant, warehouse, product)
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    _create_sale(api_client, warehouse, product, [{"method": "debit", "amount": "1000"}])
    _create_sale(api_client, warehouse, product, [{"method": "card", "amount": "1000"}])

    # Cash: 1 venta
    r = api_client.get("/api/sales/sales/list/?payment_method=cash")
    assert r.status_code == 200
    assert r.json()["count"] == 1

    # Debit: 1 venta
    r = api_client.get("/api/sales/sales/list/?payment_method=debit")
    assert r.json()["count"] == 1

    # Transfer: 0 ventas
    r = api_client.get("/api/sales/sales/list/?payment_method=transfer")
    assert r.json()["count"] == 0


@pytest.mark.django_db
def test_filter_by_payment_method_with_split(api_client, tenant, warehouse, product):
    """Si la venta tiene split (cash+card), aparece en ambos filtros."""
    _setup_stock(tenant, warehouse, product)
    _create_sale(api_client, warehouse, product, [
        {"method": "cash", "amount": "500"},
        {"method": "card", "amount": "500"},
    ])

    r = api_client.get("/api/sales/sales/list/?payment_method=cash")
    assert r.json()["count"] == 1

    r = api_client.get("/api/sales/sales/list/?payment_method=card")
    assert r.json()["count"] == 1

    r = api_client.get("/api/sales/sales/list/?payment_method=debit")
    assert r.json()["count"] == 0


# ─── FILTRO: has_tip ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_filter_has_tip(api_client, tenant, warehouse, product):
    """?has_tip=true devuelve solo ventas con tip > 0."""
    _setup_stock(tenant, warehouse, product)
    # Venta sin propina
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    # Venta con propina (cliente paga subtotal + tip)
    _create_sale(api_client, warehouse, product,
                 [{"method": "cash", "amount": "1100"}], tip=100)

    r = api_client.get("/api/sales/sales/list/?has_tip=true")
    assert r.status_code == 200
    assert r.json()["count"] == 1

    r = api_client.get("/api/sales/sales/list/?has_tip=false")
    assert r.json()["count"] == 1

    # Sin filtro: 2
    r = api_client.get("/api/sales/sales/list/")
    assert r.json()["count"] == 2


# ─── FILTRO: combinados ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_filters_combine_AND(api_client, cashier_client, owner, tenant, warehouse, product):
    """Múltiples filtros se combinan con AND. Solo coinciden las que cumplen TODOS."""
    _setup_stock(tenant, warehouse, product)
    # Owner cash sin tip
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])
    # Owner cash con tip
    _create_sale(api_client, warehouse, product,
                 [{"method": "cash", "amount": "1100"}], tip=100)
    # Owner debit con tip
    _create_sale(api_client, warehouse, product,
                 [{"method": "debit", "amount": "1100"}], tip=100)
    # Cashier cash con tip
    _create_sale(cashier_client, warehouse, product,
                 [{"method": "cash", "amount": "1100"}], tip=100)

    # owner + cash + tip → 1
    r = api_client.get(
        f"/api/sales/sales/list/?cashier={owner.id}&payment_method=cash&has_tip=true"
    )
    assert r.status_code == 200
    assert r.json()["count"] == 1


# ─── FILTRO: invalido (no rompe) ─────────────────────────────────────────


@pytest.mark.django_db
def test_filter_invalid_does_not_crash(api_client, tenant, warehouse, product):
    """Params inválidos NO rompen — devuelven 200 (vacío o ignorados)."""
    _setup_stock(tenant, warehouse, product)
    _create_sale(api_client, warehouse, product, [{"method": "cash", "amount": "1000"}])

    # IDs no numéricos → no matchea (cashier es texto, busca por username)
    r = api_client.get("/api/sales/sales/list/?cashier=999999")
    assert r.status_code == 200
    assert r.json()["count"] == 0  # ID inexistente

    # Tabla inválida → ignorado (no isdigit), devuelve todas
    r = api_client.get("/api/sales/sales/list/?table=abc")
    assert r.status_code == 200
    assert r.json()["count"] == 1

    # Payment method inexistente → 0
    r = api_client.get("/api/sales/sales/list/?payment_method=inexistente")
    assert r.json()["count"] == 0
