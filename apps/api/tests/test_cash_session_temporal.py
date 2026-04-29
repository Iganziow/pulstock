"""
Tests para el fix del cierre de caja: ahora suma TODAS las ventas del store
en el rango temporal (opened_at → closed_at), no solo las que tienen FK
cash_session = session.

Bug reportado por Daniel 29/04/26: el cierre filtraba por
`Sale.cash_session_id == session.id`. Si una venta se hacía con la caja
cerrada (cash_session=NULL), nunca aparecía en NINGÚN cierre. Marbrava
27-abr tenía $6.764 en propinas huérfanas que el dueño no veía.

Fix: el cierre representa el efectivo físico que pasó por el local entre
apertura y cierre, sin importar si la venta tenía FK asignado.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from caja.models import CashRegister, CashSession
from caja.views import _session_summary
from sales.models import Sale, SalePayment


def _make_register(tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja test")


def _open_session(tenant, store, register, owner, initial="100000", at=None):
    s = CashSession.objects.create(
        tenant=tenant, store=store, register=register,
        opened_by=owner, initial_amount=Decimal(initial),
        status=CashSession.STATUS_OPEN,
    )
    if at:
        CashSession.objects.filter(id=s.id).update(opened_at=at)
        s.refresh_from_db()
    return s


def _make_sale(tenant, store, warehouse, owner, *,
               total, tip="0", method="cash", at=None,
               cash_session=None):
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal(str(total)),
        total=Decimal(str(total)), tip=Decimal(str(tip)),
        status="COMPLETED", sale_type="VENTA",
        cash_session=cash_session,
    )
    if at:
        Sale.objects.filter(id=sale.id).update(created_at=at)
        sale.refresh_from_db()
    SalePayment.objects.create(
        sale=sale, tenant=tenant, method=method,
        amount=Decimal(str(total)) + Decimal(str(tip)),
    )
    return sale


@pytest.mark.django_db
class TestSessionSummaryTemporalRange:
    """El summary del cierre suma TODAS las ventas del store en el rango
    temporal, incluyendo las que no tenían cash_session asignado."""

    def test_orphan_sales_in_range_counted(
        self, tenant, store, warehouse, owner,
    ):
        """Venta sin cash_session pero dentro del rango → debe entrar al summary."""
        register = _make_register(tenant, store)
        # Sesión abierta hace 2 horas
        open_at = timezone.now() - timedelta(hours=2)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        # Venta huérfana 1 hora después de abrir (sin cash_session asignado)
        when = timezone.now() - timedelta(hours=1)
        _make_sale(tenant, store, warehouse, owner, total="5000", tip="500",
                   method="cash", at=when, cash_session=None)

        summary = _session_summary(session)
        # cash_payments_total = 5500 (5000 + 500 propina)
        # cash_sales = 5500 - 500 = 5000
        assert Decimal(summary["cash_sales"]) == Decimal("5000.00")
        # Total tips = 500
        assert Decimal(summary["total_tips"]) == Decimal("500")
        # Expected = inicial + cash_payments = 100000 + 5500
        assert Decimal(summary["expected_cash"]) == Decimal("105500.00")

    def test_sales_before_open_excluded(
        self, tenant, store, warehouse, owner,
    ):
        """Venta ANTES del opened_at NO entra al summary."""
        register = _make_register(tenant, store)
        open_at = timezone.now() - timedelta(hours=1)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        # Venta hace 3 horas (antes de abrir)
        before = timezone.now() - timedelta(hours=3)
        _make_sale(tenant, store, warehouse, owner, total="5000", tip="0",
                   method="cash", at=before)

        summary = _session_summary(session)
        # No debe contar
        assert Decimal(summary["cash_sales"]) == Decimal("0")
        assert Decimal(summary["expected_cash"]) == Decimal("100000.00")

    def test_other_store_excluded(
        self, tenant, store, warehouse, owner,
    ):
        """Ventas de OTRO store no se cuentan aunque estén en el rango."""
        from stores.models import Store
        from core.models import Warehouse
        store2 = Store.objects.create(tenant=tenant, name="Local 2")
        warehouse2 = Warehouse.objects.create(tenant=tenant, store=store2, name="Bod 2")

        register = _make_register(tenant, store)
        open_at = timezone.now() - timedelta(hours=1)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        # Venta del store2 dentro del rango
        when = timezone.now() - timedelta(minutes=30)
        _make_sale(tenant, store2, warehouse2, owner, total="9999", tip="0",
                   method="cash", at=when)

        summary = _session_summary(session)
        assert Decimal(summary["cash_sales"]) == Decimal("0")

    def test_void_excluded(self, tenant, store, warehouse, owner):
        """Ventas VOID NO se cuentan."""
        register = _make_register(tenant, store)
        open_at = timezone.now() - timedelta(hours=1)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        when = timezone.now() - timedelta(minutes=30)
        sale = _make_sale(tenant, store, warehouse, owner, total="5000", tip="0",
                          method="cash", at=when)
        Sale.objects.filter(id=sale.id).update(status="VOID")

        summary = _session_summary(session)
        assert Decimal(summary["cash_sales"]) == Decimal("0")

    def test_multiple_sales_mixed_assignment(
        self, tenant, store, warehouse, owner,
    ):
        """Algunas ventas con cash_session asignado, otras NULL — todas
        cuentan si están en el rango."""
        register = _make_register(tenant, store)
        open_at = timezone.now() - timedelta(hours=2)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        when1 = timezone.now() - timedelta(hours=1, minutes=30)
        when2 = timezone.now() - timedelta(hours=1)
        # Una con FK asignado
        _make_sale(tenant, store, warehouse, owner, total="3000", tip="0",
                   method="debit", at=when1, cash_session=session)
        # Otra huérfana
        _make_sale(tenant, store, warehouse, owner, total="2000", tip="0",
                   method="debit", at=when2, cash_session=None)

        summary = _session_summary(session)
        # debit_sales = 3000 + 2000 = 5000
        assert Decimal(summary["debit_sales"]) == Decimal("5000.00")


@pytest.mark.django_db
class TestCloseSessionAdoptsOrphans:
    """Al cerrar la sesión, las ventas huérfanas del rango se asocian a esta
    sesión vía FK para dejar la BD consistente."""

    def test_close_assigns_orphans_in_range(
        self, api_client, tenant, store, warehouse, owner,
    ):
        register = _make_register(tenant, store)
        open_at = timezone.now() - timedelta(hours=1)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)

        # 2 huérfanas dentro del rango + 1 fuera
        in_range_when = timezone.now() - timedelta(minutes=30)
        out_of_range_when = timezone.now() - timedelta(hours=3)
        s1 = _make_sale(tenant, store, warehouse, owner, total="1000", tip="0",
                        method="cash", at=in_range_when, cash_session=None)
        s2 = _make_sale(tenant, store, warehouse, owner, total="2000", tip="0",
                        method="debit", at=in_range_when, cash_session=None)
        s3 = _make_sale(tenant, store, warehouse, owner, total="9000", tip="0",
                        method="cash", at=out_of_range_when, cash_session=None)

        # Cerrar
        r = api_client.post(
            f"/api/caja/sessions/{session.id}/close/",
            {"counted_cash": "100000"},
            format="json",
        )
        assert r.status_code == 200, r.data

        # s1 y s2 (en rango) ahora tienen cash_session=session
        s1.refresh_from_db(); s2.refresh_from_db(); s3.refresh_from_db()
        assert s1.cash_session_id == session.id
        assert s2.cash_session_id == session.id
        # s3 (fuera de rango) sigue huérfana
        assert s3.cash_session_id is None

    def test_close_doesnt_steal_other_session_sales(
        self, api_client, tenant, store, warehouse, owner,
    ):
        """Si la venta YA tiene cash_session asignado a otra sesión vieja,
        NO se le quita (defensa: el cierre solo adopta huérfanas, nunca
        roba a otra sesión)."""
        register = _make_register(tenant, store)
        # Sesión vieja ya cerrada
        old = CashSession.objects.create(
            tenant=tenant, store=store, register=register, opened_by=owner,
            initial_amount=Decimal("0"), status=CashSession.STATUS_CLOSED,
            closed_by=owner, counted_cash=Decimal("0"),
            expected_cash=Decimal("0"), difference=Decimal("0"),
        )
        open_at = timezone.now() - timedelta(hours=1)
        session = _open_session(tenant, store, register, owner, "100000", at=open_at)
        # Venta dentro del rango pero con FK a la sesión vieja
        when = timezone.now() - timedelta(minutes=30)
        s1 = _make_sale(tenant, store, warehouse, owner, total="1000", tip="0",
                        method="cash", at=when, cash_session=old)

        api_client.post(
            f"/api/caja/sessions/{session.id}/close/",
            {"counted_cash": "100000"},
            format="json",
        )
        s1.refresh_from_db()
        # Sigue asociada a la vieja, NO se cambió
        assert s1.cash_session_id == old.id
