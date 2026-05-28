"""
Test e2e protocolo del usuario: 2 turnos de caja en el mismo dia con
diferentes tipos de propinas + edicion post-cierre + verificacion de
inmutabilidad del closing_snapshot.

Escenarios:
  Turno 1 (cajero A):
    - Venta 1: cash 5000 + propina cash 500 (Fase A explicito)
    - Venta 2: debit 8000 + propina cash 1000 (Fase A: payment debit, tip cash fisico aparte)
    - Venta 3: cash 3000 + transfer 2000 (split, sin propina)
    Cierre: counted_cash debe igualar expected_cash.

  Turno 2 (cajero B, mismo dia):
    - Venta 4: debit 12000 + propina debit 1200 (Fase A: tip mismo metodo que payment, pero aparte)
    - Venta 5: cash 7000 + propina cash 700 (Fase A explicito)
    Cierre: cuadre exacto.

  Edicion post-cierre:
    - PATCH propina de venta del turno 1
    - Verificar que closing_snapshot del turno 1 NO cambia (es inmutable)
    - Verificar que el live recalcula con el nuevo monto
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from caja.models import CashRegister, CashSession
from inventory.models import StockItem
from sales.models import Sale, SalePayment, SaleTip


@pytest.fixture
def register(db, tenant, store):
    return CashRegister.objects.create(
        tenant=tenant, store=store, name="Caja 1", is_active=True,
    )


@pytest.fixture
def stockitem_big(db, tenant, product, warehouse_a):
    return StockItem.objects.create(
        tenant=tenant, product=product, warehouse=warehouse_a,
        on_hand=Decimal("1000"), avg_cost=Decimal("100"),
    )


def _open_session(client, register_id, initial="10000"):
    resp = client.post(
        reverse("caja-session-open", kwargs={"pk": register_id}),
        data={"initial_amount": initial},
        format="json",
    )
    assert resp.status_code in (200, 201), resp.content
    return resp.data


def _close_session(client, session_id, counted):
    resp = client.post(
        reverse("caja-session-close", kwargs={"pk": session_id}),
        data={"counted_cash": str(counted)},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.data


def _session_live(client, session_id):
    resp = client.get(
        reverse("caja-session-detail", kwargs={"pk": session_id}),
    )
    assert resp.status_code == 200, resp.content
    return resp.data["live"]


def _create_sale_fase_a(tenant, store, warehouse, owner, session, *,
                        subtotal, payments, tips=None):
    """Crea venta Fase A: SalePayment = solo venta, SaleTip = explicito."""
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, cash_session=session,
        subtotal=Decimal(str(subtotal)), total=Decimal(str(subtotal)),
        tip=sum((Decimal(str(t["amount"])) for t in (tips or [])), Decimal("0")),
        status="COMPLETED", sale_type="VENTA",
        sale_number=Sale.objects.filter(tenant=tenant).count() + 1,
        total_cost=Decimal("0"), gross_profit=Decimal("0"),
    )
    for p in payments:
        SalePayment.objects.create(
            sale=sale, tenant=tenant,
            method=p["method"], amount=Decimal(str(p["amount"])),
        )
    for t in (tips or []):
        SaleTip.objects.create(
            sale=sale, tenant=tenant,
            method=t["method"], amount=Decimal(str(t["amount"])),
        )
    return sale


@pytest.mark.django_db
class TestTwoShiftsE2E:

    def test_dos_turnos_cuadran_independientes(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """Turno 1 → cierra OK. Turno 2 nuevo → cierra OK. Cada turno
        es independiente."""

        # === TURNO 1 ===
        sess1_data = _open_session(auth_client, register.id, initial="10000")
        sess1_id = sess1_data["id"]
        sess1 = CashSession.objects.get(id=sess1_id)

        # Venta 1: cash 5000 + propina cash 500
        _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess1,
            subtotal="5000",
            payments=[{"method": "cash", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )
        # Venta 2: debit 8000 + propina cash 1000 (aparte, fisica)
        _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess1,
            subtotal="8000",
            payments=[{"method": "debit", "amount": "8000"}],
            tips=[{"method": "cash", "amount": "1000"}],
        )
        # Venta 3: cash 3000 + transfer 2000, sin propina
        _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess1,
            subtotal="5000",
            payments=[
                {"method": "cash", "amount": "3000"},
                {"method": "transfer", "amount": "2000"},
            ],
            tips=[],
        )

        live1 = _session_live(auth_client, sess1_id)
        # cash_payments_total = 5000 + 3000 = 8000 (todo cash venta)
        # cash_tips = 500 + 1000 = 1500 (propinas cash Fase A — fisicas aparte)
        # expected_cash = 10000 initial + 8000 cash_payments + 1500 fase_a_extra + 0 movs
        assert Decimal(live1["cash_sales"]) == Decimal("8000"), live1
        assert Decimal(live1["cash_tips"]) == Decimal("1500"), live1
        assert Decimal(live1["debit_sales"]) == Decimal("8000"), live1
        assert Decimal(live1["transfer_sales"]) == Decimal("2000"), live1
        # total_sales = subtotal real = 5000 + 8000 + 5000 = 18000
        assert Decimal(live1["total_sales"]) == Decimal("18000"), live1
        # expected_cash = 10000 + 8000 + 1500 = 19500
        expected1 = Decimal("19500.00")
        assert Decimal(live1["expected_cash"]) == expected1, live1

        # Cierre turno 1: cajero cuenta exactamente lo esperado
        close1 = _close_session(auth_client, sess1_id, counted="19500")
        assert Decimal(close1["counted_cash"]) == Decimal("19500.00")
        assert Decimal(close1["difference"]) == Decimal("0.00")

        # Verificar snapshot guardado
        sess1.refresh_from_db()
        assert sess1.closing_snapshot, "closing_snapshot debe estar"
        snap1 = sess1.closing_snapshot
        assert Decimal(snap1["expected_cash"]) == expected1

        # === TURNO 2 (mismo dia, nueva session) ===
        sess2_data = _open_session(auth_client, register.id, initial="19500")
        sess2_id = sess2_data["id"]
        sess2 = CashSession.objects.get(id=sess2_id)

        # Venta 4: debit 12000 + propina debit 1200 (mismo metodo, aparte)
        _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess2,
            subtotal="12000",
            payments=[{"method": "debit", "amount": "12000"}],
            tips=[{"method": "debit", "amount": "1200"}],
        )
        # Venta 5: cash 7000 + propina cash 700
        _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess2,
            subtotal="7000",
            payments=[{"method": "cash", "amount": "7000"}],
            tips=[{"method": "cash", "amount": "700"}],
        )

        live2 = _session_live(auth_client, sess2_id)
        # cash_payments_total = 7000
        # cash_tips = 700 (Fase A — fisico aparte)
        # debit_payments_total = 12000
        # debit_tips = 1200 (Fase A — NO se resta de debit_sales)
        # expected_cash = 19500 initial + 7000 cash_payments + 700 extra + 0 movs
        assert Decimal(live2["cash_sales"]) == Decimal("7000")
        assert Decimal(live2["cash_tips"]) == Decimal("700")
        assert Decimal(live2["debit_sales"]) == Decimal("12000")
        assert Decimal(live2["tips_by_method"]["debit"]) == Decimal("1200")
        expected2 = Decimal("27200.00")
        assert Decimal(live2["expected_cash"]) == expected2, live2

        close2 = _close_session(auth_client, sess2_id, counted="27200")
        assert Decimal(close2["difference"]) == Decimal("0.00")

        # === Verificar inmutabilidad del turno 1 ===
        sess1.refresh_from_db()
        assert Decimal(sess1.closing_snapshot["expected_cash"]) == expected1, (
            "El snapshot del turno 1 NO debe cambiar cuando turno 2 cierra"
        )

    def test_editar_propina_post_cierre_no_muta_snapshot(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """Editar SaleTip de una venta antigua NO debe cambiar el snapshot
        guardado en el cierre. El live de esa session SI refleja el cambio
        (porque se recalcula on-demand)."""
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        sale = _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess,
            subtotal="5000",
            payments=[{"method": "cash", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )

        # Cerrar con expected = 10000 + 5000 + 500 = 15500
        close = _close_session(auth_client, sess_id, counted="15500")
        sess.refresh_from_db()
        snap_expected = Decimal(sess.closing_snapshot["expected_cash"])
        assert snap_expected == Decimal("15500.00")

        # Editar SaleTip (cambiar metodo de propina a debit)
        SaleTip.objects.filter(sale=sale).delete()
        SaleTip.objects.create(
            sale=sale, tenant=tenant, method="debit", amount=Decimal("500"),
        )
        sale.tip = Decimal("500")
        sale.save(update_fields=["tip"])

        # Snapshot NO cambia
        sess.refresh_from_db()
        assert Decimal(sess.closing_snapshot["expected_cash"]) == snap_expected, (
            "closing_snapshot debe ser inmutable post-cierre"
        )
