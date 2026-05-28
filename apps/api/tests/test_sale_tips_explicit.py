"""
Tests Fase A: create_sale acepta tips_in explicito (Fudo-style).

Comportamiento esperado:

- Sin tips_in (legacy): SalePayment.amount incluye propina, SaleTip se crea
  por reparto proporcional o un solo metodo. NO debe romper nada vs hoy.
- Con tips_in: SalePayment.amount = solo venta (sin tip), SaleTip se crea
  exactamente segun lo declarado por el caller (sin heuristica, sin smart-cash).

El frontend legacy actual NO manda tips_in → todos los tests existentes
de ventas/caja deben seguir pasando sin cambio.
"""
from decimal import Decimal

import pytest

from inventory.models import StockItem
from sales.models import Sale, SalePayment, SaleTip
from sales.services import create_sale, SaleValidationError


@pytest.fixture
def stockitem(db, tenant, product, warehouse_a):
    return StockItem.objects.create(
        tenant=tenant, product=product, warehouse=warehouse_a,
        on_hand=Decimal("100"), avg_cost=Decimal("500.00"),
    )


def _build_lines(product, qty=1, unit_price="5000"):
    return [{"product_id": product.id, "qty": str(qty), "unit_price": unit_price}]


@pytest.mark.django_db
class TestBackCompatLegacy:
    """Sin tips_in → identico a comportamiento previo."""

    def test_sin_tips_in_propina_se_atribuye_al_unico_pago(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """1 payment cash, tip 500 sin tips_in → SaleTip cash 500."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="5000"),
            payments_in=[{"method": "cash", "amount": "5500"}],
            tip=Decimal("500"),
            # tips_in NO se pasa → legacy
        )
        sale = result["sale"]
        # SalePayment.amount = subtotal + tip (5000 + 500), recortado al
        # grand_total_to_charge que en legacy incluye tip.
        payment = sale.payments.get()
        assert payment.method == "cash"
        assert payment.amount == Decimal("5500.00")
        # SaleTip creado con el metodo del unico pago
        tip_row = sale.tips.get()
        assert tip_row.method == "cash"
        assert tip_row.amount == Decimal("500.00")
        assert sale.tip == Decimal("500")

    def test_sin_tips_in_split_se_reparte_proporcionalmente(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """2 payments split, tip 1000 sin tips_in → reparto proporcional."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=2, unit_price="5000"),
            # subtotal=10000, tip=1000 → grand_total=11000
            payments_in=[
                {"method": "cash", "amount": "2750"},   # 25% del total
                {"method": "debit", "amount": "8250"},  # 75% del total
            ],
            tip=Decimal("1000"),
        )
        sale = result["sale"]
        # SaleTip dividido proporcionalmente entre cash y debit
        tip_rows = list(sale.tips.order_by("method"))
        assert len(tip_rows) == 2
        # Cash: 1000 * 2750 / 11000 = 250
        # Debit: 1000 - 250 = 750 (la ultima fila absorbe el redondeo)
        by_method = {t.method: t.amount for t in tip_rows}
        assert by_method["cash"] == Decimal("250.00")
        assert by_method["debit"] == Decimal("750.00")


@pytest.mark.django_db
class TestTipsInExplicit:
    """Con tips_in → camino nuevo, sin heuristica."""

    def test_payment_solo_venta_tip_aparte_mismo_metodo(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """Pago cash 5000 + propina cash 500 explicita."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="5000"),
            payments_in=[{"method": "cash", "amount": "5000"}],  # SOLO venta
            tip=Decimal("500"),
            tips_in=[{"method": "cash", "amount": "500"}],
        )
        sale = result["sale"]
        payment = sale.payments.get()
        assert payment.method == "cash"
        assert payment.amount == Decimal("5000.00"), (
            "Con tips_in, SalePayment.amount debe ser SOLO venta, no incluir tip"
        )
        tip_row = sale.tips.get()
        assert tip_row.method == "cash"
        assert tip_row.amount == Decimal("500.00")
        assert sale.tip == Decimal("500")
        assert sale.total == Decimal("5000")

    def test_payment_debit_tip_cash_caso_tipico_cafeteria(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """Cliente paga cuenta con debito, deja propina en efectivo (billete)."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="10000"),
            payments_in=[{"method": "debit", "amount": "10000"}],
            tip=Decimal("1000"),
            tips_in=[{"method": "cash", "amount": "1000"}],
        )
        sale = result["sale"]
        payment = sale.payments.get()
        assert payment.method == "debit"
        assert payment.amount == Decimal("10000.00")
        tip_row = sale.tips.get()
        assert tip_row.method == "cash"
        assert tip_row.amount == Decimal("1000.00")

    def test_tips_in_split_multiple_metodos(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """Propina dividida: 300 cash + 200 transfer (caso real Marbrava)."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="5000"),
            payments_in=[{"method": "debit", "amount": "5000"}],
            tip=Decimal("500"),
            tips_in=[
                {"method": "cash", "amount": "300"},
                {"method": "transfer", "amount": "200"},
            ],
        )
        sale = result["sale"]
        tips_by_method = {t.method: t.amount for t in sale.tips.all()}
        assert tips_by_method == {
            "cash": Decimal("300.00"),
            "transfer": Decimal("200.00"),
        }

    def test_tips_in_amount_cero_se_ignora(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """Items con amount=0 se filtran silenciosamente."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="5000"),
            payments_in=[{"method": "cash", "amount": "5000"}],
            tip=Decimal("500"),
            tips_in=[
                {"method": "cash", "amount": "500"},
                {"method": "debit", "amount": "0"},  # ← ignorado
            ],
        )
        sale = result["sale"]
        tips = list(sale.tips.all())
        assert len(tips) == 1
        assert tips[0].method == "cash"
        assert tips[0].amount == Decimal("500.00")

    def test_tips_in_vacio_con_tip_cero_no_crea_filas(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """tips_in=[] + tip=0 → no crea SaleTip y no falla."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product, qty=1, unit_price="5000"),
            payments_in=[{"method": "cash", "amount": "5000"}],
            tip=Decimal("0"),
            tips_in=[],
        )
        sale = result["sale"]
        assert sale.tips.count() == 0
        assert sale.tip == Decimal("0")


@pytest.mark.django_db
class TestTipsInValidation:
    """tips_in mal formado → SaleValidationError."""

    def test_metodo_invalido_falla(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        with pytest.raises(SaleValidationError, match="invalido"):
            create_sale(
                user=user, tenant_id=tenant.id, store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=_build_lines(product),
                payments_in=[{"method": "cash", "amount": "5000"}],
                tip=Decimal("500"),
                tips_in=[{"method": "bitcoin", "amount": "500"}],
            )

    def test_amount_negativo_falla(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        with pytest.raises(SaleValidationError, match="negativo"):
            create_sale(
                user=user, tenant_id=tenant.id, store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=_build_lines(product),
                payments_in=[{"method": "cash", "amount": "5000"}],
                tip=Decimal("500"),
                tips_in=[{"method": "cash", "amount": "-100"}],
            )

    def test_suma_tips_no_coincide_con_tip_total_falla(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """tip=500 pero tips_in suma 400 → ValidationError."""
        with pytest.raises(SaleValidationError, match="no coincide"):
            create_sale(
                user=user, tenant_id=tenant.id, store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=_build_lines(product),
                payments_in=[{"method": "cash", "amount": "5000"}],
                tip=Decimal("500"),
                tips_in=[{"method": "cash", "amount": "400"}],
            )

    def test_tips_in_no_es_lista_falla(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        with pytest.raises(SaleValidationError, match="lista"):
            create_sale(
                user=user, tenant_id=tenant.id, store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=_build_lines(product),
                payments_in=[{"method": "cash", "amount": "5000"}],
                tip=Decimal("500"),
                tips_in={"method": "cash", "amount": "500"},  # dict, no lista
            )

    def test_item_no_es_dict_falla(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        with pytest.raises(SaleValidationError, match="dict"):
            create_sale(
                user=user, tenant_id=tenant.id, store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=_build_lines(product),
                payments_in=[{"method": "cash", "amount": "5000"}],
                tip=Decimal("500"),
                tips_in=["cash", "500"],  # str, no dict
            )

    def test_tolerancia_1_centavo_rounding(
        self, user, tenant, store, warehouse_a, product, stockitem,
    ):
        """Diferencia <= 1 centavo se acepta (rounding cliente/servidor)."""
        result = create_sale(
            user=user, tenant_id=tenant.id, store_id=store.id,
            warehouse_id=warehouse_a.id,
            lines_in=_build_lines(product),
            payments_in=[{"method": "cash", "amount": "5000"}],
            tip=Decimal("500.00"),
            tips_in=[{"method": "cash", "amount": "499.99"}],  # 1 centavo menos
        )
        # No lanza
        assert result["sale"].tips.count() == 1
