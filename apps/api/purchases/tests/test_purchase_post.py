import pytest
from decimal import Decimal

from purchases.models import Purchase, PurchaseLine
from inventory.models import StockItem, StockMove

pytestmark = pytest.mark.django_db


def test_purchase_post_applies_stock_and_kardex(
    auth_client, tenant, store, warehouse_a, product, stockitem_a, user
):
    # Arrange: Purchase DRAFT
    p = Purchase.objects.create(
        tenant=tenant,
        store=store,
        warehouse=warehouse_a,
        status="DRAFT",
        created_by=user,
    )

    qty = Decimal("10")
    unit_cost = Decimal("1000")

    # Arrange: Linea de compra (tu modelo exige tenant y tiene line_total_cost)
    PurchaseLine.objects.create(
        tenant=tenant,
        purchase=p,
        product=product,
        qty=qty,
        unit_cost=unit_cost,
        line_total_cost=qty * unit_cost,
        note="",
    )

    # Act: postear
    url = f"/api/purchases/{p.id}/post/"
    r = auth_client.post(url, data={}, format="json")
    assert r.status_code in (200, 201), r.content

    # Assert: estado compra
    p.refresh_from_db()
    assert p.status == "POSTED"

    # Assert: stock valorizado
    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse_a, product=product)
    assert si.on_hand == qty
    assert si.avg_cost == unit_cost
    assert si.stock_value == qty * unit_cost

    # Assert: movimiento kardex
    move = StockMove.objects.filter(
        tenant=tenant,
        warehouse=warehouse_a,
        product=product,
        ref_type="PURCHASE",
        ref_id=p.id,
    ).latest("id")

    assert move.qty == qty
    assert move.cost_snapshot == unit_cost
    assert move.value_delta == qty * unit_cost
