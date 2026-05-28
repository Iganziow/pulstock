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


# ─── Auto-migración legacy → Fase A vía edición ─────────────────────────


@pytest.mark.django_db
class TestEditLegacyAutoMigratesToFaseA:
    """27/05/26 — El frontend (DetailPanel) ahora pre-rellena el modal de
    edición de pagos con el monto NETO de venta (sin propina embebida) en
    lugar del legacy mezclado.

    Antes: SalePayment(debit, 5280) con SaleTip(debit, 480) — sum_pay > total.
    Ahora al editar (incluso sin cambios reales) → SalePayment(debit, 4800),
    SaleTip intacta — sum_pay == total. Es la misma migración que hace
    `migrate_tips_explicit.py` pero on-demand cuando un manager toca la venta.

    Estos tests aseguran que:
      1. El backend acepta el escenario (no rompe).
      2. SaleTip queda intacta (la propina NO se duplica ni se pierde).
      3. Sale.tip NO cambia.
      4. El total cobrado al cliente (Sale.total + Sale.tip) sigue igual.
    """

    def test_edit_legacy_payment_to_net_preserves_tip(
        self, api_client, tenant, warehouse, product,
    ):
        """Venta legacy: payment $5280 mezclado con propina $480. Manager
        edita pagos al monto neto $4800. SaleTip queda intacta."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        # Simular venta LEGACY a mano (no via API porque ahora Fase A es
        # default). subtotal=$4800, tip=$480, payment_amount=$5280 mezclado.
        from core.models import User
        owner = User.objects.first()
        sale = Sale.objects.create(
            tenant=tenant, store=warehouse.store, warehouse=warehouse,
            created_by=owner,
            subtotal=Decimal("4800"), total=Decimal("4800"),
            tip=Decimal("480"),
            status="COMPLETED", sale_type="VENTA",
        )
        SalePayment.objects.create(
            sale=sale, tenant=tenant, method="debit",
            amount=Decimal("5280"),  # ← legacy mezclado
        )
        SaleTip.objects.create(
            sale=sale, tenant=tenant, method="debit",
            amount=Decimal("480"),
        )

        # Sanity check pre-edición: sum_payments > total (legacy)
        assert sum(p.amount for p in SalePayment.objects.filter(sale=sale)) == Decimal("5280")

        # Manager edita el pago al monto NETO (lo que el nuevo modal pre-rellena)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [{"method": "debit", "amount": "4800"}]},
            format="json",
        )
        assert r.status_code == 200, r.data

        # Post-edición: payment ahora es Fase A (== total), SaleTip intacta
        pays = list(SalePayment.objects.filter(sale=sale))
        assert len(pays) == 1
        assert pays[0].method == "debit"
        assert pays[0].amount == Decimal("4800.00")

        tips = list(SaleTip.objects.filter(sale=sale))
        assert len(tips) == 1
        assert tips[0].method == "debit"
        assert tips[0].amount == Decimal("480.00")

        # Sale.tip NO cambia. Total cobrado al cliente sigue siendo $5280
        # (4800 venta + 480 propina) — exactamente lo mismo que antes.
        sale.refresh_from_db()
        assert sale.tip == Decimal("480.00")
        assert sale.total == Decimal("4800.00")

    def test_edit_legacy_with_split_payment_to_net_preserves_tip(
        self, api_client, tenant, warehouse, product,
    ):
        """Caso split: legacy con 2 pagos prorrateados al neto via edición."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        from core.models import User
        owner = User.objects.first()
        sale = Sale.objects.create(
            tenant=tenant, store=warehouse.store, warehouse=warehouse,
            created_by=owner,
            subtotal=Decimal("10000"), total=Decimal("10000"),
            tip=Decimal("1000"),
            status="COMPLETED", sale_type="VENTA",
        )
        # Legacy: 2 pagos que suman $11000 (10000 venta + 1000 tip mezclado)
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash",  amount=Decimal("5500"))
        SalePayment.objects.create(sale=sale, tenant=tenant, method="debit", amount=Decimal("5500"))
        SaleTip.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("1000"))

        # Frontend prorratea: cash $5500 → $5000, debit $5500 → $5000
        # (último ajusta para sumar 10000 exacto)
        r = api_client.patch(
            f"/api/sales/sales/{sale.id}/payments/",
            {"payments": [
                {"method": "cash",  "amount": "5000"},
                {"method": "debit", "amount": "5000"},
            ]},
            format="json",
        )
        assert r.status_code == 200, r.data

        # Suma de pagos ahora == total (Fase A)
        total_pays = sum(p.amount for p in SalePayment.objects.filter(sale=sale))
        assert total_pays == Decimal("10000.00")

        # SaleTip intacta
        tips = list(SaleTip.objects.filter(sale=sale))
        assert len(tips) == 1
        assert tips[0].amount == Decimal("1000.00")

        sale.refresh_from_db()
        assert sale.tip == Decimal("1000.00")
        assert sale.total == Decimal("10000.00")

    def test_edit_fase_a_payment_no_op_round_trip(
        self, api_client, tenant, warehouse, product,
    ):
        """Venta Fase A (nueva): payment ya es neto. Editar sin cambios
        debe ser no-op (los amounts ya coinciden)."""
        _stock(tenant, warehouse, product, qty="10", avg_cost="500")
        # Crear venta Fase A via API normal (con tips_in explícito)
        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": product.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "debit", "amount": "3000"}],
            "tip": "500",
            "tips": [{"method": "cash", "amount": "500"}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        # SalePayment ya es neto ($3000)
        pays_pre = list(SalePayment.objects.filter(sale_id=sale_id))
        assert len(pays_pre) == 1
        assert pays_pre[0].amount == Decimal("3000.00")

        # Edición "no-op" (frontend manda el mismo neto)
        r = api_client.patch(
            f"/api/sales/sales/{sale_id}/payments/",
            {"payments": [{"method": "debit", "amount": "3000"}]},
            format="json",
        )
        assert r.status_code == 200

        # Todo intacto
        pays_post = list(SalePayment.objects.filter(sale_id=sale_id))
        assert len(pays_post) == 1
        assert pays_post[0].amount == Decimal("3000.00")
        tips = list(SaleTip.objects.filter(sale_id=sale_id))
        assert len(tips) == 1
        assert tips[0].method == "cash"
        assert tips[0].amount == Decimal("500.00")


