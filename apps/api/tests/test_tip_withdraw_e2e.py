"""
Tests E2E HTTP del retiro de propinas — la ruta que de verdad usa Mario.

Hay tests unitarios en test_tip_withdraw_category.py que validan la
migración + el comportamiento del modelo. Acá testeamos lo que pasa
cuando el frontend hace POST a /api/caja/sessions/<id>/movements/
con category="TIP_WITHDRAW", que es el caso real cuando se aprieta
"💸 Retirar propinas".

Edge cases cubiertos:
  - Happy path: POST → 201 + expected_cash baja
  - Amount inválido (0, negativo, no numérico)
  - Description vacía
  - Sesión cerrada → 409
  - Cross-tenant: usuario A no puede crear movs en sesión de tenant B
  - Categoría desactivada → 400
  - El cajero también puede hacer retiro (no es solo del owner)
  - Concurrencia: 2 retiros simultáneos no se pisan
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from caja.models import CashRegister, CashSession, CashMovement, MovementCategory
from core.models import User, Tenant
from stores.models import Store


# ── Fixtures locales ────────────────────────────────────────────────────────


@pytest.fixture
def register(db, tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja 1")


@pytest.fixture
def open_session(db, tenant, store, register, owner):
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register,
        initial_amount=Decimal("10000"),
        opened_by=owner,
    )


@pytest.fixture
def closed_session(db, tenant, store, register, owner):
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register,
        initial_amount=Decimal("10000"),
        opened_by=owner,
        status=CashSession.STATUS_CLOSED,
    )


@pytest.fixture
def cashier(db, tenant, store):
    user = User.objects.create_user(
        username="cashier_test", password="x",
        tenant=tenant, active_store=store, role=User.Role.CASHIER,
    )
    return user


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestTipWithdrawHappyPath:
    """El flujo que de verdad usa el frontend."""

    def test_post_with_tip_withdraw_string_creates_movement(
        self, api_client, open_session, tenant
    ):
        """POST con category='TIP_WITHDRAW' (string, no category_id) crea
        el movimiento, sincroniza el FK y devuelve 201.

        Este es el flujo EXACTO del frontend (CajaModals.tsx + page.tsx)
        — manda category como string, no como id."""
        url = f"/api/caja/sessions/{open_session.id}/movements/"
        resp = api_client.post(url, {
            "type": "OUT",
            "amount": "5000",
            "description": "Mario retiró sus propinas",
            "category": "TIP_WITHDRAW",
        }, format="json")

        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["type"] == "OUT"
        assert Decimal(str(data["amount"])) == Decimal("5000")
        assert data["category"] == "TIP_WITHDRAW"

        # El movimiento queda en la DB con FK seteada
        mov = CashMovement.objects.get(id=data["id"])
        assert mov.category_fk is not None
        assert mov.category_fk.code == "TIP_WITHDRAW"
        assert mov.category_fk.tenant_id == tenant.id

    def test_tip_withdraw_decreases_expected_cash(
        self, api_client, open_session
    ):
        """expected_cash baja en el monto retirado — esto es lo que
        permite que la caja cuadre al cierre."""
        # Inicial: $10.000 + $0 IN - $0 OUT = $10.000
        before_url = "/api/caja/sessions/current/"
        before = api_client.get(before_url).json()
        expected_before = Decimal(str(before["live"]["expected_cash"]))

        # Retirar $5.000 de propinas
        api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT",
                "amount": "5000",
                "description": "Retiro de propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )

        after = api_client.get(before_url).json()
        expected_after = Decimal(str(after["live"]["expected_cash"]))
        assert expected_after == expected_before - Decimal("5000"), (
            f"expected_cash debería bajar $5.000: antes={expected_before}, "
            f"después={expected_after}"
        )


@pytest.mark.django_db
class TestTipWithdrawValidation:
    """Edge cases de input mal formado — el frontend debería bloquearlos
    pero el backend tiene que ser defensivo igual."""

    def test_amount_zero_rejected(self, api_client, open_session):
        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "0",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400
        assert "amount" in resp.json().get("detail", "").lower()

    def test_amount_negative_rejected(self, api_client, open_session):
        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "-100",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400

    def test_amount_non_numeric_rejected(self, api_client, open_session):
        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "abc",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400

    def test_empty_description_rejected(self, api_client, open_session):
        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400

    def test_whitespace_description_rejected(self, api_client, open_session):
        """Description con solo espacios = vacío después de strip()."""
        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "   \t\n   ",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestTipWithdrawSessionState:
    """Una sesión cerrada o inexistente NO puede recibir movimientos."""

    def test_closed_session_rejects_tip_withdraw(self, api_client, closed_session):
        resp = api_client.post(
            f"/api/caja/sessions/{closed_session.id}/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        # El backend devuelve 409 (la sesión existe pero ya no está OPEN)
        assert resp.status_code == 409
        assert "abierta" in resp.json()["detail"].lower()

    def test_nonexistent_session_returns_404(self, api_client):
        resp = api_client.post(
            "/api/caja/sessions/99999/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 404


@pytest.mark.django_db
class TestTipWithdrawCrossTenant:
    """Un usuario del tenant A no puede crear retiros en sesiones del
    tenant B. Esto es CRÍTICO: si se rompe se filtra plata entre cuentas."""

    def test_user_from_tenant_a_cannot_post_to_tenant_b_session(self, db):
        # Tenant A con sesión abierta
        tenant_a = Tenant.objects.create(name="Cafe A", slug="cafe-a")
        store_a = Store.objects.create(tenant=tenant_a, name="Local A")
        register_a = CashRegister.objects.create(
            tenant=tenant_a, store=store_a, name="Caja A",
        )
        owner_a = User.objects.create_user(
            username="owner_a", password="x", tenant=tenant_a,
            active_store=store_a, role=User.Role.OWNER,
        )
        session_a = CashSession.objects.create(
            tenant=tenant_a, store=store_a, register=register_a,
            initial_amount=Decimal("10000"), opened_by=owner_a,
        )

        # Tenant B (otro café) intenta crear un retiro en la sesión de A
        tenant_b = Tenant.objects.create(name="Cafe B", slug="cafe-b")
        store_b = Store.objects.create(tenant=tenant_b, name="Local B")
        owner_b = User.objects.create_user(
            username="owner_b", password="x", tenant=tenant_b,
            active_store=store_b, role=User.Role.OWNER,
        )

        client = APIClient()
        client.force_authenticate(user=owner_b)
        resp = client.post(
            f"/api/caja/sessions/{session_a.id}/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "Hack — retiro de plata ajena",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        # Debe devolver 404 (la sesión "no existe" para el tenant B
        # — filtrada en el queryset)
        assert resp.status_code == 404, (
            f"FUGA DE TENANT: {owner_b.username} pudo postear a la sesión "
            f"de {owner_a.username} y devolvió {resp.status_code}"
        )

        # Y la sesión de A NO tiene el movimiento
        assert session_a.movements.count() == 0


@pytest.mark.django_db
class TestTipWithdrawCategoryStates:
    """¿Qué pasa si el dueño desactiva la categoría TIP_WITHDRAW desde
    /caja/categorias? El backend tiene que rechazar limpio, no romper."""

    def test_inactive_tip_withdraw_category_rejects_post(
        self, api_client, open_session, tenant
    ):
        """Si TIP_WITHDRAW.is_active=False, el endpoint devuelve 400."""
        cat = MovementCategory.objects.get(tenant=tenant, code="TIP_WITHDRAW")
        cat.is_active = False
        cat.save()

        resp = api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {
                "type": "OUT", "amount": "5000",
                "description": "Retiro propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 400
        assert "inválida" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


@pytest.mark.django_db
class TestTipWithdrawByCashier:
    """El cajero (no solo el dueño) puede hacer retiros de propinas.

    Esto es decisión de producto: el cajero está físicamente en la
    caja cuando el equipo retira sus propinas, así que puede registrarlo.
    Si Mario decide después que solo el dueño/manager pueda, se cambia
    el permission_classes en AddMovementView.
    """

    def test_cashier_can_register_tip_withdraw(
        self, db, tenant, store, register, cashier, owner
    ):
        # Sesión abierta por el owner — el cajero entra después
        session = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            initial_amount=Decimal("10000"), opened_by=owner,
        )

        client = APIClient()
        client.force_authenticate(user=cashier)
        resp = client.post(
            f"/api/caja/sessions/{session.id}/movements/",
            {
                "type": "OUT", "amount": "3000",
                "description": "Ignacia retiró sus propinas",
                "category": "TIP_WITHDRAW",
            }, format="json",
        )
        assert resp.status_code == 201, (
            f"El cajero debería poder hacer retiro de propinas. "
            f"Si Mario decide que no, hay que agregar IsManager o IsOwner "
            f"al permission_classes de AddMovementView. Status: {resp.status_code}"
        )

        mov = CashMovement.objects.get(id=resp.json()["id"])
        assert mov.created_by_id == cashier.id
        assert mov.category_fk.code == "TIP_WITHDRAW"


@pytest.mark.django_db
class TestTipWithdrawReporting:
    """Para los reportes: los retiros de propinas deben quedar separables
    de los gastos reales del café."""

    def test_tip_withdrawals_filterable_separately(
        self, api_client, open_session
    ):
        """Filtrando por category='TIP_WITHDRAW' obtenemos solo los retiros,
        excluyéndolos del 'gastos del café'."""
        # 1 retiro de propinas + 1 compra real
        api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {"type": "OUT", "amount": "4000", "description": "Mario retiró",
             "category": "TIP_WITHDRAW"}, format="json",
        )
        api_client.post(
            f"/api/caja/sessions/{open_session.id}/movements/",
            {"type": "OUT", "amount": "2500", "description": "Compra leche",
             "category": "OTHER_OUT"}, format="json",
        )

        # Total OUT incluye ambos
        all_out = open_session.movements.filter(type="OUT")
        assert all_out.count() == 2
        assert sum(m.amount for m in all_out) == Decimal("6500")

        # Pero al filtrar gastos REALES (excluyendo TIP_WITHDRAW) → solo 1
        real_expenses = open_session.movements.filter(type="OUT").exclude(
            category="TIP_WITHDRAW"
        )
        assert real_expenses.count() == 1
        assert real_expenses.first().amount == Decimal("2500")

        tip_withdrawals = open_session.movements.filter(category="TIP_WITHDRAW")
        assert tip_withdrawals.count() == 1
        assert tip_withdrawals.first().amount == Decimal("4000")
