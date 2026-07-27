"""
tests/test_sale_edit_waiter.py — Editar el garzón de una venta cerrada.

Feature (Mario): corregir el garzón de una venta COMPLETED (mesa o mostrador),
solo admin. Sale.waiter es la fuente de verdad; reportes y propinas por garzón
lo siguen automáticamente. Verifica que NADA derivado se rompa:

  1. Denormalización: cobrar una mesa copia open_order.waiter → sale.waiter.
  2. Fallback: venta con open_order.waiter pero sin sale.waiter (legacy) se
     muestra/filtra igual (garzón efectivo).
  3. Editar garzón de mesa → actualiza TODAS las ventas de la comanda + la mesa.
  4. Editar garzón de mostrador (sin open_order) → solo esa venta.
  5. La propina sigue al garzón editado (tips-list re-atribuye).
  6. El filtro ?waiter= de la lista de ventas sigue al garzón editado.
  7. Permiso: cajero → 403; owner/manager → 200.
  8. Validación: null limpia; otro tenant → 400; falta waiter_id → 400.
  9. Sin acoplamiento: editar pagos y anular siguen funcionando post-edición.
"""
import pytest
from decimal import Decimal

from rest_framework.test import APIClient

from core.models import User
from tables.models import Table, OpenOrder
from sales.models import Sale, SalePayment, SaleTip
from inventory.models import StockItem


URL_SALES_LIST = "/api/sales/sales/list/"
URL_TIPS_LIST = "/api/sales/tips-list/"


def _waiter_url(pk):
    return f"/api/sales/sales/{pk}/waiter/"


def _make_user(tenant, store, username, role=User.Role.CASHIER, first="Ana", last="A"):
    u = User.objects.create_user(username=username, password="pass123",
                                 first_name=first, last_name=last)
    u.tenant = tenant
    u.active_store = store
    u.role = role
    u.save(update_fields=["tenant", "active_store", "role"])
    return u


def _seed_stock(tenant, warehouse, product, qty="100"):
    StockItem.objects.update_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={"on_hand": Decimal(qty), "avg_cost": Decimal("100")},
    )


def _open(api_client, table_id, warehouse_id, waiter_id=None):
    body = {"warehouse_id": warehouse_id}
    if waiter_id:
        body["waiter_id"] = waiter_id
    r = api_client.post(f"/api/tables/tables/{table_id}/open/", body, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def _add_lines(api_client, order_id, lines):
    r = api_client.post(f"/api/tables/orders/{order_id}/add-lines/",
                        {"lines": lines}, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def _checkout(api_client, order_id, payload):
    return api_client.post(f"/api/tables/orders/{order_id}/checkout/", payload, format="json")


def _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, waiter, tip="800"):
    """Cobra una mesa completa con garzón + propina cash. Devuelve la Sale."""
    _seed_stock(tenant, warehouse, product)
    table = Table.objects.create(tenant=tenant, store=store, name=f"T-{waiter.username}")
    order = _open(api_client, table.id, warehouse.id, waiter_id=waiter.id)
    _add_lines(api_client, order["id"], [{"product_id": product.id, "qty": 2}])
    subtotal = int(product.price) * 2
    payload = {"mode": "all", "payments": [{"method": "cash", "amount": str(subtotal)}]}
    if tip and tip != "0":
        payload["tip"] = tip
        payload["tips"] = [{"method": "cash", "amount": tip}]
    resp = _checkout(api_client, order["id"], payload)
    assert resp.status_code in (200, 201), resp.content
    sale = Sale.objects.filter(open_order_id=order["id"], status="COMPLETED").first()
    assert sale is not None
    return sale, order["id"]


# ──────────────────────────────────────────────────────────────────────────
# 1. Denormalización al cobrar
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_checkout_denormaliza_waiter_en_la_venta(api_client, tenant, store, warehouse, product):
    garzon = _make_user(tenant, store, "garzon_denorm")
    sale, _ = _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, garzon)
    sale.refresh_from_db()
    assert sale.waiter_id == garzon.id  # copiado desde open_order.waiter


# ──────────────────────────────────────────────────────────────────────────
# 2. Fallback: venta con mesa pero sin sale.waiter (legacy) sigue funcionando
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_fallback_open_order_waiter_cuando_sale_waiter_null(api_client, tenant, store, warehouse, owner):
    garzon = _make_user(tenant, store, "garzon_legacy")
    table = Table.objects.create(tenant=tenant, store=store, name="T-legacy")
    order = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table, opened_by=owner, waiter=garzon, status="CLOSED",
    )
    sale = Sale.objects.create(  # sin sale.waiter (legacy)
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        subtotal=Decimal("500"), total=Decimal("500"), status="COMPLETED",
        open_order=order,
    )
    # El display usa el garzón efectivo (fallback a la mesa)
    r = api_client.get(f"{URL_SALES_LIST}?waiter={garzon.id}")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["results"]}
    assert sale.id in ids


# ──────────────────────────────────────────────────────────────────────────
# 3. Editar garzón de una mesa → todas las ventas de la comanda + la mesa
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_editar_garzon_mesa_actualiza_todas_las_ventas_de_la_comanda(
    api_client, tenant, store, warehouse, owner
):
    gar_a = _make_user(tenant, store, "gar_a_multi")
    gar_b = _make_user(tenant, store, "gar_b_multi")
    table = Table.objects.create(tenant=tenant, store=store, name="T-multi")
    order = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        table=table, opened_by=owner, waiter=gar_a, status="CLOSED",
    )
    # Dos ventas (cobros parciales) de la MISMA comanda, ambas con garzón A
    s1 = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                             created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                             status="COMPLETED", open_order=order, waiter=gar_a)
    s2 = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                             created_by=owner, subtotal=Decimal("500"), total=Decimal("500"),
                             status="COMPLETED", open_order=order, waiter=gar_a)

    resp = api_client.patch(_waiter_url(s1.id), {"waiter_id": gar_b.id}, format="json")
    assert resp.status_code == 200, resp.content
    assert set(resp.json()["affected_sale_ids"]) == {s1.id, s2.id}

    s1.refresh_from_db(); s2.refresh_from_db(); order.refresh_from_db()
    assert s1.waiter_id == gar_b.id
    assert s2.waiter_id == gar_b.id  # la otra venta de la mesa también
    assert order.waiter_id == gar_b.id  # y la mesa queda consistente


# ──────────────────────────────────────────────────────────────────────────
# 4. Editar garzón de una venta de mostrador (sin mesa)
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_editar_garzon_mostrador_solo_esa_venta(api_client, tenant, store, warehouse, owner):
    garzon = _make_user(tenant, store, "gar_mostrador")
    sale = Sale.objects.create(  # mostrador: sin open_order
        tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
        subtotal=Decimal("2000"), total=Decimal("2000"), status="COMPLETED",
    )
    assert sale.waiter_id is None
    resp = api_client.patch(_waiter_url(sale.id), {"waiter_id": garzon.id}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["affected_sale_ids"] == [sale.id]
    sale.refresh_from_db()
    assert sale.waiter_id == garzon.id


# ──────────────────────────────────────────────────────────────────────────
# 5. La PROPINA sigue al garzón editado (lo crítico)
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_propina_sigue_al_garzon_editado(api_client, tenant, store, warehouse, product):
    gar_a = _make_user(tenant, store, "gar_tip_a")
    gar_b = _make_user(tenant, store, "gar_tip_b")
    sale, _ = _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, gar_a, tip="800")

    # Antes: la propina se atribuye a A
    r = api_client.get(f"{URL_TIPS_LIST}?waiter={gar_a.id}")
    assert r.json()["count"] == 1
    r = api_client.get(f"{URL_TIPS_LIST}?waiter={gar_b.id}")
    assert r.json()["count"] == 0

    # Corregir el garzón a B
    resp = api_client.patch(_waiter_url(sale.id), {"waiter_id": gar_b.id}, format="json")
    assert resp.status_code == 200, resp.content

    # Ahora: la propina se atribuye a B, ya NO a A
    r = api_client.get(f"{URL_TIPS_LIST}?waiter={gar_b.id}")
    assert r.json()["count"] == 1
    assert r.json()["results"][0]["waiter_id"] == gar_b.id
    r = api_client.get(f"{URL_TIPS_LIST}?waiter={gar_a.id}")
    assert r.json()["count"] == 0


# ──────────────────────────────────────────────────────────────────────────
# 6. El filtro de la lista de ventas sigue al garzón editado
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_filtro_lista_ventas_sigue_al_garzon_editado(api_client, tenant, store, warehouse, product):
    gar_a = _make_user(tenant, store, "gar_list_a")
    gar_b = _make_user(tenant, store, "gar_list_b")
    sale, _ = _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, gar_a)

    api_client.patch(_waiter_url(sale.id), {"waiter_id": gar_b.id}, format="json")

    r = api_client.get(f"{URL_SALES_LIST}?waiter={gar_b.id}")
    assert sale.id in {s["id"] for s in r.json()["results"]}
    r = api_client.get(f"{URL_SALES_LIST}?waiter={gar_a.id}")
    assert sale.id not in {s["id"] for s in r.json()["results"]}


# ──────────────────────────────────────────────────────────────────────────
# 7. Permisos
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_cajero_no_puede_editar_garzon(api_client, tenant, store, warehouse, owner):
    garzon = _make_user(tenant, store, "gar_perm")
    cajero = _make_user(tenant, store, "cajero_perm", role=User.Role.CASHIER)
    sale = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                               status="COMPLETED")
    cli = APIClient()
    cli.force_authenticate(user=cajero)
    resp = cli.patch(_waiter_url(sale.id), {"waiter_id": garzon.id}, format="json")
    assert resp.status_code == 403
    sale.refresh_from_db()
    assert sale.waiter_id is None  # no cambió


# ──────────────────────────────────────────────────────────────────────────
# 8. Validación
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_waiter_null_limpia_el_garzon(api_client, tenant, store, warehouse, owner):
    garzon = _make_user(tenant, store, "gar_clear")
    sale = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                               status="COMPLETED", waiter=garzon)
    resp = api_client.patch(_waiter_url(sale.id), {"waiter_id": None}, format="json")
    assert resp.status_code == 200, resp.content
    sale.refresh_from_db()
    assert sale.waiter_id is None


@pytest.mark.django_db
def test_waiter_de_otro_tenant_rechazado(api_client, tenant, store, warehouse, owner):
    other_tenant = type(tenant).objects.create(name="Otro", slug="otro")
    other_store = type(store).objects.create(tenant=other_tenant, name="Otra")
    intruso = _make_user(other_tenant, other_store, "intruso_waiter")
    sale = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                               status="COMPLETED")
    resp = api_client.patch(_waiter_url(sale.id), {"waiter_id": intruso.id}, format="json")
    assert resp.status_code == 400
    sale.refresh_from_db()
    assert sale.waiter_id is None


@pytest.mark.django_db
def test_falta_waiter_id_es_400(api_client, tenant, store, warehouse, owner):
    sale = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                               status="COMPLETED")
    resp = api_client.patch(_waiter_url(sale.id), {}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_no_se_puede_editar_garzon_de_venta_anulada(api_client, tenant, store, warehouse, owner):
    garzon = _make_user(tenant, store, "gar_void")
    sale = Sale.objects.create(tenant=tenant, store=store, warehouse=warehouse,
                               created_by=owner, subtotal=Decimal("1000"), total=Decimal("1000"),
                               status="VOID")
    resp = api_client.patch(_waiter_url(sale.id), {"waiter_id": garzon.id}, format="json")
    assert resp.status_code == 400


# ──────────────────────────────────────────────────────────────────────────
# 9. Sin acoplamiento: editar pagos y anular siguen funcionando post-edición
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_editar_pagos_funciona_tras_editar_garzon(api_client, tenant, store, warehouse, product):
    gar_a = _make_user(tenant, store, "gar_pay_a")
    gar_b = _make_user(tenant, store, "gar_pay_b")
    sale, _ = _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, gar_a, tip="0")

    # Editar garzón, luego editar pagos: ambos deben funcionar
    assert api_client.patch(_waiter_url(sale.id), {"waiter_id": gar_b.id}, format="json").status_code == 200
    total = str(sale.total)
    resp = api_client.patch(f"/api/sales/sales/{sale.id}/payments/",
                            {"payments": [{"method": "debit", "amount": total}]}, format="json")
    assert resp.status_code == 200, resp.content
    sale.refresh_from_db()
    assert sale.waiter_id == gar_b.id  # el garzón editado se mantiene


@pytest.mark.django_db
def test_anular_venta_funciona_tras_editar_garzon(api_client, tenant, store, warehouse, product):
    gar_a = _make_user(tenant, store, "gar_void_a")
    gar_b = _make_user(tenant, store, "gar_void_b")
    sale, _ = _mesa_sale_with_tip(api_client, tenant, store, warehouse, product, gar_a, tip="500")

    assert api_client.patch(_waiter_url(sale.id), {"waiter_id": gar_b.id}, format="json").status_code == 200
    resp = api_client.post(f"/api/sales/sales/{sale.id}/void/", {"reason": "test"}, format="json")
    assert resp.status_code == 200, resp.content
    sale.refresh_from_db()
    assert sale.status == "VOID"
    # Propinas limpiadas (no doble conteo por garzón)
    assert not SaleTip.objects.filter(sale=sale).exists()
