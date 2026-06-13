"""
Fix auditoría (09/06/26): un tip negativo en el camino legacy reducía el
grand_total a cobrar (subtotal_neto + tip) → subcobro. create_sale ahora
clampa tip a >= 0 para cualquier caller (POS usa safe_decimal que no clampa).
"""
import pytest
from decimal import Decimal

from catalog.models import Product
from inventory.models import StockItem
from sales.services import create_sale


@pytest.mark.django_db
def test_negative_tip_clamped_to_zero(tenant, store, warehouse, owner):
    p = Product.objects.create(tenant=tenant, name="Té", price=Decimal("2000"), is_active=True)
    StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p,
                             on_hand=Decimal("50"), avg_cost=Decimal("500"),
                             stock_value=Decimal("25000"))
    result = create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": p.id, "qty": "1", "unit_price": "2000"}],
        payments_in=[{"method": "cash", "amount": "2000"}],
        tip=Decimal("-500"),
    )
    sale = result["sale"]
    assert sale.tip == Decimal("0.00"), f"tip negativo debió clamparse a 0, quedó {sale.tip}"
    # El total a cobrar no se vio reducido por el tip negativo.
    assert sale.total == Decimal("2000")
