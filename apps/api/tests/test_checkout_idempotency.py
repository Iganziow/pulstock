"""
Fix auditoría (09/06/26): el checkout de mesas (/tables/orders/<id>/checkout/)
no aceptaba idempotency_key. Aunque el doble cobro ya estaba prevenido por
select_for_update + status=OPEN + guardas de líneas pagadas, el retry devolvía
un 404 confuso. Ahora:
  - acepta idempotency_key y lo propaga a create_sale,
  - en el retry devuelve la venta ORIGINAL (idempotent=True), sin duplicar.
"""
import pytest
from decimal import Decimal


@pytest.fixture
def open_order_with_line(api_client, tenant, store, warehouse, product, owner):
    from tables.models import Table, OpenOrder, OpenOrderLine
    from inventory.models import StockItem
    StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={"on_hand": Decimal("100"), "avg_cost": Decimal("500"),
                  "stock_value": Decimal("50000")},
    )
    table = Table.objects.create(tenant=tenant, store=store, name="Checkout Idem")
    order = OpenOrder.objects.create(
        tenant=tenant, table=table, store=store, warehouse=warehouse,
        status="OPEN", opened_by=owner,
    )
    OpenOrderLine.objects.create(
        order=order, tenant=tenant, product=product,
        qty=Decimal("2"), unit_price=Decimal("1000"), added_by=owner,
    )
    return order


@pytest.mark.django_db
class TestCheckoutIdempotency:
    def test_retry_same_key_returns_same_sale_no_duplicate(self, api_client, open_order_with_line):
        from sales.models import Sale
        payload = {
            "mode": "all",
            "payments": [{"method": "cash", "amount": 2000}],
            "idempotency_key": "checkout-key-001",
        }
        r1 = api_client.post(
            f"/api/tables/orders/{open_order_with_line.id}/checkout/", payload, format="json")
        assert r1.status_code == 201, r1.data
        sale_id_1 = r1.data.get("sale_id") or r1.data.get("id")
        assert sale_id_1
        assert Sale.objects.count() == 1

        # Retry con la MISMA key (la orden ya está cerrada): antes daba 404,
        # ahora devuelve la venta original sin duplicar.
        r2 = api_client.post(
            f"/api/tables/orders/{open_order_with_line.id}/checkout/", payload, format="json")
        assert r2.status_code == 201, r2.data
        sale_id_2 = r2.data.get("sale_id") or r2.data.get("id")
        assert sale_id_2 == sale_id_1, "el retry debe devolver la MISMA venta"
        assert r2.data.get("idempotent") is True
        assert Sale.objects.count() == 1, "NO debe crear una segunda venta"

    def test_no_key_closed_order_still_safe(self, api_client, open_order_with_line):
        """Sin idempotency_key: el primer cobro cierra la orden; el retry cae
        en 'orden no encontrada' (404). Sigue sin duplicar (defensa previa)."""
        from sales.models import Sale
        payload = {"mode": "all", "payments": [{"method": "cash", "amount": 2000}]}
        r1 = api_client.post(
            f"/api/tables/orders/{open_order_with_line.id}/checkout/", payload, format="json")
        assert r1.status_code == 201, r1.data
        r2 = api_client.post(
            f"/api/tables/orders/{open_order_with_line.id}/checkout/", payload, format="json")
        assert r2.status_code == 404
        assert Sale.objects.count() == 1, "sin key tampoco se duplica (orden ya cerrada)"
