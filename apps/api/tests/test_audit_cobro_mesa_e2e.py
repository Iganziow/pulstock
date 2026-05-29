"""
AUDITORÍA E2E del cobro de mesas (Mario 28/05/26).

Recorre el flujo COMPLETO vía endpoints reales (no Sale.objects.create):
  abrir mesa con garzón → agregar líneas → cobrar (/checkout/) con el
  payload EXACTO que genera el modal rediseñado (buildCheckoutSplit) →
  verificar SalePayment + SaleTip + cierre de mesa + atribución por garzón
  en /tips-list/ + cuadre de caja.

Cubre los casos que el usuario pidió auditar:
  - Pago por separado (split)
  - Pago por item (partial)
  - Un cobro con propina, otro sin
  - Propina por método distinto al pago
  - Propina split (varios métodos)
  - Propinas atribuidas al garzón correcto en el reporte
  - Cierre de mesa (order CLOSED, table FREE)

Los payloads de `payments`/`tips` son los que el frontend YA separó:
payments = solo la cuenta (subtotal), tips = propina explícita. Eso es
exactamente lo que buildCheckoutSplit() produce (testeado en el front,
ver apps/web/__tests__/mesas-checkout.test.ts).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import User
from tables.models import Table, OpenOrder
from sales.models import Sale, SalePayment, SaleTip
from inventory.models import StockItem
from caja.models import CashRegister, CashSession


URL_TABLES = "/api/tables/tables/"
URL_TIPS_LIST = "/api/sales/tips-list/"


# ─── Helpers de flujo (vía API real) ─────────────────────────────────────


def _make_waiter(tenant, store, username, first="Gar", last="Zón"):
    u = User.objects.create_user(username=username, password="x", first_name=first, last_name=last)
    u.tenant = tenant
    u.active_store = store
    u.role = User.Role.CASHIER
    u.save(update_fields=["tenant", "active_store", "role"])
    return u


def _stock(tenant, warehouse, product, qty="1000", cost="100"):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={
            "on_hand": Decimal(qty), "avg_cost": Decimal(cost),
            "stock_value": (Decimal(qty) * Decimal(cost)).quantize(Decimal("0.001")),
        },
    )
    return si


def _create_table(api_client, name):
    r = api_client.post(URL_TABLES, {"name": name, "capacity": 4}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _open(api_client, table_id, warehouse_id, waiter_id=None):
    body = {"warehouse_id": warehouse_id}
    if waiter_id:
        body["waiter_id"] = waiter_id
    r = api_client.post(f"/api/tables/tables/{table_id}/open/", body, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def _add_lines(api_client, order_id, lines):
    r = api_client.post(f"/api/tables/orders/{order_id}/add-lines/", {"lines": lines}, format="json")
    assert r.status_code in (200, 201), r.content
    return r.json()


def _checkout(api_client, order_id, payload):
    return api_client.post(f"/api/tables/orders/{order_id}/checkout/", payload, format="json")


# ─── E2E ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAuditCobroMesaE2E:

    def test_cobro_total_con_propina_atribuida_a_garzon(
        self, api_client, tenant, store, warehouse, product, owner,
    ):
        """Flujo completo: garzón atiende mesa, se cobra TODO con propina
        efectivo. Verifica que la propina quede atribuida al GARZÓN (no al
        cajero) en /tips-list/, que la mesa cierre, y que SalePayment sea
        solo la cuenta."""
        _stock(tenant, warehouse, product)
        garzon = _make_waiter(tenant, store, "garzon_e2e_1", "Ana", "Atiende")

        table = _create_table(api_client, "Mesa E2E 1")
        order = _open(api_client, table["id"], warehouse.id, waiter_id=garzon.id)
        _add_lines(api_client, order["id"], [
            {"product_id": product.id, "qty": 1, "unit_price": "4000.00"},
            {"product_id": product.id, "qty": 1, "unit_price": "4000.00"},
        ])

        # Payload tal como lo arma el modal (buildCheckoutSplit):
        # cuenta 8000, propina 800 efectivo → payments=cuenta, tips=propina.
        resp = _checkout(api_client, order["id"], {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "8000"}],
            "tip": "800",
            "tips": [{"method": "cash", "amount": "800"}],
        })
        assert resp.status_code == 201, resp.content
        sale = Sale.objects.get(id=resp.json()["id"])

        # SalePayment = solo la cuenta
        assert sale.total == Decimal("8000.00")
        assert sum(p.amount for p in sale.payments.all()) == Decimal("8000.00")
        # SaleTip = propina aparte
        tips = list(SaleTip.objects.filter(sale=sale))
        assert len(tips) == 1
        assert tips[0].method == "cash"
        assert tips[0].amount == Decimal("800.00")
        assert sale.tip == Decimal("800.00")

        # Cierre de mesa: order CLOSED, table FREE
        order_db = OpenOrder.objects.get(id=order["id"])
        assert order_db.status == OpenOrder.STATUS_CLOSED
        table_db = Table.objects.get(id=table["id"])
        assert table_db.status == Table.STATUS_FREE

        # Propina atribuida al GARZÓN en el reporte
        r = api_client.get(f"{URL_TIPS_LIST}?waiter={garzon.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1, data
        row = data["results"][0]
        assert row["sale_id"] == sale.id
        assert row["waiter_id"] == garzon.id
        assert row["waiter_name"] == "Ana Atiende"
        assert row["tip_amount"] == "800.00"
        # Desglose por método de la propina
        assert row["tips"] == [{"id": tips[0].id, "method": "cash", "amount": "800.00"}]

    def test_dos_mesas_dos_garzones_una_con_propina_otra_sin(
        self, api_client, tenant, store, warehouse, product, owner,
    ):
        """Una mesa con propina (garzón A), otra sin propina (garzón B).
        El reporte debe atribuir SOLO la propina de A a A, y B no aparece
        en tips-list (sin propina)."""
        _stock(tenant, warehouse, product)
        gar_a = _make_waiter(tenant, store, "garzon_e2e_a", "Ana", "A")
        gar_b = _make_waiter(tenant, store, "garzon_e2e_b", "Beto", "B")

        # Mesa A: con propina
        ta = _create_table(api_client, "Mesa A")
        oa = _open(api_client, ta["id"], warehouse.id, waiter_id=gar_a.id)
        _add_lines(api_client, oa["id"], [{"product_id": product.id, "qty": 1, "unit_price": "5000.00"}])
        ra = _checkout(api_client, oa["id"], {
            "mode": "all",
            "payments": [{"method": "debit", "amount": "5000"}],
            "tip": "500", "tips": [{"method": "cash", "amount": "500"}],
        })
        assert ra.status_code == 201, ra.content
        sale_a = Sale.objects.get(id=ra.json()["id"])

        # Mesa B: SIN propina
        tb = _create_table(api_client, "Mesa B")
        ob = _open(api_client, tb["id"], warehouse.id, waiter_id=gar_b.id)
        _add_lines(api_client, ob["id"], [{"product_id": product.id, "qty": 1, "unit_price": "3000.00"}])
        rb = _checkout(api_client, ob["id"], {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "3000"}],
        })
        assert rb.status_code == 201, rb.content
        sale_b = Sale.objects.get(id=rb.json()["id"])

        assert sale_b.tip == Decimal("0.00")
        assert SaleTip.objects.filter(sale=sale_b).count() == 0

        # tips-list general: solo 1 (la de A)
        r = api_client.get(URL_TIPS_LIST)
        data = r.json()
        assert data["count"] == 1
        assert data["results"][0]["sale_id"] == sale_a.id

        # Filtrar por B: 0 propinas
        r = api_client.get(f"{URL_TIPS_LIST}?waiter={gar_b.id}")
        assert r.json()["count"] == 0

        # La propina de A quedó en cash (método distinto al pago débito)
        tip_a = SaleTip.objects.get(sale=sale_a)
        assert tip_a.method == "cash"
        assert tip_a.amount == Decimal("500.00")

    def test_cobro_split_pago_con_propina(
        self, api_client, tenant, store, warehouse, product, owner,
    ):
        """Split de pago (efectivo + débito) + propina. payments separados
        (ya netos), tips explícito. Verifica SalePayment split y SaleTip."""
        _stock(tenant, warehouse, product)
        garzon = _make_waiter(tenant, store, "garzon_split", "Sol", "Split")

        t = _create_table(api_client, "Mesa Split")
        o = _open(api_client, t["id"], warehouse.id, waiter_id=garzon.id)
        _add_lines(api_client, o["id"], [{"product_id": product.id, "qty": 1, "unit_price": "10000.00"}])

        # Modal split: cuenta 10000 = 5000 cash + 5000 debit, propina 1000 cash.
        resp = _checkout(api_client, o["id"], {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "5000"}, {"method": "debit", "amount": "5000"}],
            "tip": "1000", "tips": [{"method": "cash", "amount": "1000"}],
        })
        assert resp.status_code == 201, resp.content
        sale = Sale.objects.get(id=resp.json()["id"])

        pays = {p.method: p.amount for p in sale.payments.all()}
        assert pays == {"cash": Decimal("5000.00"), "debit": Decimal("5000.00")}
        assert sale.total == Decimal("10000.00")
        tip = SaleTip.objects.get(sale=sale)
        assert tip.method == "cash" and tip.amount == Decimal("1000.00")

    def test_cobro_propina_split_dos_metodos(
        self, api_client, tenant, store, warehouse, product, owner,
    ):
        """Propina dividida en 2 métodos (efectivo + débito). Verifica que
        se creen 2 SaleTip y que tips-list muestre el desglose 'mixed'."""
        _stock(tenant, warehouse, product)
        garzon = _make_waiter(tenant, store, "garzon_tipsplit", "Tip", "Split")

        t = _create_table(api_client, "Mesa TipSplit")
        o = _open(api_client, t["id"], warehouse.id, waiter_id=garzon.id)
        _add_lines(api_client, o["id"], [{"product_id": product.id, "qty": 1, "unit_price": "10000.00"}])

        resp = _checkout(api_client, o["id"], {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "10000"}],
            "tip": "1000",
            "tips": [{"method": "cash", "amount": "600"}, {"method": "debit", "amount": "400"}],
        })
        assert resp.status_code == 201, resp.content
        sale = Sale.objects.get(id=resp.json()["id"])

        tips = {t.method: t.amount for t in SaleTip.objects.filter(sale=sale)}
        assert tips == {"cash": Decimal("600.00"), "debit": Decimal("400.00")}
        assert sale.tip == Decimal("1000.00")

        # tips-list: método 'mixed' + desglose de las 2 filas
        r = api_client.get(f"{URL_TIPS_LIST}?waiter={garzon.id}")
        row = r.json()["results"][0]
        assert row["payment_method"] == "mixed"
        methods = {t["method"]: t["amount"] for t in row["tips"]}
        assert methods == {"cash": "600.00", "debit": "400.00"}

    def test_cobro_por_items_parcial_con_propina(
        self, api_client, tenant, store, warehouse, product, product_b, owner,
    ):
        """Cobro por items: se cobra 1 de 2 líneas con propina. La mesa NO
        cierra (queda 1 línea sin pagar). La propina de este cobro parcial
        queda atribuida al garzón."""
        _stock(tenant, warehouse, product)
        _stock(tenant, warehouse, product_b)
        garzon = _make_waiter(tenant, store, "garzon_partial", "Par", "Cial")

        t = _create_table(api_client, "Mesa Partial")
        o = _open(api_client, t["id"], warehouse.id, waiter_id=garzon.id)
        added = _add_lines(api_client, o["id"], [
            {"product_id": product.id, "qty": 1, "unit_price": "4000.00"},
            {"product_id": product_b.id, "qty": 1, "unit_price": "3000.00"},
        ])
        # Tomar el id de la primera línea
        line1_id = added["lines"][0]["id"]

        resp = _checkout(api_client, o["id"], {
            "mode": "partial",
            "line_ids": [line1_id],
            "payments": [{"method": "cash", "amount": "4000"}],
            "tip": "400", "tips": [{"method": "cash", "amount": "400"}],
        })
        assert resp.status_code == 201, resp.content
        sale = Sale.objects.get(id=resp.json()["id"])
        assert sale.total == Decimal("4000.00")
        assert SaleTip.objects.get(sale=sale).amount == Decimal("400.00")

        # La mesa NO cierra (queda product_b sin pagar)
        order_db = OpenOrder.objects.get(id=o["id"])
        assert order_db.status == OpenOrder.STATUS_OPEN
        table_db = Table.objects.get(id=t["id"])
        assert table_db.status == Table.STATUS_OPEN

        # Propina atribuida al garzón
        r = api_client.get(f"{URL_TIPS_LIST}?waiter={garzon.id}")
        assert r.json()["count"] == 1
        assert r.json()["results"][0]["tip_amount"] == "400.00"


@pytest.mark.django_db
class TestAuditCobroMesaCajaCuadre:
    """Cierre de caja con propinas de mesa cobradas vía endpoint real."""

    def test_cobro_mesa_con_propina_cuadra_caja(
        self, api_client, tenant, store, warehouse, product, owner,
    ):
        """Abrir caja → cobrar mesa con propina cash → cerrar caja cuadra
        exacto (la propina cash es dinero físico que entra al cajón)."""
        _stock(tenant, warehouse, product)
        register = CashRegister.objects.create(tenant=tenant, store=store, name="Caja Audit", is_active=True)
        garzon = _make_waiter(tenant, store, "garzon_caja", "Caj", "Era")

        # Abrir caja con $10.000 de fondo
        ro = api_client.post(reverse("caja-session-open", kwargs={"pk": register.id}),
                             {"initial_amount": "10000"}, format="json")
        assert ro.status_code in (200, 201), ro.content
        sess_id = ro.json()["id"]

        # Cobrar mesa: cuenta 5000 efectivo + propina 500 efectivo
        t = _create_table(api_client, "Mesa Caja")
        o = _open(api_client, t["id"], warehouse.id, waiter_id=garzon.id)
        _add_lines(api_client, o["id"], [{"product_id": product.id, "qty": 1, "unit_price": "5000.00"}])
        rc = _checkout(api_client, o["id"], {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "5000"}],
            "tip": "500", "tips": [{"method": "cash", "amount": "500"}],
        })
        assert rc.status_code == 201, rc.content

        # Live: expected_cash = 10000 fondo + 5000 cuenta cash + 500 propina cash
        live = api_client.get(reverse("caja-session-detail", kwargs={"pk": sess_id})).json()["live"]
        assert Decimal(live["cash_sales"]) == Decimal("5000"), live
        assert Decimal(live["cash_tips"]) == Decimal("500"), live
        assert Decimal(live["expected_cash"]) == Decimal("15500.00"), live

        # Cerrar contando exacto → diferencia 0
        rclose = api_client.post(reverse("caja-session-close", kwargs={"pk": sess_id}),
                                 {"counted_cash": "15500"}, format="json")
        assert rclose.status_code == 200, rclose.content
        assert Decimal(rclose.json()["difference"]) == Decimal("0.00")
