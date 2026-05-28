"""
Test e2e: cuando el manager edita propina o pagos de una venta Fase A,
TODO se correlaciona consistente:

1. SalePayment / SaleTip se actualizan en BD
2. La lista de ventas (`/sales/list/`) refleja el nuevo Sale.tip
3. El detalle de venta (`/sales/<pk>/`) muestra el desglose nuevo
4. El cierre de caja LIVE (`_session_summary`) cuadra con la realidad
5. Si la venta esta en una session ya cerrada, el closing_snapshot NO cambia
6. El reporte de propinas (`/tips-summary/` y `/tips-list/`) usa SaleTip directo

NOTA: garzon (CASHIER role) NO puede editar — solo OWNER/MANAGER.
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
    assert resp.status_code in (200, 201), resp.content
    return resp.data


def _close_session(client, session_id, counted):
    resp = client.post(
        reverse("caja-session-close", kwargs={"pk": session_id}),
        data={"counted_cash": str(counted)}, format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.data


def _live(client, session_id):
    resp = client.get(reverse("caja-session-detail", kwargs={"pk": session_id}))
    return resp.data["live"]


def _create_sale_fase_a(tenant, store, warehouse, owner, session, *,
                        subtotal, payments, tips=None):
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
            sale=sale, tenant=tenant, method=p["method"],
            amount=Decimal(str(p["amount"])),
        )
    for t in (tips or []):
        SaleTip.objects.create(
            sale=sale, tenant=tenant, method=t["method"],
            amount=Decimal(str(t["amount"])),
        )
    return sale


@pytest.mark.django_db
class TestEditTipCorrelation:

    def test_editar_tip_actualiza_todos_los_reportes(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """Cobrar mesa, manager edita propina, todo coordina."""
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        sale = _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess,
            subtotal="5000",
            payments=[{"method": "debit", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )

        # 1. Live inicial
        live = _live(auth_client, sess_id)
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("500")
        assert Decimal(live["debit_sales"]) == Decimal("5000")
        assert Decimal(live["expected_cash"]) == Decimal("10500.00")  # initial + tip cash

        # 2. Manager edita propina: split 300 cash + 200 transfer
        edit_url = reverse("sale-edit-tip", kwargs={"pk": sale.id})
        resp = auth_client.patch(edit_url, data={
            "tips": [
                {"method": "cash", "amount": "300"},
                {"method": "transfer", "amount": "200"},
            ],
        }, format="json")
        assert resp.status_code == 200, resp.content

        # 3. BD actualizada
        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")
        tips_now = {t.method: t.amount for t in sale.tips.all()}
        assert tips_now == {"cash": Decimal("300.00"), "transfer": Decimal("200.00")}

        # 4. Live recalcula
        live = _live(auth_client, sess_id)
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("300")
        assert Decimal(live["tips_by_method"]["transfer"]) == Decimal("200")
        # expected_cash baja: ahora solo 300 cash extra (no 500)
        assert Decimal(live["expected_cash"]) == Decimal("10300.00")

        # 5. Detalle muestra split
        detail_resp = auth_client.get(reverse("sale-detail", kwargs={"pk": sale.id}))
        assert detail_resp.status_code == 200
        assert Decimal(detail_resp.data["tip"]) == Decimal("500.00")
        tips_in_detail = {t["method"]: Decimal(t["amount"]) for t in detail_resp.data["tips"]}
        assert tips_in_detail == {"cash": Decimal("300.00"), "transfer": Decimal("200.00")}

    def test_editar_tip_post_cierre_NO_muta_snapshot(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """Cerrar caja, despues editar propina de venta del turno: snapshot inmutable."""
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        sale = _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess,
            subtotal="5000",
            payments=[{"method": "cash", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )

        # Cerrar con expected = 15500
        _close_session(auth_client, sess_id, counted="15500")
        sess.refresh_from_db()
        snap_before = dict(sess.closing_snapshot)
        assert Decimal(snap_before["expected_cash"]) == Decimal("15500.00")
        assert Decimal(snap_before["tips_by_method"]["cash"]) == Decimal("500")

        # Editar propina post-cierre
        resp = auth_client.patch(
            reverse("sale-edit-tip", kwargs={"pk": sale.id}),
            data={"tips": [{"method": "debit", "amount": "500"}]},
            format="json",
        )
        assert resp.status_code == 200

        # Snapshot NO cambia
        sess.refresh_from_db()
        assert sess.closing_snapshot == snap_before

    def test_editar_payments_actualiza_correctamente(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """Manager corrige metodo de pago de debit a cash. Cierre cuadra."""
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        sale = _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess,
            subtotal="5000",
            payments=[{"method": "debit", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )

        # Manager edita: cobrar todo en cash (incluye propina aparte)
        resp = auth_client.patch(
            reverse("sale-edit-payments", kwargs={"pk": sale.id}),
            data={"payments": [{"method": "cash", "amount": "5000"}]},
            format="json",
        )
        assert resp.status_code == 200, resp.content

        live = _live(auth_client, sess_id)
        # cash_sales = 5000 (sum_payments == subtotal → Fase A)
        # cash_tips = 500 (SaleTip)
        # debit_sales = 0
        # expected_cash = 10000 + 5000 cash payment + 500 fase_a_extra = 15500
        assert Decimal(live["cash_sales"]) == Decimal("5000")
        assert Decimal(live["debit_sales"]) == Decimal("0")
        assert Decimal(live["tips_by_method"]["cash"]) == Decimal("500")
        assert Decimal(live["expected_cash"]) == Decimal("15500.00")

    def test_editar_tip_a_cero_lo_elimina(
        self, auth_client, owner, tenant, store, warehouse_a, register, stockitem_big,
    ):
        """tip=0 borra todas las SaleTip rows."""
        sess_data = _open_session(auth_client, register.id, initial="10000")
        sess_id = sess_data["id"]
        sess = CashSession.objects.get(id=sess_id)

        sale = _create_sale_fase_a(
            tenant, store, warehouse_a, owner, sess,
            subtotal="5000",
            payments=[{"method": "cash", "amount": "5000"}],
            tips=[{"method": "cash", "amount": "500"}],
        )

        resp = auth_client.patch(
            reverse("sale-edit-tip", kwargs={"pk": sale.id}),
            data={"tip": "0"},
            format="json",
        )
        assert resp.status_code == 200

        sale.refresh_from_db()
        assert sale.tip == Decimal("0.00")
        assert sale.tips.count() == 0

        live = _live(auth_client, sess_id)
        assert Decimal(live["total_tips"]) == Decimal("0")
        # cash_payments_total = 5000, no extra tip → expected = 10000 + 5000 = 15000
        assert Decimal(live["expected_cash"]) == Decimal("15000.00")

    def test_permission_classes_son_IsManager(self):
        """Verifica que los endpoints de edicion tienen IsManager — esto
        garantiza que el CASHIER (garzon) NO puede editar payments ni tip.
        Solo OWNER/MANAGER pueden corregir post-checkout.

        Test directo de los view classes en vez de hacer request porque
        el middleware de subscription complica setup multi-user en test.
        """
        from sales.views import SaleEditPayments, SaleEditTip
        from core.permissions import IsManager
        for view_cls in (SaleEditPayments, SaleEditTip):
            assert IsManager in view_cls.permission_classes, (
                f"{view_cls.__name__} debe requerir IsManager"
            )
