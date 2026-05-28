"""
Tests del management command `migrate_tips_explicit` (Fase C).

Verifica que ventas legacy con propina embebida en SalePayment.amount
se separan correctamente: SalePayment queda con solo la venta, SaleTip
representa la propina explicita.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from sales.models import Sale, SalePayment, SaleTip


def _make_legacy_sale(tenant, store, warehouse, owner, *, subtotal, tip, method="cash"):
    """Helper: crea venta legacy con SalePayment.amount = subtotal + tip."""
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner,
        subtotal=Decimal(str(subtotal)),
        total=Decimal(str(subtotal)),
        tip=Decimal(str(tip)),
        status="COMPLETED", sale_type="VENTA",
        sale_number=Sale.objects.filter(tenant=tenant).count() + 1,
        total_cost=Decimal("0"), gross_profit=Decimal("0"),
    )
    SalePayment.objects.create(
        sale=sale, tenant=tenant,
        method=method,
        amount=Decimal(str(subtotal)) + Decimal(str(tip)),
    )
    return sale


@pytest.mark.django_db
class TestMigrateTipsExplicit:

    def test_dry_run_no_escribe(self, tenant, store, warehouse_a, user):
        sale = _make_legacy_sale(tenant, store, warehouse_a, user,
                                 subtotal="5000", tip="500")
        out = StringIO()
        call_command("migrate_tips_explicit", tenant=tenant.id, stdout=out)

        sale.refresh_from_db()
        payment = sale.payments.get()
        assert payment.amount == Decimal("5500.00"), "Dry-run NO debe modificar"
        assert sale.tips.count() == 0
        assert "DRY-RUN" in out.getvalue()

    def test_apply_separa_propina_de_payment(self, tenant, store, warehouse_a, user):
        sale = _make_legacy_sale(tenant, store, warehouse_a, user,
                                 subtotal="5000", tip="500")
        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())

        sale.refresh_from_db()
        payment = sale.payments.get()
        assert payment.amount == Decimal("5000.00"), (
            "Despues de migracion, SalePayment.amount = solo venta"
        )
        # SaleTip creado con la propina
        tips = list(sale.tips.all())
        assert len(tips) == 1
        assert tips[0].method == "cash"
        assert tips[0].amount == Decimal("500.00")

    def test_split_payments_se_separa_proporcional(
        self, tenant, store, warehouse_a, user,
    ):
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse_a,
            created_by=user,
            subtotal=Decimal("10000"), total=Decimal("10000"),
            tip=Decimal("1000"),
            status="COMPLETED", sale_type="VENTA",
            sale_number=1,
            total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        # Split 25/75: $2750 cash + $8250 debit (suma 11000 = 10000 + 1000)
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("2750"))
        SalePayment.objects.create(sale=sale, tenant=tenant, method="debit", amount=Decimal("8250"))

        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())

        payments = list(sale.payments.order_by("id"))
        # Cash: 2750 - (1000 * 2750/11000) = 2750 - 250 = 2500
        # Debit: 8250 - (1000 * 8250/11000) = 8250 - 750 = 7500
        assert payments[0].amount == Decimal("2500.00")
        assert payments[1].amount == Decimal("7500.00")

        tips_by_method = {t.method: t.amount for t in sale.tips.all()}
        assert tips_by_method == {
            "cash": Decimal("250.00"),
            "debit": Decimal("750.00"),
        }

    def test_no_toca_ventas_fase_a(self, tenant, store, warehouse_a, user):
        """Ventas que YA están en formato Fase A no se modifican."""
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse_a,
            created_by=user,
            subtotal=Decimal("5000"), total=Decimal("5000"),
            tip=Decimal("500"),
            status="COMPLETED", sale_type="VENTA",
            sale_number=2,
            total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        # Fase A: SalePayment.amount = solo venta
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("5000"))
        SaleTip.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("500"))

        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())

        sale.refresh_from_db()
        payment = sale.payments.get()
        assert payment.amount == Decimal("5000"), "Fase A no debe modificarse"
        assert sale.tips.count() == 1  # tip original intacto

    def test_no_toca_ventas_sin_tip(self, tenant, store, warehouse_a, user):
        """Ventas con tip=0 no se procesan."""
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse_a,
            created_by=user,
            subtotal=Decimal("5000"), total=Decimal("5000"),
            tip=Decimal("0"),
            status="COMPLETED", sale_type="VENTA",
            sale_number=3,
            total_cost=Decimal("0"), gross_profit=Decimal("0"),
        )
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("5000"))

        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())

        sale.refresh_from_db()
        assert sale.payments.get().amount == Decimal("5000")
        assert sale.tips.count() == 0

    def test_idempotente(self, tenant, store, warehouse_a, user):
        """Ejecutar el migrate 2 veces no rompe los datos."""
        sale = _make_legacy_sale(tenant, store, warehouse_a, user,
                                 subtotal="5000", tip="500")

        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())
        call_command("migrate_tips_explicit", tenant=tenant.id, apply=True,
                     stdout=StringIO())

        sale.refresh_from_db()
        assert sale.payments.get().amount == Decimal("5000.00"), (
            "Segunda corrida no debe restar de nuevo"
        )
        assert sale.tips.count() == 1
        assert sale.tips.get().amount == Decimal("500.00")
