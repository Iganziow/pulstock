"""
Test E2E pre-deploy: combina los cambios pendientes en local que vamos
a deployar juntos:
  1. Cobro parcial intra-line (line_qtys) — fix Mario 25/05/26
  2. Propinas explicitas (tips_in) — Fases A+B+C+D
  3. Cierre de caja correcto con mix legacy + Fase A

Si este test pasa, tenemos alta confianza que el deploy no rompe el
cuadre de caja.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from caja.models import CashRegister, CashSession
from inventory.models import StockItem
from sales.models import Sale, SalePayment, SaleTip
from tables.models import Table, OpenOrder, OpenOrderLine
from tables.services import checkout_order


@pytest.fixture
def register(db, tenant, store):
    return CashRegister.objects.create(
        tenant=tenant, store=store, name="Caja", is_active=True,
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
        data={"initial_amount": initial}, format="json",
    )
    assert resp.status_code in (200, 201)
    return resp.data


def _close_session(client, session_id, counted):
    resp = client.post(
        reverse("caja-session-close", kwargs={"pk": session_id}),
        data={"counted_cash": str(counted)}, format="json",
    )
    assert resp.status_code == 200
    return resp.data


def _live(client, session_id):
    resp = client.get(reverse("caja-session-detail", kwargs={"pk": session_id}))
    return resp.data["live"]


@pytest.mark.django_db
class TestE2EPartialTipsCaja:

    def test_mesa_con_partial_qty_propina_explicita_y_cuadra_caja(
        self, auth_client, owner, tenant, store, warehouse_a, register,
        product, stockitem_big,
    ):
        """
        Escenario completo:
        1. Mario abre caja con $10.000 fondo
        2. Crea mesa con 2 chaparritas + 1 americano
        3. Primer cliente paga 1 chaparrita ($3.800) con cash + tip $200 cash
        4. Segundo cliente paga la otra chaparrita ($3.800) con debit + tip $300 cash
        5. Tercer cliente paga el americano ($2.800) con debit + tip $100 cash
        6. Cierra caja → debe cuadrar exacto.

        Total fisico cash esperado:
          $10.000 (fondo)
          + $3.800 (1ra venta cash)
          + $200 + $300 + $100 (3 propinas cash)
          = $14.400

        Total debit: $3.800 + $2.800 = $6.600 (no toca cash)
        """
        # 1. Abrir caja
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        # 2. Crear mesa con OpenOrder + 2 lines
        table = Table.objects.create(
            tenant=tenant, store=store, name="Mesa Test",
            status=Table.STATUS_OPEN,
        )
        order = OpenOrder.objects.create(
            tenant=tenant, store=store, warehouse=warehouse_a,
            table=table, opened_by=owner, status=OpenOrder.STATUS_OPEN,
        )
        chap_line = OpenOrderLine.objects.create(
            tenant=tenant, order=order, product=product,
            qty=Decimal("2"), unit_price=Decimal("3800"),
            added_by=owner,
        )
        amer_line = OpenOrderLine.objects.create(
            tenant=tenant, order=order, product=product,
            qty=Decimal("1"), unit_price=Decimal("2800"),
            added_by=owner,
        )

        # 3. Primer cliente: 1 de 2 chaparritas, cash + tip cash
        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[chap_line.id],
            payments_in=[{"method": "cash", "amount": "3800"}],
            tip=Decimal("200"),
            tips_in=[{"method": "cash", "amount": "200"}],
            line_qtys={chap_line.id: 1},  # cobra solo 1
            user=owner,
        )
        chap_line.refresh_from_db()
        assert chap_line.qty == Decimal("1.000")
        assert chap_line.is_paid is False

        # 4. Segundo cliente: otra chaparrita, debit + tip cash
        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[chap_line.id],
            payments_in=[{"method": "debit", "amount": "3800"}],
            tip=Decimal("300"),
            tips_in=[{"method": "cash", "amount": "300"}],
            line_qtys={chap_line.id: 1},
            user=owner,
        )
        chap_line.refresh_from_db()
        assert chap_line.is_paid is True  # ya esta toda pagada

        # 5. Tercer cliente: americano, debit + tip cash
        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[amer_line.id],
            payments_in=[{"method": "debit", "amount": "2800"}],
            tip=Decimal("100"),
            tips_in=[{"method": "cash", "amount": "100"}],
            user=owner,
        )

        # Order debe estar CERRADO porque todas las lines estan pagadas
        order.refresh_from_db()
        assert order.status == OpenOrder.STATUS_CLOSED

        # Verificar live antes de cerrar caja
        live = _live(auth_client, sess_id)

        # cash_payments_total = 3800 (1ra venta)
        # cash_tips = 200 + 300 + 100 = 600 (Fase A, fisico aparte)
        # debit_payments_total = 3800 + 2800 = 6600
        # expected_cash = 10000 + 3800 + 600 = 14400
        assert Decimal(live["cash_sales"]) == Decimal("3800"), f"live={live}"
        assert Decimal(live["cash_tips"]) == Decimal("600"), f"live={live}"
        assert Decimal(live["debit_sales"]) == Decimal("6600"), f"live={live}"
        assert Decimal(live["total_tips"]) == Decimal("600"), f"live={live}"
        assert Decimal(live["expected_cash"]) == Decimal("14400.00"), f"live={live}"

        # 6. Cerrar caja con counted exacto
        close = _close_session(auth_client, sess_id, counted="14400")
        assert Decimal(close["counted_cash"]) == Decimal("14400.00")
        assert Decimal(close["difference"]) == Decimal("0.00")

        # 3 ventas distintas vinculadas al order
        sales = Sale.objects.filter(open_order=order)
        assert sales.count() == 3
