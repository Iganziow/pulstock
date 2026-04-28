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
