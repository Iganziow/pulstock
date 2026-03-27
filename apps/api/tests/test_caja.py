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
        assert resp.status_code == 404  # open session not found

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
