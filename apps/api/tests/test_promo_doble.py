# -*- coding: utf-8 -*-
"""
tests/test_promo_doble.py — una promocion se descuenta UNA vez.

El POS manda la linea al precio promo (pos/page.tsx) y las mesas la guardan a
precio promo y la pasan tal cual a create_sale. Hasta el 13/10/26,
sales/pricing.py calculaba ademas (precio lleno - precio promo) x qty y lo
RESTABA del bruto, que ya estaba a precio promo: un producto de $1.000 con 30%
quedaba en $400 en vez de $700, y el ultimo pago se recortaba a $400 aunque el
cliente pago $700. Medido en produccion: 2 de las 3 lineas con promo de la
historia, $2.480 registrados de menos.

El test viejo (test_e2e_audit_fixes::TestPromotionEnforcement) cubria solo el
caso raro: el cliente manda el precio lleno por cache vieja.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import StockItem
from sales.models import Sale, SaleLine, SalePayment

D = Decimal


@pytest.fixture
def promo_30(tenant, warehouse, product):
    from promotions.models import Promotion, PromotionProduct
    product.price = D("1000")
    product.save()
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                             on_hand=D("10"), avg_cost=D("300"), stock_value=D("3000"))
    ahora = timezone.now()
    promo = Promotion.objects.create(
        tenant=tenant, name="30 off", discount_type="pct", discount_value=D("30"),
        start_date=ahora - timedelta(days=1), end_date=ahora + timedelta(days=1), is_active=True,
    )
    PromotionProduct.objects.create(promotion=promo, product=product)
    return promo


def _vender(api_client, warehouse, product, unit_price, pago, **linea):
    payload = {
        "warehouse_id": warehouse.id,
        "lines": [{"product_id": product.id, "qty": "1", "unit_price": unit_price, **linea}],
        "payments": [{"method": "cash", "amount": pago}],
    }
    r = api_client.post("/api/sales/sales/", payload, format="json")
    assert r.status_code == 201, r.data
    venta = Sale.objects.get(pk=r.data["id"])
    return venta, SaleLine.objects.get(sale=venta)


@pytest.mark.django_db
class TestPromoUnaVez:
    def test_el_precio_promo_del_pos_no_se_descuenta_otra_vez(
            self, api_client, tenant, warehouse, product, promo_30):
        """El caso NORMAL: el POS ya manda $700."""
        venta, linea = _vender(api_client, warehouse, product, "700", 700)
        assert venta.total == D("700"), "se desconto dos veces: total %s" % venta.total
        assert linea.line_total == D("700")
        assert linea.original_unit_price == D("1000"), "la boleta pierde el 'antes'"
        assert not linea.discount_amount, "el ahorro de la promo no se resta: ya esta en el precio"
        pagado = sum(p.amount for p in SalePayment.objects.filter(sale=venta))
        assert pagado == D("700"), "el pago se recorto a %s" % pagado

    def test_las_dos_rutas_dan_lo_mismo_y_quedan_vinculadas(
            self, api_client, tenant, warehouse, product, promo_30):
        """Precio promo (lo normal) o precio lleno (cache vieja): misma venta, y
        las dos lineas vinculadas a su promocion. Antes la de precio lleno quedaba
        sin vinculo."""
        normal, l_normal = _vender(api_client, warehouse, product, "700", 700)
        vieja, l_vieja = _vender(api_client, warehouse, product, "1000", 700)
        assert normal.total == vieja.total == D("700")
        assert l_normal.line_total == l_vieja.line_total == D("700")
        assert l_normal.promotion_id == l_vieja.promotion_id == promo_30.id

    def test_un_descuento_manual_sigue_restandose(
            self, api_client, tenant, warehouse, product):
        """Control: sin promo, el descuento manual se resta igual que antes."""
        product.price = D("1000")
        product.save()
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=product,
                                 on_hand=D("10"), avg_cost=D("300"), stock_value=D("3000"))
        venta, linea = _vender(api_client, warehouse, product, "1000", 900,
                               discount_type="pct", discount_value="10")
        assert venta.total == D("900")
        assert linea.discount_amount == D("100")
