"""
Tests para la categoría 'TIP_WITHDRAW' (Retiro de propinas).

Mario reportó (06/05/26) que al retirar propinas en efectivo la caja
quedaba descuadrada o el retiro se mezclaba con gastos del café.
Solución: una categoría dedicada que separa retiros de propinas de
los gastos reales del negocio.
"""
import pytest

from caja.models import MovementCategory, CashMovement, CashSession
from core.models import Tenant


@pytest.mark.django_db
class TestTipWithdrawCategorySeed:
    """La categoría TIP_WITHDRAW debe existir para todos los tenants."""

    def test_existing_tenant_has_tip_withdraw_category(self, tenant):
        """Por la migración 0005, el tenant ya viene con TIP_WITHDRAW."""
        cat = MovementCategory.objects.filter(
            tenant=tenant, code="TIP_WITHDRAW"
        ).first()
        assert cat is not None
        assert cat.label == "Retiro de propinas"
        assert cat.type == "OUT"
        assert cat.is_default_template is True
        assert cat.is_active is True

    def test_new_tenant_gets_tip_withdraw_category_via_signal(self, db):
        """Cuando se crea un Tenant nuevo, el signal popula TIP_WITHDRAW
        junto con las demás default categories."""
        new_tenant = Tenant.objects.create(name="Nuevo café", slug="nuevo-cafe")
        cat = MovementCategory.objects.filter(
            tenant=new_tenant, code="TIP_WITHDRAW"
        ).first()
        assert cat is not None, (
            "El signal debería haber creado TIP_WITHDRAW automáticamente. "
            "Si falla, probablemente alguien actualizó signals.py sin "
            "incluir TIP_WITHDRAW en DEFAULT_CATEGORIES."
        )
        assert cat.type == "OUT"


@pytest.mark.django_db
class TestTipWithdrawAffectsExpectedCash:
    """El retiro de propinas baja el expected_cash, que es lo que hace
    que la caja cuadre cuando alguien retira sus propinas físicamente."""

    def test_movement_with_tip_withdraw_category_is_a_normal_out_movement(
        self, tenant, store, owner
    ):
        """Un movimiento OUT con categoría TIP_WITHDRAW se comporta igual
        que cualquier otro egreso a nivel de cálculo de caja: baja el
        expected_cash. La diferencia es solo de categorización (reportes)."""
        from decimal import Decimal
        from caja.models import CashRegister

        register = CashRegister.objects.create(tenant=tenant, store=store, name="Caja 1")
        session = CashSession.objects.create(
            tenant=tenant, store=store, register=register,
            initial_amount=Decimal("10000"),
            opened_by=owner,
        )

        cat_tip = MovementCategory.objects.get(tenant=tenant, code="TIP_WITHDRAW")
        cat_other = MovementCategory.objects.get(tenant=tenant, code="OTHER_OUT")

        # Crear un retiro de propinas y un egreso normal del mismo monto
        CashMovement.objects.create(
            tenant=tenant, session=session, type="OUT",
            amount=Decimal("5000"), description="Mario retiró sus propinas",
            category="TIP_WITHDRAW", category_fk=cat_tip,
            created_by=owner,
        )
        CashMovement.objects.create(
            tenant=tenant, session=session, type="OUT",
            amount=Decimal("3000"), description="Compra de leche",
            category="OTHER_OUT", category_fk=cat_other,
            created_by=owner,
        )

        # Ambos movimientos pesan igual en el expected_cash (8000 OUT total)
        out_total = sum(
            m.amount for m in session.movements.filter(type="OUT")
        )
        assert out_total == Decimal("8000")

        # Pero al filtrar por categoría TIP_WITHDRAW vs gastos reales:
        tip_withdrawals = session.movements.filter(category="TIP_WITHDRAW")
        real_expenses = session.movements.filter(type="OUT").exclude(category="TIP_WITHDRAW")
        assert tip_withdrawals.count() == 1
        assert real_expenses.count() == 1
        assert tip_withdrawals.first().amount == Decimal("5000")
