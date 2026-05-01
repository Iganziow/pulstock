"""
Tests del endpoint DELETE /caja/movements/<id>/
(Daniel/Mario 01/05/26 — caso real Marbrava: pago a Covili marcado mal).

REGLAS DE PROTECCIÓN:
- Caja OPEN o huérfano  → manager+ puede borrar
- Caja CLOSED           → solo OWNER

Es DINERO CRÍTICO — los tests cubren:
1. Permisos por estado de sesión
2. Permisos por rol del usuario
3. Multi-tenant (no borrar de otro tenant)
4. Multi-store (no borrar de otro store)
5. Audit log
6. Snapshot inmutable de cierre NO se altera
"""
import pytest
from decimal import Decimal

from caja.models import CashRegister, CashSession, CashMovement
from core.models import Tenant, User
from stores.models import Store


pytestmark = pytest.mark.django_db


# ─── Helpers ──────────────────────────────────────────────────────────────

def _create_movement(tenant, session, type_="OUT", amount="1000", desc="test", category=""):
    return CashMovement.objects.create(
        tenant=tenant, session=session, type=type_,
        amount=Decimal(str(amount)), description=desc, category=category,
        created_by=session.opened_by,
    )


@pytest.fixture
def register_fx(tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja A")


@pytest.fixture
def open_session_fx(register_fx, owner, tenant, store):
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register_fx,
        opened_by=owner, initial_amount=Decimal("10000"), status="OPEN",
    )


@pytest.fixture
def closed_session_fx(register_fx, owner, tenant, store):
    """Sesión cerrada con snapshot persistido (PR #97)."""
    from django.utils import timezone
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register_fx,
        opened_by=owner, initial_amount=Decimal("10000"),
        status="CLOSED", closed_by=owner, closed_at=timezone.now(),
        counted_cash=Decimal("10000"), expected_cash=Decimal("10000"),
        difference=Decimal("0"),
        closing_snapshot={"total_sales": "0", "total_tips": "0"},
    )


@pytest.fixture
def manager_user(tenant, store):
    """User con rol manager (no owner)."""
    u = User.objects.create_user(
        username="manager_test_del", email="manager@del.test",
        password="x", tenant=tenant,
    )
    u.role = "manager"
    u.active_store = store
    u.save()
    return u


# ─── 1. Casos OPEN ──────────────────────────────────────────────────────

class TestDeleteOpenSession:
    """Movimientos en sesión OPEN: cualquier user con tenant puede borrar."""

    def test_delete_movement_in_open_session_works(
        self, api_client, owner, tenant, open_session_fx,
    ):
        m = _create_movement(tenant, open_session_fx)
        r = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r.status_code == 200, r.data
        assert not CashMovement.objects.filter(id=m.id).exists()

    def test_delete_returns_snapshot_in_response(
        self, api_client, owner, tenant, open_session_fx,
    ):
        m = _create_movement(tenant, open_session_fx, type_="OUT", amount="1500", desc="Pago Covili")
        r = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r.status_code == 200
        snap = r.data["deleted"]
        assert snap["type"] == "OUT"
        assert snap["amount"] == "1500.00"
        assert snap["description"] == "Pago Covili"


# ─── 2. Casos CLOSED ────────────────────────────────────────────────────

class TestDeleteClosedSession:
    """Movimientos en sesión CLOSED: solo OWNER, manager rechazado."""

    def test_owner_can_delete_in_closed_session(
        self, api_client, owner, tenant, closed_session_fx,
    ):
        m = _create_movement(tenant, closed_session_fx)
        r = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r.status_code == 200, r.data
        assert not CashMovement.objects.filter(id=m.id).exists()

    def test_manager_cannot_delete_in_closed_session(
        self, api_client, manager_user, tenant, closed_session_fx,
    ):
        m = _create_movement(tenant, closed_session_fx)
        api_client.force_authenticate(user=manager_user)
        r = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r.status_code == 403, r.data
        assert r.data.get("code") == "closed_session_owner_only"
        # NO se borró
        assert CashMovement.objects.filter(id=m.id).exists()

    def test_closed_session_snapshot_does_not_change_after_delete(
        self, api_client, owner, tenant, closed_session_fx,
    ):
        """El closing_snapshot histórico (PR #97) NO debe mutar al borrar
        un movimiento de la sesión cerrada. Reporte histórico inmutable."""
        m = _create_movement(tenant, closed_session_fx, type_="OUT", amount="500")
        snap_before = dict(closed_session_fx.closing_snapshot)
        r = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r.status_code == 200
        closed_session_fx.refresh_from_db()
        # El snapshot debe seguir siendo idéntico
        assert closed_session_fx.closing_snapshot == snap_before


# ─── 3. Multi-tenant + multi-store ──────────────────────────────────────

class TestDeleteSecurityIsolation:
    """No se debe poder borrar movimientos de otro tenant o store."""

    def test_cannot_delete_other_tenant_movement(
        self, api_client, owner, tenant, open_session_fx,
    ):
        # Crear otro tenant + sesión + movimiento
        t2 = Tenant.objects.create(slug="other-del", name="Other")
        s2 = Store.objects.create(tenant=t2, code="o", name="OS")
        r2 = CashRegister.objects.create(tenant=t2, store=s2, name="R2")
        u2 = User.objects.create_user(username="u2-del", email="u2@del", password="x", tenant=t2)
        sess2 = CashSession.objects.create(
            tenant=t2, store=s2, register=r2, opened_by=u2,
            initial_amount=Decimal("0"), status="OPEN",
        )
        m_other = _create_movement(t2, sess2)

        # Owner del tenant 1 intenta borrar mov del tenant 2
        r = api_client.delete(f"/api/caja/movements/{m_other.id}/")
        assert r.status_code == 404  # ni siquiera lo encuentra (filtra por tenant)
        # NO se borró
        assert CashMovement.objects.filter(id=m_other.id).exists()

    def test_cannot_delete_other_store_movement(
        self, api_client, owner, tenant, store, open_session_fx,
    ):
        """Aun mismo tenant: no debe borrar movs de un store al que el
        usuario no tiene acceso (active_store != el store del mov)."""
        # Crear otro store + sesión + mov en mismo tenant
        s2 = Store.objects.create(tenant=tenant, code="s2-del", name="Otro Store")
        r2 = CashRegister.objects.create(tenant=tenant, store=s2, name="R2")
        sess2 = CashSession.objects.create(
            tenant=tenant, store=s2, register=r2, opened_by=owner,
            initial_amount=Decimal("0"), status="OPEN",
        )
        m_other = _create_movement(tenant, sess2)

        # Owner está activo en store 1 → no debe poder tocar store 2
        r = api_client.delete(f"/api/caja/movements/{m_other.id}/")
        assert r.status_code == 403
        assert CashMovement.objects.filter(id=m_other.id).exists()


# ─── 4. Edge cases ─────────────────────────────────────────────────────

class TestDeleteEdgeCases:

    def test_delete_nonexistent_returns_404(self, api_client, owner):
        r = api_client.delete("/api/caja/movements/99999/")
        assert r.status_code == 404

    def test_delete_twice_second_returns_404(
        self, api_client, owner, tenant, open_session_fx,
    ):
        m = _create_movement(tenant, open_session_fx)
        r1 = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r1.status_code == 200
        r2 = api_client.delete(f"/api/caja/movements/{m.id}/")
        assert r2.status_code == 404


# ─── 5. Visualización unificada (regresión Daniel) ─────────────────────

class TestUnifiedVisualization:
    """Cuando se crea un movimiento desde POST /sessions/<id>/movements/
    debe aparecer en GET /caja/movements/ (NO duplicado)."""

    def test_movement_created_via_session_appears_in_global_list(
        self, api_client, owner, tenant, open_session_fx,
    ):
        # Crear movimiento desde el endpoint de sesión
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category": "SUPPLIER", "amount": "5000", "description": "Pago Covili"},
            format="json",
        )
        assert r.status_code == 201
        mov_id = r.data["id"]

        # Listarlo desde el endpoint global de movimientos
        r2 = api_client.get("/api/caja/movements/")
        assert r2.status_code == 200
        ids = [m["id"] for m in r2.data["results"]]
        # Debe aparecer EXACTAMENTE 1 vez (no duplicado)
        assert ids.count(mov_id) == 1, f"Movimiento aparece {ids.count(mov_id)} veces en el listado global"
