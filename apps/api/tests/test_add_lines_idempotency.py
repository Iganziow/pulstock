"""
Tests de idempotency en /tables/orders/<id>/add-lines/.

Caso de uso: WiFi inestable. El frontend manda el confirm pero la
respuesta nunca llega. El cajero reintenta con la misma idempotency_key
→ el backend NO debe duplicar líneas.
"""
import pytest
from decimal import Decimal


@pytest.fixture
def open_order(api_client, tenant, store, warehouse, product, owner):
    from tables.models import Table, OpenOrder
    from inventory.models import StockItem
    StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={"on_hand": Decimal("100"), "avg_cost": Decimal("500")},
    )
    table = Table.objects.create(tenant=tenant, store=store, name="Idem Test")
    order = OpenOrder.objects.create(
        tenant=tenant, table=table, store=store, warehouse=warehouse,
        status="OPEN", opened_by=owner,
    )
    return order


@pytest.mark.django_db
class TestAddLinesIdempotency:
    """Idempotency en confirm de pendientes — Mario (Marbrava)."""

    def test_same_key_does_not_duplicate(self, api_client, open_order, product):
        """1ra request crea N líneas. 2da con misma key NO duplica."""
        from tables.models import OpenOrderLine
        payload = {
            "idempotency_key": "abc-key-001",
            "lines": [
                {"product_id": product.id, "qty": "1", "unit_price": "1000"},
                {"product_id": product.id, "qty": "2", "unit_price": "1000"},
            ],
        }
        # 1ra
        r1 = api_client.post(f"/api/tables/orders/{open_order.id}/add-lines/", payload, format="json")
        assert r1.status_code == 201, r1.data
        count1 = OpenOrderLine.objects.filter(order=open_order).count()
        assert count1 == 2

        # 2da (retry) — misma key
        r2 = api_client.post(f"/api/tables/orders/{open_order.id}/add-lines/", payload, format="json")
        assert r2.status_code == 200, r2.data  # 200 = idempotent retry
        count2 = OpenOrderLine.objects.filter(order=open_order).count()
        assert count2 == 2, f"Se duplicaron! Quedaron {count2} lineas en vez de 2"

    def test_different_keys_create_independent_batches(self, api_client, open_order, product):
        """Si las keys son distintas, son requests legítimos distintos."""
        from tables.models import OpenOrderLine

        # Batch 1
        api_client.post(
            f"/api/tables/orders/{open_order.id}/add-lines/",
            {"idempotency_key": "key-batch-1", "lines": [
                {"product_id": product.id, "qty": "1", "unit_price": "1000"},
            ]}, format="json",
        )
        # Batch 2 (key distinta)
        api_client.post(
            f"/api/tables/orders/{open_order.id}/add-lines/",
            {"idempotency_key": "key-batch-2", "lines": [
                {"product_id": product.id, "qty": "1", "unit_price": "1000"},
            ]}, format="json",
        )
        assert OpenOrderLine.objects.filter(order=open_order).count() == 2

    def test_no_key_legacy_behavior(self, api_client, open_order, product):
        """Sin idempotency_key: comportamiento legacy, cada POST crea
        nuevas lineas (era lo de antes — no rompemos retro-compat)."""
        from tables.models import OpenOrderLine
        payload = {"lines": [{"product_id": product.id, "qty": "1", "unit_price": "1000"}]}

        r1 = api_client.post(f"/api/tables/orders/{open_order.id}/add-lines/", payload, format="json")
        r2 = api_client.post(f"/api/tables/orders/{open_order.id}/add-lines/", payload, format="json")
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert OpenOrderLine.objects.filter(order=open_order).count() == 2

    def test_key_persisted_on_lines(self, api_client, open_order, product):
        """La key queda guardada en cada línea creada (para debug/audit)."""
        from tables.models import OpenOrderLine
        api_client.post(
            f"/api/tables/orders/{open_order.id}/add-lines/",
            {"idempotency_key": "stored-key-xyz", "lines": [
                {"product_id": product.id, "qty": "1", "unit_price": "1000"},
                {"product_id": product.id, "qty": "1", "unit_price": "1000"},
            ]}, format="json",
        )
        lines = list(OpenOrderLine.objects.filter(order=open_order))
        assert all(l.add_lines_batch_key == "stored-key-xyz" for l in lines)
