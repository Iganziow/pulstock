"""
tests/test_caja.py
==================
Comprehensive tests for the caja (cash register) module.
Covers registers, sessions, movements, and close/expected-cash logic.
"""
import pytest
from decimal import Decimal

from caja.models import CashRegister, CashSession, CashMovement


# ---------------------------------------------------------------------------
# Helper URLs
# ---------------------------------------------------------------------------
REGISTERS_URL = "/api/caja/registers/"
CURRENT_URL = "/api/caja/sessions/current/"
HISTORY_URL = "/api/caja/sessions/history/"


def open_url(register_id):
    return f"/api/caja/registers/{register_id}/open/"


def detail_url(session_id):
    return f"/api/caja/sessions/{session_id}/"


def movements_url(session_id):
    return f"/api/caja/sessions/{session_id}/movements/"


def close_url(session_id):
    return f"/api/caja/sessions/{session_id}/close/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def register(tenant, store):
    return CashRegister.objects.create(
        tenant=tenant, store=store, name="Caja 1"
    )


@pytest.fixture
def open_session(api_client, register):
    """Open a session with initial_amount=10000 and return the response data."""
    resp = api_client.post(open_url(register.id), {"initial_amount": "10000"})
    assert resp.status_code == 201
    return resp.data


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER TESTS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterCreate:

    def test_create_register(self, api_client):
        resp = api_client.post(REGISTERS_URL, {"name": "Caja Nueva"})
        assert resp.status_code == 201
        assert resp.data["name"] == "Caja Nueva"
        assert "id" in resp.data

    def test_create_register_missing_name(self, api_client):
        resp = api_client.post(REGISTERS_URL, {"name": ""})
        assert resp.status_code == 400

    def test_create_register_blank_name(self, api_client):
        resp = api_client.post(REGISTERS_URL, {})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestRegisterList:

    def test_list_empty(self, api_client):
        resp = api_client.get(REGISTERS_URL)
        assert resp.status_code == 200
        assert resp.data == []

    def test_list_returns_registers(self, api_client, register):
        resp = api_client.get(REGISTERS_URL)
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["name"] == "Caja 1"

    def test_has_open_session_flag_false(self, api_client, register):
        resp = api_client.get(REGISTERS_URL)
        assert resp.data[0]["has_open_session"] is False

    def test_has_open_session_flag_true(self, api_client, register, open_session):
        resp = api_client.get(REGISTERS_URL)
        assert resp.data[0]["has_open_session"] is True

    def test_inactive_register_not_listed(self, api_client, register):
        register.is_active = False
        register.save()
        resp = api_client.get(REGISTERS_URL)
        assert len(resp.data) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SESSION — OPEN
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOpenSession:

    def test_open_session_success(self, api_client, register):
        resp = api_client.post(open_url(register.id), {"initial_amount": "5000"})
        assert resp.status_code == 201
        assert resp.data["status"] == "OPEN"
        assert Decimal(resp.data["initial_amount"]) == Decimal("5000")
        assert resp.data["register_id"] == register.id

    def test_open_session_default_initial_amount(self, api_client, register):
        resp = api_client.post(open_url(register.id), {})
        assert resp.status_code == 201
        assert Decimal(resp.data["initial_amount"]) == Decimal("0")

    def test_open_duplicate_session_409(self, api_client, register, open_session):
        resp = api_client.post(open_url(register.id), {"initial_amount": "1000"})
        assert resp.status_code == 409

    def test_open_session_nonexistent_register_404(self, api_client):
        resp = api_client.post(open_url(99999), {"initial_amount": "1000"})
        assert resp.status_code == 404

    def test_open_session_inactive_register_404(self, api_client, register):
        register.is_active = False
        register.save()
        resp = api_client.post(open_url(register.id), {"initial_amount": "1000"})
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# SESSION — CURRENT
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCurrentSession:

    def test_current_no_open_session(self, api_client):
        resp = api_client.get(CURRENT_URL)
        assert resp.status_code == 404

    def test_current_returns_open_session(self, api_client, register, open_session):
        resp = api_client.get(CURRENT_URL)
        assert resp.status_code == 200
        assert resp.data["id"] == open_session["id"]
        assert resp.data["status"] == "OPEN"

    def test_current_includes_movements_and_live(self, api_client, register, open_session):
        resp = api_client.get(CURRENT_URL)
        assert "movements" in resp.data
        assert "live" in resp.data


# ═══════════════════════════════════════════════════════════════════════════
# SESSION — DETAIL
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSessionDetail:

    def test_detail_open_session(self, api_client, register, open_session):
        resp = api_client.get(detail_url(open_session["id"]))
        assert resp.status_code == 200
        assert resp.data["id"] == open_session["id"]
        assert "movements" in resp.data
        assert "live" in resp.data

    def test_detail_nonexistent_404(self, api_client):
        resp = api_client.get(detail_url(99999))
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# MOVEMENTS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMovements:

    def test_add_movement_in(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "IN",
            "amount": "5000",
            "description": "Cambio recibido",
        })
        assert resp.status_code == 201
        assert resp.data["type"] == "IN"
        assert Decimal(resp.data["amount"]) == Decimal("5000")
        assert resp.data["description"] == "Cambio recibido"

    def test_add_movement_out(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "OUT",
            "amount": "2000",
            "description": "Pago proveedor",
        })
        assert resp.status_code == 201
        assert resp.data["type"] == "OUT"
        assert Decimal(resp.data["amount"]) == Decimal("2000")

    def test_add_movement_invalid_type_400(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "TRANSFER",
            "amount": "1000",
            "description": "Transferencia",
        })
        assert resp.status_code == 400

    def test_add_movement_zero_amount_400(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "IN",
            "amount": "0",
            "description": "Cero",
        })
        assert resp.status_code == 400

    def test_add_movement_negative_amount_400(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "IN",
            "amount": "-500",
            "description": "Negativo",
        })
        assert resp.status_code == 400

    def test_add_movement_missing_description_400(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(movements_url(sid), {
            "type": "IN",
            "amount": "1000",
            "description": "",
        })
        assert resp.status_code == 400

    def test_add_movement_on_closed_session(self, api_client, register, open_session):
        sid = open_session["id"]
        # Close the session first
        api_client.post(close_url(sid), {"counted_cash": "10000"})
        # Try to add movement
        resp = api_client.post(movements_url(sid), {
            "type": "IN",
            "amount": "1000",
            "description": "Late movement",
        })
        # Post-fix RACE-10: lockeamos sesión y validamos status bajo lock.
        # Ahora devuelve 409 (conflict) — distingue de "sesión no existe".
        assert resp.status_code == 409

    def test_add_movement_nonexistent_session(self, api_client):
        resp = api_client.post(movements_url(99999), {
            "type": "IN",
            "amount": "1000",
            "description": "Ghost",
        })
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# SESSION — CLOSE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCloseSession:

    def test_close_session_basic(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(close_url(sid), {"counted_cash": "10000"})
        assert resp.status_code == 200
        assert resp.data["status"] == "CLOSED"
        assert resp.data["counted_cash"] is not None
        assert resp.data["expected_cash"] is not None
        assert resp.data["difference"] is not None
        assert resp.data["closed_at"] is not None

    def test_close_session_expected_cash_equals_initial_no_movements(
        self, api_client, register, open_session
    ):
        """With no sales or movements, expected = initial_amount."""
        sid = open_session["id"]
        resp = api_client.post(close_url(sid), {"counted_cash": "12000"})
        assert resp.status_code == 200
        # expected should be 10000 (the initial_amount)
        assert Decimal(resp.data["expected_cash"]) == Decimal("10000.00")
        # difference = counted - expected = 12000 - 10000 = 2000
        assert Decimal(resp.data["difference"]) == Decimal("2000.00")

    def test_close_session_with_movements(self, api_client, register, open_session):
        """expected = initial + movements_in - movements_out."""
        sid = open_session["id"]
        # Add IN movement
        api_client.post(movements_url(sid), {
            "type": "IN", "amount": "3000", "description": "Extra cash"
        })
        # Add OUT movement
        api_client.post(movements_url(sid), {
            "type": "OUT", "amount": "1000", "description": "Expense"
        })
        # expected = 10000 + 3000 - 1000 = 12000
        resp = api_client.post(close_url(sid), {"counted_cash": "11500"})
        assert resp.status_code == 200
        assert Decimal(resp.data["expected_cash"]) == Decimal("12000.00")
        # difference = 11500 - 12000 = -500
        assert Decimal(resp.data["difference"]) == Decimal("-500.00")

    def test_close_session_with_note(self, api_client, register, open_session):
        sid = open_session["id"]
        resp = api_client.post(close_url(sid), {
            "counted_cash": "10000",
            "note": "Todo cuadra",
        })
        assert resp.status_code == 200
        assert resp.data["note"] == "Todo cuadra"

    def test_close_already_closed_session(self, api_client, register, open_session):
        sid = open_session["id"]
        api_client.post(close_url(sid), {"counted_cash": "10000"})
        # Try closing again
        resp = api_client.post(close_url(sid), {"counted_cash": "10000"})
        assert resp.status_code == 404  # open session not found

    def test_close_nonexistent_session(self, api_client):
        resp = api_client.post(close_url(99999), {"counted_cash": "10000"})
        assert resp.status_code == 404

    def test_after_close_current_returns_404(self, api_client, register, open_session):
        """After closing, GET /current/ should return 404."""
        sid = open_session["id"]
        api_client.post(close_url(sid), {"counted_cash": "10000"})
        resp = api_client.get(CURRENT_URL)
        assert resp.status_code == 404

    def test_after_close_can_reopen(self, api_client, register, open_session):
        """After closing a session, a new one can be opened on the same register."""
        sid = open_session["id"]
        api_client.post(close_url(sid), {"counted_cash": "10000"})
        resp = api_client.post(open_url(register.id), {"initial_amount": "5000"})
        assert resp.status_code == 201
        assert resp.data["status"] == "OPEN"


# ═══════════════════════════════════════════════════════════════════════════
# SESSION — HISTORY
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSessionHistory:

    def test_history_empty(self, api_client):
        resp = api_client.get(HISTORY_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["results"] == []

    def test_history_includes_closed_sessions(self, api_client, register, open_session):
        sid = open_session["id"]
        api_client.post(close_url(sid), {"counted_cash": "10000"})
        resp = api_client.get(HISTORY_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["results"][0]["status"] == "CLOSED"

    def test_history_excludes_open_sessions(self, api_client, register, open_session):
        resp = api_client.get(HISTORY_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# MULTI-REGISTER
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMultiRegister:

    def test_two_registers_independent_sessions(self, api_client, tenant, store):
        """Two registers can each have an open session simultaneously."""
        r1 = CashRegister.objects.create(tenant=tenant, store=store, name="Caja A")
        r2 = CashRegister.objects.create(tenant=tenant, store=store, name="Caja B")

        resp1 = api_client.post(open_url(r1.id), {"initial_amount": "1000"})
        resp2 = api_client.post(open_url(r2.id), {"initial_amount": "2000"})
        assert resp1.status_code == 201
        assert resp2.status_code == 201

        # Both show in register list
        resp = api_client.get(REGISTERS_URL)
        open_flags = {r["name"]: r["has_open_session"] for r in resp.data}
        assert open_flags["Caja A"] is True
        assert open_flags["Caja B"] is True


# ═══════════════════════════════════════════════════════════════════════════
# TIPS PER METHOD vs CASH FLOW (regression test for cash-tip bug 27/04/26)
# ═══════════════════════════════════════════════════════════════════════════
# Mario reportó: la caja no cuadraba al cierre porque las propinas pagadas
# por DÉBITO/CRÉDITO se estaban sumando al efectivo esperado en caja
# (cash_tips antes era SUM de TODAS las propinas, sin filtrar método).
# Si una venta se pagó por tarjeta + propina, la caja esperaba esa
# propina en efectivo físico que nunca entró → diferencia falsa al cierre.

@pytest.mark.django_db
class TestTipsCashFlowReconciliation:

    def _create_sale_with_payment(self, owner, tenant, store, warehouse, session, total, tip, method):
        """Helper: crea venta COMPLETED con tip y un único pago en `method`."""
        from sales.models import Sale, SalePayment
        from decimal import Decimal as D
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner,
            cash_session=session,
            status="COMPLETED",
            sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D(total), total=D(total) + D(tip),
            tip=D(tip),
            total_cost=D("0"), gross_profit=D("0"),
        )
        SalePayment.objects.create(
            tenant=tenant, sale=sale,
            method=method, amount=D(total) + D(tip),
        )
        return sale

    def test_tip_paid_by_debit_does_not_inflate_cash(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """Reproduce el bug exacto que reportó Mario:
        venta de $36.500 + $2.137 propina pagada TODA con DÉBITO.
        SalePayment.amount = $38.637 (subtotal + propina).
        Antes del fix: expected_cash sumaba $2.137 al efectivo.
        Después del fix: expected_cash queda igual al fondo inicial
        (no entró nada de efectivo físico).
        """
        session = CashSession.objects.get(id=open_session["id"])
        self._create_sale_with_payment(
            owner, tenant, store, warehouse, session,
            total="36500", tip="2137", method="debit",
        )
        resp = api_client.get(detail_url(session.id))
        live = resp.data["live"]
        # cash_tips debe ser 0 — la propina fue por débito, no efectivo.
        assert Decimal(live["cash_tips"]) == Decimal("0")
        # total_tips sigue mostrando los $2.137 (informativo).
        assert Decimal(live["total_tips"]) == Decimal("2137")
        # tips_by_method["debit"] debe tener los $2.137.
        assert Decimal(live["tips_by_method"]["debit"]) == Decimal("2137")
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("0")
        # debit_sales (display) = pago bruto $38.637 − propina $2.137 = $36.500
        assert Decimal(live["debit_sales"]) == Decimal("36500")
        # cash_sales = 0 (no hubo nada en efectivo).
        assert Decimal(live["cash_sales"]) == Decimal("0")
        # expected_cash = solo fondo inicial (no entró efectivo).
        assert Decimal(live["expected_cash"]) == Decimal("10000.00")

    def test_tip_paid_by_cash_inflates_cash(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """Caso complementario: venta $5000 + propina $500 toda en EFECTIVO.
        SalePayment.amount = $5500 (cliente entregó eso en efectivo físico).
        - cash_sales display = $5000 (sin propina)
        - cash_tips display = $500
        - expected_cash = fondo + $5500 (todo el cash físico que entró)
        """
        session = CashSession.objects.get(id=open_session["id"])
        self._create_sale_with_payment(
            owner, tenant, store, warehouse, session,
            total="5000", tip="500", method="cash",
        )
        resp = api_client.get(detail_url(session.id))
        live = resp.data["live"]
        assert Decimal(live["cash_tips"]) == Decimal("500")
        assert Decimal(live["total_tips"]) == Decimal("500")
        # cash_sales (display) = pago bruto $5500 − propina $500 = $5000
        assert Decimal(live["cash_sales"]) == Decimal("5000")
        # expected_cash = fondo $10000 + total cash físico $5500 = $15500
        assert Decimal(live["expected_cash"]) == Decimal("15500.00")

    def test_split_payment_tip_attribution(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """Venta $8000 + propina $1000 split: $5625 cash + $3375 card
        (ambos cubren proporcionalmente subtotal+propina = $9000).
        Reparto proporcional propina: 1000 × 5625/9000 = 625 a cash,
        1000 × 3375/9000 = 375 a card.
        - cash_sales display = $5625 - $625 = $5000
        - card_sales display = $3375 - $375 = $3000
        - expected_cash = fondo + $5625 (todo cash físico)
        """
        from sales.models import Sale, SalePayment
        from decimal import Decimal as D
        session = CashSession.objects.get(id=open_session["id"])
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner,
            cash_session=session,
            status="COMPLETED",
            sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D("8000"), total=D("9000"),
            tip=D("1000"),
            total_cost=D("0"), gross_profit=D("0"),
        )
        SalePayment.objects.create(tenant=tenant, sale=sale, method="cash", amount=D("5625"))
        SalePayment.objects.create(tenant=tenant, sale=sale, method="card", amount=D("3375"))

        resp = api_client.get(detail_url(session.id))
        live = resp.data["live"]
        # cash_tips = 1000 × 5625/9000 = 625
        assert Decimal(live["cash_tips"]) == Decimal("625")
        # tips_by_method["card"] absorbe el resto del redondeo = 375
        assert Decimal(live["tips_by_method"]["card"]) == Decimal("375")
        # Suma debe ser exacta 1000 (no 999 por redondeo)
        total_breakdown = sum(Decimal(v) for v in live["tips_by_method"].values())
        assert total_breakdown == Decimal("1000")
        # cash_sales = $5625 - $625 = $5000
        assert Decimal(live["cash_sales"]) == Decimal("5000")
        # card_sales = $3375 - $375 = $3000
        assert Decimal(live["card_sales"]) == Decimal("3000")
        # expected_cash = fondo $10000 + cash físico $5625 = $15625
        assert Decimal(live["expected_cash"]) == Decimal("15625.00")

    def test_consumo_interno_with_tip_does_not_leak_to_session_summary(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """Defensa: si por algún bug llegara una venta CONSUMO_INTERNO con
        tip > 0, NO debe aparecer en tips_by_method ni en total_tips de
        la sesión activa. CONSUMO_INTERNO no es ingreso del local y no
        genera propinas para el equipo (no hubo cliente que pagara).
        """
        from sales.models import Sale, SalePayment
        from decimal import Decimal as D
        session = CashSession.objects.get(id=open_session["id"])
        # Sale CONSUMO_INTERNO con tip 500 (estado inválido pero defensivo).
        Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
            cash_session=session,
            status="COMPLETED", sale_type=Sale.SALE_TYPE_CONSUMO,
            subtotal=D("3000"), total=D("3000"),
            tip=D("500"),
            total_cost=D("0"), gross_profit=D("0"),
        )
        # Y una venta normal VENTA con tip 200 para confirmar que sí cuenta.
        sale_v = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
            cash_session=session,
            status="COMPLETED", sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D("2000"), total=D("2000"),
            tip=D("200"),
            total_cost=D("0"), gross_profit=D("0"),
        )
        SalePayment.objects.create(tenant=tenant, sale=sale_v, method="cash", amount=D("2200"))

        resp = api_client.get(detail_url(session.id))
        live = resp.data["live"]
        # Solo la propina de la VENTA debe aparecer (200), no la del CONSUMO (500).
        assert Decimal(live["total_tips"]) == Decimal("200")
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("200")

    def test_split_tip_method_diff_payments_no_negative_sales(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """Daniel 29/04/26: caso real Marbrava — cliente paga cuenta de
        $3.500 con $4.000 cash (incluye propina $500). Después el dueño
        edita la propina a split: $300 cash + $200 transferencia. Los
        payments siguen siendo cash $4.000, pero ahora hay propina por
        transferencia $200 sin payment de transferencia.

        Antes del fix: transfer_sales = 0 - 200 = -$200 (mostraba negativo).
        Después: transfer_sales clamped a $0, transferencia $200 visible
        en tips_by_method, total_sales toma sum(sale.total) directo.
        """
        from sales.models import Sale, SalePayment, SaleTip
        from decimal import Decimal as D
        session = CashSession.objects.get(id=open_session["id"])
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner,
            cash_session=session,
            status="COMPLETED",
            sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D("3500"), total=D("3500"),
            tip=D("500"),
            total_cost=D("0"), gross_profit=D("0"),
        )
        SalePayment.objects.create(tenant=tenant, sale=sale, method="cash", amount=D("4000"))
        # Tip split: 300 cash + 200 transferencia (sin payment de transferencia)
        SaleTip.objects.create(tenant=tenant, sale=sale, method="cash", amount=D("300"))
        SaleTip.objects.create(tenant=tenant, sale=sale, method="transfer", amount=D("200"))

        resp = api_client.get(detail_url(session.id))
        live = resp.data["live"]
        # NO debe ser negativo
        assert Decimal(live["transfer_sales"]) >= 0
        assert Decimal(live["transfer_sales"]) == Decimal("0")
        # Cash sales: 4000 cash payment - 300 cash tip = 3700
        assert Decimal(live["cash_sales"]) == Decimal("3700")
        # Tips by method correctos
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("300")
        assert Decimal(live["tips_by_method"]["transfer"]) == Decimal("200")
        # total_sales = subtotal real (3500), no derivado de payments
        assert Decimal(live["total_sales"]) == Decimal("3500")
        # expected_cash usa cash_payments_total (4000 cash) + initial (10000)
        assert Decimal(live["expected_cash"]) == Decimal("14000.00")


# ═══════════════════════════════════════════════════════════════════════════
# VOID — la propina debe limpiarse al anular venta (regresión 27/04/26)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestVoidClearsTip:

    def test_void_zeros_sale_tip(self, api_client, owner, tenant, store, warehouse):
        """Cuando se anula una venta con tip > 0, sale.tip debe quedar
        en 0 para que no aparezca en reportes de propinas. El tip
        original queda registrado en el audit log."""
        from sales.models import Sale, SalePayment, SaleLine
        from catalog.models import Product
        from decimal import Decimal as D
        from inventory.models import StockItem
        from core.models import Warehouse as W

        # Producto + stock para que el void pueda revertir
        product = Product.objects.create(
            tenant=tenant, name="Café", sku="CAF1", price=D("2000"),
            cost=D("500"), is_active=True,
        )
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("10"), avg_cost=D("500"),
        )

        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
            status="COMPLETED", sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D("2000"), total=D("2000"),
            tip=D("200"),
            total_cost=D("500"), gross_profit=D("1500"),
        )
        SaleLine.objects.create(
            tenant=tenant, sale=sale, product=product,
            qty=D("1"), unit_price=D("2000"), line_total=D("2000"),
            unit_cost_snapshot=D("500"), line_cost=D("500"),
        )
        SalePayment.objects.create(tenant=tenant, sale=sale, method="cash", amount=D("2200"))

        resp = api_client.post(f"/api/sales/sales/{sale.id}/void/")
        assert resp.status_code == 200, resp.data

        sale.refresh_from_db()
        assert sale.status == "VOID"
        assert sale.tip == Decimal("0.00"), \
            f"Tip debería quedar en 0 al anular, pero quedó en {sale.tip}"


# ═══════════════════════════════════════════════════════════════════════════
# CIERRE INMUTABLE — Daniel 29/04/26 (estilo Fudo: arqueo cerrado no muta)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestClosingSnapshotImmutable:
    """Casos vitales para el cierre de caja:

    1. Editar propina DESPUÉS del cierre NO debe cambiar el reporte de la
       sesión cerrada (snapshot inmutable).
    2. Anular venta DESPUÉS del cierre NO debe cambiar el reporte cerrado.
    3. Sesiones consecutivas: cada arqueo cuenta SOLO sus ventas, sin
       solapamiento si dos sesiones comparten timestamp exacto.
    """

    def _create_sale_in_session(self, owner, tenant, store, warehouse, session,
                                  total, tip_method, tip_amount, payment_method=None):
        from sales.models import Sale, SalePayment, SaleTip
        from decimal import Decimal as D
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner,
            cash_session=session,
            status="COMPLETED",
            sale_type=Sale.SALE_TYPE_VENTA,
            subtotal=D(total), total=D(total),
            tip=D(tip_amount),
            total_cost=D("0"), gross_profit=D("0"),
        )
        pay_method = payment_method or tip_method
        SalePayment.objects.create(
            tenant=tenant, sale=sale,
            method=pay_method, amount=D(total) + D(tip_amount),
        )
        if Decimal(str(tip_amount)) > 0:
            SaleTip.objects.create(
                tenant=tenant, sale=sale,
                method=tip_method, amount=D(tip_amount),
            )
        return sale

    def test_edit_tip_after_close_does_not_mutate_closed_session(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """CASO #1: Mario cierra caja con tip $500. Al día siguiente
        edita la propina de esa venta a $5000. El reporte CERRADO debe
        seguir mostrando $500 (snapshot inmutable). Solo lo "live" de
        sesiones OPEN refleja cambios.
        """
        session = CashSession.objects.get(id=open_session["id"])
        sale = self._create_sale_in_session(
            owner, tenant, store, warehouse, session,
            total="5000", tip_method="cash", tip_amount="500",
        )

        # Cerrar la sesión
        close_resp = api_client.post(close_url(session.id), {"counted_cash": "15500"})
        assert close_resp.status_code == 200, close_resp.data
        snapshot_at_close = close_resp.data["live"]
        assert Decimal(snapshot_at_close["total_tips"]) == Decimal("500")
        assert Decimal(snapshot_at_close["tips_by_method"]["cash"]) == Decimal("500")

        # Ahora editar la propina (POST cierre) — esto NO debe afectar el cierre
        from sales.models import SaleTip
        SaleTip.objects.filter(sale=sale).delete()
        SaleTip.objects.create(tenant=tenant, sale=sale, method="cash", amount=Decimal("5000"))
        sale.tip = Decimal("5000")
        sale.save(update_fields=["tip"])

        # Re-consultar el detalle de la sesión CERRADA
        resp = api_client.get(detail_url(session.id))
        assert resp.status_code == 200
        live_after = resp.data["live"]
        # CRÍTICO: el snapshot debe ser igual al del cierre, NO al recálculo actual
        assert Decimal(live_after["total_tips"]) == Decimal("500"), (
            f"INMUTABILIDAD ROTA: el reporte cerrado cambió tras editar propina. "
            f"Esperado $500 (al cierre), obtenido ${live_after['total_tips']}."
        )
        assert Decimal(live_after["tips_by_method"]["cash"]) == Decimal("500")
        # Y los campos persistidos también
        assert Decimal(resp.data["expected_cash"]) == Decimal(snapshot_at_close["expected_cash"])

    def test_void_sale_after_close_does_not_mutate_closed_session(
        self, api_client, owner, tenant, store, warehouse, register, open_session,
    ):
        """CASO #2: Sesión cerrada con venta + propina $500. Después
        anulan la venta. El cierre histórico NO debe perder esos $500.
        """
        session = CashSession.objects.get(id=open_session["id"])
        sale = self._create_sale_in_session(
            owner, tenant, store, warehouse, session,
            total="3000", tip_method="cash", tip_amount="500",
        )

        # Cerrar
        close_resp = api_client.post(close_url(session.id), {"counted_cash": "13500"})
        assert close_resp.status_code == 200
        tips_at_close = Decimal(close_resp.data["live"]["total_tips"])
        sales_at_close = Decimal(close_resp.data["live"]["total_sales"])
        assert tips_at_close == Decimal("500")

        # Anular la venta DESPUÉS del cierre
        void_resp = api_client.post(f"/api/sales/sales/{sale.id}/void/")
        assert void_resp.status_code == 200

        # Re-consultar el cierre — debe seguir mostrando los mismos valores
        resp = api_client.get(detail_url(session.id))
        live_after = resp.data["live"]
        assert Decimal(live_after["total_tips"]) == tips_at_close, (
            f"INMUTABILIDAD ROTA: al anular venta el cierre histórico perdió propinas. "
            f"Antes ${tips_at_close}, ahora ${live_after['total_tips']}."
        )
        assert Decimal(live_after["total_sales"]) == sales_at_close

    def test_consecutive_sessions_no_overlap_no_double_count(
        self, api_client, owner, tenant, store, warehouse, register,
    ):
        """CASO #3: Dos sesiones consecutivas. Cada una debe contar SOLO
        sus propias ventas — ni doble conteo ni huérfanas.

        Mario abre 10:00, vende $5000 a las 11:00, cierra 12:00.
        Ignacia abre 12:05, vende $3000 a las 13:00, cierra 14:00.
        """
        from django.utils import timezone
        from datetime import timedelta
        from sales.models import Sale, SalePayment

        # Sesión Mario: opened 12 horas atrás, closed 10 horas atrás
        now = timezone.now()
        sess_mario = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            opened_by=owner,
            initial_amount=Decimal("10000"),
            status=CashSession.STATUS_CLOSED,
            closed_by=owner,
            closed_at=now - timedelta(hours=10),
            counted_cash=Decimal("15000"),
            expected_cash=Decimal("15000"),
            difference=Decimal("0"),
            closing_snapshot={"total_sales": "5000", "total_tips": "0", "_legacy_test": True},
        )
        # Override opened_at via update (auto_now_add no acepta seteo en create normal)
        CashSession.objects.filter(id=sess_mario.id).update(
            opened_at=now - timedelta(hours=12),
        )
        sess_mario.refresh_from_db()

        # Venta de Mario: 11h atrás (durante su sesión)
        s_mario = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner, cash_session=sess_mario,
            status="COMPLETED", sale_type="VENTA",
            subtotal=Decimal("5000"), total=Decimal("5000"),
            tip=Decimal("0"), total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        Sale.objects.filter(id=s_mario.id).update(created_at=now - timedelta(hours=11))
        SalePayment.objects.create(tenant=tenant, sale=s_mario, method="cash", amount=Decimal("5000"))

        # Sesión Ignacia: opened hace ~9.9h (5min después del cierre de Mario)
        sess_ignacia = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            opened_by=owner,
            initial_amount=Decimal("10000"),
            status=CashSession.STATUS_OPEN,
        )
        CashSession.objects.filter(id=sess_ignacia.id).update(
            opened_at=now - timedelta(hours=9, minutes=55),
        )
        sess_ignacia.refresh_from_db()

        # Venta de Ignacia: 9h atrás (durante su sesión)
        s_ignacia = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner, cash_session=sess_ignacia,
            status="COMPLETED", sale_type="VENTA",
            subtotal=Decimal("3000"), total=Decimal("3000"),
            tip=Decimal("0"), total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        Sale.objects.filter(id=s_ignacia.id).update(created_at=now - timedelta(hours=9))
        SalePayment.objects.create(tenant=tenant, sale=s_ignacia, method="cash", amount=Decimal("3000"))

        # Detail de la sesión actualmente OPEN (Ignacia) — debe ver SOLO $3000, no $8000
        resp = api_client.get(detail_url(sess_ignacia.id))
        live = resp.data["live"]
        assert Decimal(live["total_sales"]) == Decimal("3000"), (
            f"DOBLE CONTEO: la sesión de Ignacia ve ${live['total_sales']} "
            f"(debería ver $3000). Probablemente está incluyendo la venta de Mario."
        )
        assert Decimal(live["cash_sales"]) == Decimal("3000")

        # Y la sesión CERRADA de Mario debe seguir mostrando su snapshot ($5000)
        resp_mario = api_client.get(detail_url(sess_mario.id))
        # El snapshot persistido tiene total_sales=5000 (lo que pusimos)
        assert resp_mario.data["live"].get("total_sales") == "5000"

    def test_consecutive_sessions_boundary_exact_same_timestamp(
        self, api_client, owner, tenant, store, warehouse, register,
    ):
        """CASO #3.bis: edge case de boundary. Mario cierra exactamente
        en T. Ignacia abre exactamente en T. Una venta hecha en T debe
        entrar a UNA sola sesión, no a las dos.

        Con __gt en start_dt (cuando viene de prev_closed) + __lte en
        end_dt, la venta hecha en T entra al cierre de Mario (no a la
        sesión de Ignacia).

        Importante: Mario debe tener actividad real (al menos 1 venta
        previa) para ser considerado como prev_closed en la lógica de
        "ignorar sesiones-fantasma sin actividad" (caso Marbrava 27-abr).
        """
        from django.utils import timezone
        from datetime import timedelta
        from sales.models import Sale, SalePayment

        now = timezone.now()
        boundary = now - timedelta(hours=5)  # T = momento exacto del solapamiento

        sess_mario = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            opened_by=owner,
            initial_amount=Decimal("10000"),
            status=CashSession.STATUS_CLOSED,
            closed_by=owner,
            closed_at=boundary,
            counted_cash=Decimal("11000"),
            expected_cash=Decimal("11000"),
            difference=Decimal("0"),
            closing_snapshot={"total_sales": "1000", "total_tips": "0"},
        )
        CashSession.objects.filter(id=sess_mario.id).update(opened_at=now - timedelta(hours=8))

        # Actividad de Mario (necesaria para que sess_mario califique como
        # "prev_closed con actividad" en _sales_in_session_range).
        s_mario_prev = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner, cash_session=sess_mario,
            status="COMPLETED", sale_type="VENTA",
            subtotal=Decimal("1000"), total=Decimal("1000"),
            tip=Decimal("0"), total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        Sale.objects.filter(id=s_mario_prev.id).update(created_at=now - timedelta(hours=7))
        SalePayment.objects.create(tenant=tenant, sale=s_mario_prev, method="cash", amount=Decimal("1000"))

        sess_ignacia = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            opened_by=owner,
            initial_amount=Decimal("10000"),
            status=CashSession.STATUS_OPEN,
        )
        CashSession.objects.filter(id=sess_ignacia.id).update(opened_at=boundary)
        sess_ignacia.refresh_from_db()

        # Venta hecha EXACTAMENTE en T (boundary) — sin FK explícito a sesión
        s_boundary = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner,
            status="COMPLETED", sale_type="VENTA",
            subtotal=Decimal("500"), total=Decimal("500"),
            tip=Decimal("0"), total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        Sale.objects.filter(id=s_boundary.id).update(created_at=boundary)
        SalePayment.objects.create(tenant=tenant, sale=s_boundary, method="cash", amount=Decimal("500"))

        # La sesión de Ignacia (open) debe NO incluir la venta del boundary
        # (start_dt = T desde prev_closed.closed_at → filter __gt T excluye T exacto).
        resp = api_client.get(detail_url(sess_ignacia.id))
        live = resp.data["live"]
        assert Decimal(live["total_sales"]) == Decimal("0"), (
            f"BOUNDARY OVERLAP: venta en T={boundary} entró erróneamente a la "
            f"sesión que arranca en T. total_sales={live['total_sales']}, esperado $0."
        )
