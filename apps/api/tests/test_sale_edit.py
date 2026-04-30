"""
Tests para edición de venta cerrada (Daniel 29/04/26):
- PATCH /sales/{id}/payments/  → reemplaza método y monto de pagos
- PATCH /sales/{id}/tip/        → actualiza propina (libre, no validada
                                   contra payments)

Casos típicos:
- "Cobré débito y marqué efectivo": SaleEditPayments
- "El cliente dejó propina y olvidé sumarla": SaleEditTip

NO incluye edición de cantidades — corregir cantidades requiere anular
la venta entera (anti-fraude).
"""
from decimal import Decimal

import pytest

from inventory.models import StockItem
from sales.models import Sale, SalePayment, SaleTip


# ─── Helpers ─────────────────────────────────────────────────────────────


def _stock(tenant, warehouse, product, qty="100", avg_cost="100"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        stock_value=(Decimal(str(qty)) * Decimal(str(avg_cost))).quantize(Decimal("0.001")),
    )


def _create_sale(api_client, warehouse, product, qty=1, unit_price=1000, tip=0, method="cash"):
    payload = {
        "warehouse_id": warehouse.id,
        "lines": [{"product_id": product.id, "qty": str(qty), "unit_price": str(unit_price)}],
        "payments": [{"method": method, "amount": str(int(qty) * int(unit_price) + int(tip))}],
    }
    if tip > 0:
        payload["tip"] = str(tip)
    r = api_client.post("/api/sales/sales/", payload, format="json")
    assert r.status_code == 201, r.data
    return Sale.objects.get(id=r.data["id"])


# ─── SaleEditPayments ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSaleEditPayments:
    def test_change_method_cash_to_debit(
        self, api_client, tenant, warehouse, product,
    ):
        """Caso típico: el cajero marcó efectivo pero el cliente pagó con débito."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash")

        # Editar a debit
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "debit", "amount": "2000"}]},
            format="json",
        )
        assert r.status_code == 200, r.data

        # Solo debe haber 1 pago, ahora debit
        pays = list(SalePayment.objects.filter(sale=sale))
        assert len(pays) == 1
        assert pays[0].method == "debit"
        assert pays[0].amount == Decimal("2000.00")

    def test_split_payment(
        self, api_client, tenant, warehouse, product,
    ):
        """Cambiar de 1 pago a 2 pagos divididos."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=10000, method="cash")

        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [
                {"method": "cash", "amount": "5000"},
                {"method": "debit", "amount": "5000"},
            ]},
            format="json",
        )
        assert r.status_code == 200
        pays = SalePayment.objects.filter(sale=sale).order_by("amount")
        assert pays.count() == 2
        methods = {p.method for p in pays}
        assert methods == {"cash", "debit"}

    def test_underpayment_below_subtotal_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        """Regla: la suma de pagos debe cubrir AL MENOS el subtotal. La
        propina NO se considera (es libre)."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, tip=200)
        # subtotal $2000, propina $200. Intento pagar $1500 (menos que subtotal).
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "debit", "amount": "1500"}]},
            format="json",
        )
        assert r.status_code == 400
        assert "insuficiente" in str(r.data).lower()

    def test_payment_equals_subtotal_accepted_even_with_tip(
        self, api_client, tenant, warehouse, product,
    ):
        """Pagar EXACTO el subtotal está permitido aunque haya propina.
        La propina se mantiene separada (cliente la dejó por afuera)."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, tip=500)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "debit", "amount": "2000"}]},
            format="json",
        )
        assert r.status_code == 200, r.data
        # La propina sigue intacta
        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")

    def test_invalid_method_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=1000)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "bitcoin", "amount": "1000"}]},
            format="json",
        )
        assert r.status_code == 400
        assert "método" in str(r.data).lower() or "metodo" in str(r.data).lower()

    def test_zero_amount_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=1000)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "cash", "amount": "0"}]},
            format="json",
        )
        assert r.status_code == 400

    def test_void_sale_cannot_be_edited(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=1000)
        api_client.post(f"/api/sales/sales/{sale.id}/void/")
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "debit", "amount": "1000"}]},
            format="json",
        )
        assert r.status_code == 400
        assert "completed" in str(r.data).lower()


# ─── SaleEditTip ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSaleEditTipMethod:
    """Daniel 29/04/26: el dueño puede especificar con qué método se pagó
    cada propina. Soporta split: una venta puede tener N filas SaleTip
    cada una con su método.

    Backward-compat: la API también acepta el formato legacy
    `{tip, tip_method}` y lo traduce a 1 fila SaleTip.
    """

    def test_legacy_tip_with_explicit_method_creates_saletip_row(
        self, api_client, tenant, warehouse, product,
    ):
        """Formato legacy con tip_method explícito → 1 SaleTip con ese método."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="debit")

        # Cliente pagó débito $2000 + dejó $500 cash de propina aparte
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "500", "tip_method": "cash"},
            format="json",
        )
        assert r.status_code == 200, r.data

        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")
        # tip_method legacy queda en "" (la fuente de verdad pasa a SaleTip)
        assert sale.tip_method == ""

        tips = list(SaleTip.objects.filter(sale=sale))
        assert len(tips) == 1
        assert tips[0].method == "cash"
        assert tips[0].amount == Decimal("500.00")

    def test_split_tips_via_new_format(
        self, api_client, tenant, warehouse, product,
    ):
        """Caso Marbrava: cliente paga débito y deja propina dividida en
        $300 cash + $200 transferencia."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="debit")

        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tips": [
                {"method": "cash",     "amount": "300"},
                {"method": "transfer", "amount": "200"},
            ]},
            format="json",
        )
        assert r.status_code == 200, r.data

        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")  # suma denormalizada
        tips = list(SaleTip.objects.filter(sale=sale).order_by("method"))
        assert len(tips) == 2
        assert (tips[0].method, tips[0].amount) == ("cash", Decimal("300.00"))
        assert (tips[1].method, tips[1].amount) == ("transfer", Decimal("200.00"))

    def test_tip_zero_removes_all_saletips(
        self, api_client, tenant, warehouse, product,
    ):
        """Si tip = 0 (legacy o tips=[]), borra todas las filas SaleTip."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash", tip=200)
        # primero dejarlo con tip cash
        api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "200", "tip_method": "cash"},
            format="json",
        )
        assert SaleTip.objects.filter(sale=sale).count() == 1

        # ahora ponerlo en 0 (legacy)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "0"},
            format="json",
        )
        assert r.status_code == 200
        sale.refresh_from_db()
        assert sale.tip == Decimal("0.00")
        assert SaleTip.objects.filter(sale=sale).count() == 0

    def test_empty_tips_list_clears_all(
        self, api_client, tenant, warehouse, product,
    ):
        """tips=[] (lista vacía) también elimina propinas."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash", tip=200)
        api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "200", "tip_method": "cash"},
            format="json",
        )
        assert SaleTip.objects.filter(sale=sale).count() == 1

        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tips": []},
            format="json",
        )
        assert r.status_code == 200
        sale.refresh_from_db()
        assert sale.tip == Decimal("0.00")
        assert SaleTip.objects.filter(sale=sale).count() == 0

    def test_invalid_tip_method_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash")
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "500", "tip_method": "bitcoin"},
            format="json",
        )
        assert r.status_code == 400

    def test_invalid_method_in_split_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        """En formato nuevo, método inválido en cualquier fila rechaza todo."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash")
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tips": [
                {"method": "cash", "amount": "300"},
                {"method": "bitcoin", "amount": "200"},
            ]},
            format="json",
        )
        assert r.status_code == 400

    def test_legacy_no_method_proportional_split(
        self, api_client, tenant, warehouse, product,
    ):
        """Sin tip_method (vacío) → reparto proporcional según SalePayments,
        creando varias SaleTip rows."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        # Venta con split de pagos (cash + debit) para que el reparto cree N filas
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=2000, method="cash")
        # Reemplazar pagos por split
        api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [
                {"method": "cash", "amount": "1000"},
                {"method": "debit", "amount": "1000"},
            ]},
            format="json",
        )
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "300"},
            format="json",
        )
        assert r.status_code == 200
        sale.refresh_from_db()
        assert sale.tip == Decimal("300.00")
        # 50/50 entre cash y debit → 150 / 150
        tips = list(SaleTip.objects.filter(sale=sale).order_by("method"))
        assert len(tips) == 2
        # Suma debe coincidir exacto
        assert sum((t.amount for t in tips), Decimal("0")) == Decimal("300.00")


@pytest.mark.django_db
class TestSaleEditTip:
    def test_add_tip_to_completed_sale(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        # Vendo $1000 con $1500 cash (cliente dejó $500 extra que se incluyó como pago)
        sale = Sale.objects.create(
            tenant=tenant, store=warehouse.store, warehouse=warehouse,
            created_by=warehouse.tenant.users.first() if hasattr(warehouse.tenant, "users") else None,
            subtotal=Decimal("1000"), total=Decimal("1000"), tip=Decimal("0"),
            status="COMPLETED", sale_type="VENTA",
        )
        # workaround: cargar created_by manual si no hay users
        from core.models import User
        if not sale.created_by_id:
            u = User.objects.first()
            sale.created_by = u
            sale.save(update_fields=["created_by"])
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("1500"))

        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "500"},
            format="json",
        )
        assert r.status_code == 200, r.data
        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")
        # Sale.total NO cambia (la propina es separada)
        assert sale.total == Decimal("1000.00")

    def test_tip_can_exceed_payments_freely(
        self, api_client, tenant, warehouse, product,
    ):
        """Daniel 29/04/26: la propina es libre. Puede superar lo que
        cubrirían los pagos sin problema. Caso: cliente paga $1000 con
        débito y deja $500 cash de propina (que el cajero registra en
        sale.tip aunque no esté en payments)."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=1000, method="cash")
        # Total cobrado = $1000. Pongo tip=$500: NO debe rechazarse.
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "500"},
            format="json",
        )
        assert r.status_code == 200, r.data
        sale.refresh_from_db()
        assert sale.tip == Decimal("500.00")
        # Sale.total NO cambia
        assert sale.total == Decimal("1000.00")

    def test_negative_tip_rejected(
        self, api_client, tenant, warehouse, product,
    ):
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        sale = _create_sale(api_client, warehouse, product, qty=1, unit_price=1000)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/tip/",
            {"tip": "-100"},
            format="json",
        )
        assert r.status_code == 400


