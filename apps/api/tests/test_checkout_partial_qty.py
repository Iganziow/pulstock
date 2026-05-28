"""
Tests del fix de cobro parcial intra-line en checkout_order (mesas).

Mario reporto (25/05/26): mesa con 2 chaparritas, cliente quiere pagar
solo 1. Antes el checkbox del PaymentModal solo permitia "todo o nada"
por line — no habia forma de cobrar 1 de 2.

Fix: checkout_order acepta line_qtys={line_id: qty} opcional. Si la qty
es menor a line.qty, hace cobro parcial: crea Sale por esa qty y deja
la OpenOrderLine con el remanente unpaid.
"""
from decimal import Decimal

import pytest

from inventory.models import StockItem
from sales.models import Sale, SalePayment
from tables.models import Table, OpenOrder, OpenOrderLine
from tables.services import checkout_order, CheckoutError


@pytest.fixture
def stockitem_big(db, tenant, product, warehouse_a):
    return StockItem.objects.create(
        tenant=tenant, product=product, warehouse=warehouse_a,
        on_hand=Decimal("100"), avg_cost=Decimal("500.00"),
    )


@pytest.fixture
def open_order_2chaparritas(db, tenant, store, warehouse_a, user, product, stockitem_big):
    """Mesa con 2 chaparritas de $3800 c/u = $7600."""
    table = Table.objects.create(
        tenant=tenant, store=store, name="Test",
        status=Table.STATUS_OPEN,
    )
    order = OpenOrder.objects.create(
        tenant=tenant, store=store, warehouse=warehouse_a,
        table=table, opened_by=user, status=OpenOrder.STATUS_OPEN,
    )
    line = OpenOrderLine.objects.create(
        tenant=tenant, order=order, product=product,
        qty=Decimal("2"), unit_price=Decimal("3800"),
        added_by=user,
    )
    return order, line


@pytest.mark.django_db
class TestCheckoutPartialQty:

    def test_cobrar_1_de_2_chaparritas_deja_remanente_unpaid(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """Mario quiere cobrar 1 chaparrita ($3800). La otra queda en mesa."""
        order, line = open_order_2chaparritas

        result = checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "cash", "amount": "3800"}],
            line_qtys={line.id: 1},
            user=user,
        )

        # Sale creado con 1 unidad
        sale = result["sale"]
        sale_lines = list(sale.lines.all())
        assert len(sale_lines) == 1
        assert sale_lines[0].qty == Decimal("1")
        assert sale_lines[0].unit_price == Decimal("3800.00")
        assert sale.total == Decimal("3800")

        # OpenOrderLine sigue unpaid con qty=1 (la otra chaparrita)
        line.refresh_from_db()
        assert line.is_paid is False
        assert line.qty == Decimal("1.000")

        # Order NO se cierra (todavia tiene line pendiente)
        order.refresh_from_db()
        assert order.status == OpenOrder.STATUS_OPEN

    def test_cobrar_las_2_chaparritas_marca_line_como_pagada(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """Backwards-compat: si line_qtys==line.qty, comportamiento clasico."""
        order, line = open_order_2chaparritas

        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "cash", "amount": "7600"}],
            line_qtys={line.id: 2},
            user=user,
        )

        line.refresh_from_db()
        assert line.is_paid is True
        # qty se mantiene en 2 (NO se decrementa porque pago completo)
        assert line.qty == Decimal("2")

        # Order se cierra (era la unica line)
        order.refresh_from_db()
        assert order.status == OpenOrder.STATUS_CLOSED

    def test_sin_line_qtys_backwards_compat(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """Frontend legacy que NO manda line_qtys → comportamiento previo."""
        order, line = open_order_2chaparritas

        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "cash", "amount": "7600"}],
            # line_qtys NO se pasa
            user=user,
        )

        line.refresh_from_db()
        assert line.is_paid is True

    def test_cobrar_parcial_secuencial_funciona(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """1ra venta: cobra 1 de 2. 2da venta: cobra la otra. Mesa cierra."""
        order, line = open_order_2chaparritas

        # 1ra venta: 1 chaparrita cash
        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "cash", "amount": "3800"}],
            line_qtys={line.id: 1}, user=user,
        )
        line.refresh_from_db()
        assert line.qty == Decimal("1.000")
        assert line.is_paid is False

        # 2da venta: la chaparrita restante con debit
        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "debit", "amount": "3800"}],
            line_qtys={line.id: 1}, user=user,
        )
        line.refresh_from_db()
        assert line.is_paid is True

        order.refresh_from_db()
        assert order.status == OpenOrder.STATUS_CLOSED

        # 2 sales distintas asociadas al mismo order
        sales = Sale.objects.filter(open_order=order)
        assert sales.count() == 2

    def test_qty_excede_disponible_falla(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """Cobrar 3 de una line con qty=2 → CheckoutError."""
        order, line = open_order_2chaparritas

        with pytest.raises(CheckoutError, match="excede"):
            checkout_order(
                order_id=order.id, tenant_id=tenant.id, store_id=store.id,
                mode="partial", line_ids=[line.id],
                payments_in=[{"method": "cash", "amount": "11400"}],
                line_qtys={line.id: 3}, user=user,
            )

    def test_qty_cero_falla(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        order, line = open_order_2chaparritas
        with pytest.raises(CheckoutError, match="debe ser > 0"):
            checkout_order(
                order_id=order.id, tenant_id=tenant.id, store_id=store.id,
                mode="partial", line_ids=[line.id],
                payments_in=[{"method": "cash", "amount": "3800"}],
                line_qtys={line.id: 0}, user=user,
            )

    def test_line_id_como_string_funciona(
        self, tenant, store, warehouse_a, user, open_order_2chaparritas,
    ):
        """JSON envia keys como string. Backend debe aceptar ambas formas."""
        order, line = open_order_2chaparritas

        checkout_order(
            order_id=order.id, tenant_id=tenant.id, store_id=store.id,
            mode="partial", line_ids=[line.id],
            payments_in=[{"method": "cash", "amount": "3800"}],
            line_qtys={str(line.id): "1"},  # string key + string value
            user=user,
        )

        line.refresh_from_db()
        assert line.qty == Decimal("1.000")
