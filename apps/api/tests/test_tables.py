"""
tests/test_tables.py — Comprehensive tests for the tables module.
"""
import pytest
from decimal import Decimal

from tables.models import Table, OpenOrder, OpenOrderLine
from inventory.models import StockItem
from sales.models import Sale, SalePayment


URL_TABLES = "/api/tables/tables/"
URL_COUNTER = "/api/tables/counter-order/"


def _table_url(pk):
    return f"/api/tables/tables/{pk}/"


def _open_url(pk):
    return f"/api/tables/tables/{pk}/open/"


def _order_url(pk):
    return f"/api/tables/tables/{pk}/order/"


def _order_detail_url(order_id):
    return f"/api/tables/orders/{order_id}/"


def _add_lines_url(order_id):
    return f"/api/tables/orders/{order_id}/add-lines/"


def _delete_line_url(order_id, line_id):
    return f"/api/tables/orders/{order_id}/lines/{line_id}/"


def _checkout_url(order_id):
    return f"/api/tables/orders/{order_id}/checkout/"


def _cancel_url(order_id):
    return f"/api/tables/orders/{order_id}/cancel/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_table(api_client, name="Mesa 1", capacity=4, zone="", is_counter=False):
    return api_client.post(URL_TABLES, {
        "name": name,
        "capacity": capacity,
        "zone": zone,
        "is_counter": is_counter,
    }, format="json")


def _open_order(api_client, table_id, warehouse_id=None, customer_name=""):
    body = {}
    if warehouse_id:
        body["warehouse_id"] = warehouse_id
    if customer_name:
        body["customer_name"] = customer_name
    return api_client.post(_open_url(table_id), body)


def _add_lines(api_client, order_id, lines):
    return api_client.post(_add_lines_url(order_id), {"lines": lines}, format="json")


def _ensure_stock(tenant, warehouse, product, on_hand="100.000", avg_cost="500.000"):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        defaults={
            "on_hand": Decimal(on_hand),
            "avg_cost": Decimal(avg_cost),
            "stock_value": (Decimal(on_hand) * Decimal(avg_cost)).quantize(Decimal("0.000")),
        },
    )
    return si


# ═══════════════════════════════════════════════════════════════════════════
# TABLE CRUD
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTableCreate:
    def test_create_table(self, api_client):
        resp = _create_table(api_client, name="Mesa 1", capacity=6, zone="Salón")
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Mesa 1"
        assert data["capacity"] == 6
        assert data["zone"] == "Salón"
        assert data["status"] == "FREE"
        assert data["is_active"] is True
        assert data["is_counter"] is False
        assert data["active_order"] is None

    def test_create_counter_table(self, api_client):
        resp = _create_table(api_client, name="Mostrador 1", is_counter=True)
        assert resp.status_code == 201
        assert resp.json()["is_counter"] is True

    def test_create_duplicate_name_returns_409(self, api_client):
        _create_table(api_client, name="Mesa Dup")
        resp = _create_table(api_client, name="Mesa Dup")
        assert resp.status_code == 409

    def test_create_without_name_returns_400(self, api_client):
        resp = api_client.post(URL_TABLES, {"name": ""})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestTableList:
    def test_list_tables(self, api_client):
        _create_table(api_client, name="Mesa A")
        _create_table(api_client, name="Mesa B")
        resp = api_client.get(URL_TABLES)
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "Mesa A" in names
        assert "Mesa B" in names

    def test_list_excludes_inactive(self, api_client):
        r = _create_table(api_client, name="Mesa Inactiva")
        table_id = r.json()["id"]
        api_client.patch(_table_url(table_id), {"is_active": False}, format="json")
        resp = api_client.get(URL_TABLES)
        names = [t["name"] for t in resp.json()]
        assert "Mesa Inactiva" not in names


@pytest.mark.django_db
class TestTableUpdate:
    def test_update_name_and_capacity(self, api_client):
        r = _create_table(api_client, name="Original")
        pk = r.json()["id"]
        resp = api_client.patch(_table_url(pk), {"name": "Renombrada", "capacity": 8}, format="json")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renombrada"
        assert resp.json()["capacity"] == 8

    def test_update_zone(self, api_client):
        r = _create_table(api_client, name="ZoneTest")
        pk = r.json()["id"]
        resp = api_client.patch(_table_url(pk), {"zone": "Terraza"}, format="json")
        assert resp.status_code == 200
        assert resp.json()["zone"] == "Terraza"

    def test_deactivate_table(self, api_client):
        r = _create_table(api_client, name="Desactivar")
        pk = r.json()["id"]
        resp = api_client.patch(_table_url(pk), {"is_active": False}, format="json")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_update_nonexistent_returns_404(self, api_client):
        resp = api_client.patch(_table_url(99999), {"name": "X"}, format="json")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# OPEN ORDER
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOpenOrder:
    def test_open_order_on_free_table(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Open")
        table_id = r.json()["id"]

        resp = _open_order(api_client, table_id, warehouse_id=warehouse.id)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "OPEN"
        assert int(data["warehouse_id"]) == warehouse.id
        assert data["lines"] == []

        # Table status should now be OPEN
        t = Table.objects.get(id=table_id)
        assert t.status == Table.STATUS_OPEN

    def test_open_order_with_customer_name(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Cliente")
        table_id = r.json()["id"]

        resp = _open_order(api_client, table_id, warehouse_id=warehouse.id, customer_name="Juan Pérez")
        assert resp.status_code == 201
        assert resp.json()["customer_name"] == "Juan Pérez"

    def test_open_order_on_occupied_table_returns_409(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Ocu")
        table_id = r.json()["id"]

        _open_order(api_client, table_id, warehouse_id=warehouse.id)
        resp = _open_order(api_client, table_id, warehouse_id=warehouse.id)
        assert resp.status_code == 409

    def test_open_order_auto_selects_warehouse(self, api_client, warehouse):
        """When no warehouse_id is given, uses first active warehouse for the store."""
        r = _create_table(api_client, name="Mesa Auto WH")
        table_id = r.json()["id"]

        resp = _open_order(api_client, table_id)
        assert resp.status_code == 201
        assert resp.json()["warehouse_id"] == warehouse.id


# ═══════════════════════════════════════════════════════════════════════════
# GET ACTIVE ORDER
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestActiveOrder:
    def test_get_active_order(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Active")
        table_id = r.json()["id"]
        open_resp = _open_order(api_client, table_id, warehouse_id=warehouse.id)
        order_id = open_resp.json()["id"]

        resp = api_client.get(_order_url(table_id))
        assert resp.status_code == 200
        assert resp.json()["id"] == order_id
        assert "lines" in resp.json()

    def test_get_active_order_no_order_returns_404(self, api_client):
        r = _create_table(api_client, name="Mesa Sin Orden")
        table_id = r.json()["id"]
        resp = api_client.get(_order_url(table_id))
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# ADD LINES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAddLines:
    def test_add_single_line(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Lines")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 2, "unit_price": "1500.00"},
        ])
        assert resp.status_code == 201
        lines = resp.json()["lines"]
        assert len(lines) == 1
        assert lines[0]["product_id"] == product.id
        assert lines[0]["qty"] == "2.000"
        assert lines[0]["unit_price"] == "1500.00"
        assert lines[0]["is_paid"] is False
        assert lines[0]["is_cancelled"] is False

    def test_add_multiple_lines(self, api_client, warehouse, product, product_b):
        r = _create_table(api_client, name="Mesa Multi")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1},
            {"product_id": product_b.id, "qty": 3},
        ])
        assert resp.status_code == 201
        assert len(resp.json()["lines"]) == 2

    def test_add_line_with_note(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Nota")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "note": "Sin cebolla"},
        ])
        assert resp.status_code == 201
        assert resp.json()["lines"][0]["note"] == "Sin cebolla"

    def test_add_line_uses_product_price_when_omitted(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Default Price")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1},
        ])
        assert resp.status_code == 201
        assert resp.json()["lines"][0]["unit_price"] == str(product.price)

    def test_add_lines_empty_list_returns_400(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Empty")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [])
        assert resp.status_code == 400

    def test_add_line_invalid_product_returns_400(self, api_client, warehouse):
        r = _create_table(api_client, name="Mesa Bad Prod")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = _add_lines(api_client, order_id, [
            {"product_id": 99999, "qty": 1},
        ])
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# DELETE (CANCEL) LINE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDeleteLine:
    def test_cancel_unpaid_line(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Cancel")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        line_id = OpenOrderLine.objects.filter(order_id=order_id).first().id
        resp = api_client.delete(_delete_line_url(order_id, line_id))
        assert resp.status_code == 200

        # Verify soft cancel
        line = OpenOrderLine.objects.get(id=line_id)
        assert line.is_cancelled is True
        assert line.cancelled_at is not None

        # Response includes full order data
        assert "lines" in resp.json()

    def test_cancel_paid_line_returns_404(self, api_client, warehouse, product, tenant):
        """Paid lines cannot be cancelled."""
        r = _create_table(api_client, name="Mesa Paid")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        line = OpenOrderLine.objects.filter(order_id=order_id).first()
        line.is_paid = True
        line.save(update_fields=["is_paid"])

        resp = api_client.delete(_delete_line_url(order_id, line.id))
        assert resp.status_code == 404

    def test_cancel_already_cancelled_returns_404(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa DblCancel")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        line_id = OpenOrderLine.objects.filter(order_id=order_id).first().id
        api_client.delete(_delete_line_url(order_id, line_id))

        # Second cancel should fail
        resp = api_client.delete(_delete_line_url(order_id, line_id))
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# CHECKOUT
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCheckoutAll:
    def test_checkout_all_lines(self, api_client, warehouse, product, tenant):
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa Checkout")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 2, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "2000.00"}],
        }, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == "2000.00"
        assert data["lines_count"] == 1

        # Order should be closed
        order = OpenOrder.objects.get(id=order_id)
        assert order.status == OpenOrder.STATUS_CLOSED

        # Table should be free
        table = Table.objects.get(id=table_id)
        assert table.status == Table.STATUS_FREE

        # Lines should be marked as paid
        lines = OpenOrderLine.objects.filter(order_id=order_id)
        assert all(l.is_paid for l in lines)

    def test_checkout_creates_sale(self, api_client, warehouse, product, tenant):
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa Sale")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "1000.00"}],
        }, format="json")
        assert resp.status_code == 201

        sale_id = resp.json()["id"]
        sale = Sale.objects.get(id=sale_id)
        assert sale.total == Decimal("1000.00")
        assert sale.status == Sale.STATUS_COMPLETED

    def test_checkout_with_multiple_payment_methods(self, api_client, warehouse, product, tenant):
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa MultiPay")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 2, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [
                {"method": "cash", "amount": "1000.00"},
                {"method": "card", "amount": "1000.00"},
            ],
        }, format="json")
        assert resp.status_code == 201

        sale_id = resp.json()["id"]
        payments = SalePayment.objects.filter(sale_id=sale_id)
        assert payments.count() == 2
        methods = set(p.method for p in payments)
        assert methods == {"cash", "card"}


@pytest.mark.django_db
class TestCheckoutPartial:
    def test_checkout_partial_lines(self, api_client, warehouse, product, product_b, tenant):
        _ensure_stock(tenant, warehouse, product)
        _ensure_stock(tenant, warehouse, product_b)

        r = _create_table(api_client, name="Mesa Partial")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
            {"product_id": product_b.id, "qty": 1, "unit_price": "500.00"},
        ])

        lines = list(OpenOrderLine.objects.filter(order_id=order_id).order_by("id"))
        first_line_id = lines[0].id

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "partial",
            "line_ids": [first_line_id],
            "payments": [{"method": "debit", "amount": "1000.00"}],
        }, format="json")
        assert resp.status_code == 201

        # First line paid, second unpaid
        lines[0].refresh_from_db()
        lines[1].refresh_from_db()
        assert lines[0].is_paid is True
        assert lines[1].is_paid is False

        # Order stays open
        order = OpenOrder.objects.get(id=order_id)
        assert order.status == OpenOrder.STATUS_OPEN

        # Table stays open
        table = Table.objects.get(id=table_id)
        assert table.status == Table.STATUS_OPEN

    def test_partial_then_all_closes_order(self, api_client, warehouse, product, product_b, tenant):
        _ensure_stock(tenant, warehouse, product)
        _ensure_stock(tenant, warehouse, product_b)

        r = _create_table(api_client, name="Mesa PartAll")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
            {"product_id": product_b.id, "qty": 1, "unit_price": "500.00"},
        ])

        lines = list(OpenOrderLine.objects.filter(order_id=order_id).order_by("id"))

        # Pay first line
        api_client.post(_checkout_url(order_id), {
            "mode": "partial",
            "line_ids": [lines[0].id],
            "payments": [{"method": "cash", "amount": "1000.00"}],
        }, format="json")

        # Pay remaining
        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "500.00"}],
        }, format="json")
        assert resp.status_code == 201

        order = OpenOrder.objects.get(id=order_id)
        assert order.status == OpenOrder.STATUS_CLOSED

        table = Table.objects.get(id=table_id)
        assert table.status == Table.STATUS_FREE


@pytest.mark.django_db
class TestCheckoutWithTip:
    def test_checkout_with_tip(self, api_client, warehouse, product, tenant):
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa Tip")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "1200.00"}],
            "tip": "200.00",
        }, format="json")
        assert resp.status_code == 201

        sale = Sale.objects.get(id=resp.json()["id"])
        assert sale.tip == Decimal("200.00")
        # Tip is NOT added to total
        assert sale.total == Decimal("1000.00")


# ═══════════════════════════════════════════════════════════════════════════
# CANCEL ORDER
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCancelOrder:
    def test_cancel_order_with_all_lines_cancelled(self, api_client, warehouse, product):
        """Can cancel order when all lines have been individually cancelled."""
        r = _create_table(api_client, name="Mesa CancelOrd")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        # Cancel the line first
        line_id = OpenOrderLine.objects.filter(order_id=order_id).first().id
        api_client.delete(_delete_line_url(order_id, line_id))

        resp = api_client.post(_cancel_url(order_id))
        assert resp.status_code == 200

        order = OpenOrder.objects.get(id=order_id)
        assert order.status == OpenOrder.STATUS_CLOSED

        table = Table.objects.get(id=table_id)
        assert table.status == Table.STATUS_FREE

    def test_cancel_order_no_lines(self, api_client, warehouse):
        """Can cancel an order with no lines at all."""
        r = _create_table(api_client, name="Mesa NoLines")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]

        resp = api_client.post(_cancel_url(order_id))
        assert resp.status_code == 200

        order = OpenOrder.objects.get(id=order_id)
        assert order.status == OpenOrder.STATUS_CLOSED

    def test_cancel_order_with_paid_lines_returns_409(self, api_client, warehouse, product, tenant):
        """Cannot cancel an order that has paid lines."""
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa PaidCancel")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        # Pay the line via checkout
        api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "1000.00"}],
        }, format="json")

        # Re-open scenario: order is already closed, but let's test the guard directly
        # Create a new order with a paid line
        r2 = _create_table(api_client, name="Mesa PaidCancel2")
        table_id2 = r2.json()["id"]
        order_id2 = _open_order(api_client, table_id2, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id2, [
            {"product_id": product.id, "qty": 1, "unit_price": "500.00"},
        ])

        # Manually mark line as paid (simulating partial checkout)
        line = OpenOrderLine.objects.filter(order_id=order_id2, is_cancelled=False).first()
        line.is_paid = True
        line.save(update_fields=["is_paid"])

        resp = api_client.post(_cancel_url(order_id2))
        assert resp.status_code == 409

    def test_cancel_order_with_active_unpaid_items_returns_409(self, api_client, warehouse, product):
        """Cannot cancel an order with active unpaid items (must cancel them first)."""
        r = _create_table(api_client, name="Mesa ActiveItems")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_cancel_url(order_id))
        assert resp.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# COUNTER ORDER
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCounterOrder:
    def test_counter_order_creates_table_and_order(self, api_client, warehouse):
        resp = api_client.post(URL_COUNTER, {}, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "OPEN"

        # Verify the table was created as counter
        order = OpenOrder.objects.get(id=data["id"])
        table = order.table
        assert table.is_counter is True
        assert table.status == Table.STATUS_OPEN

    def test_counter_order_with_customer_name(self, api_client, warehouse):
        resp = api_client.post(URL_COUNTER, {"customer_name": "María"}, format="json")
        assert resp.status_code == 201
        assert resp.json()["customer_name"] == "María"

    def test_counter_order_reuses_free_counter_table(self, api_client, warehouse, tenant, store):
        """Uses an existing free counter table instead of creating a new one."""
        counter = Table.objects.create(
            tenant=tenant, store=store, name="Mostrador Existente",
            capacity=1, is_counter=True, status=Table.STATUS_FREE,
        )

        resp = api_client.post(URL_COUNTER, {}, format="json")
        assert resp.status_code == 201

        order = OpenOrder.objects.get(id=resp.json()["id"])
        assert order.table_id == counter.id

    def test_counter_order_creates_new_when_all_busy(self, api_client, warehouse, tenant, store):
        """Creates a new counter table when all existing counter tables are busy."""
        counter = Table.objects.create(
            tenant=tenant, store=store, name="Mostrador Ocupado",
            capacity=1, is_counter=True, status=Table.STATUS_OPEN,
        )

        resp = api_client.post(URL_COUNTER, {}, format="json")
        assert resp.status_code == 201

        order = OpenOrder.objects.get(id=resp.json()["id"])
        assert order.table_id != counter.id
        assert order.table.is_counter is True


# ═══════════════════════════════════════════════════════════════════════════
# ORDER DETAIL
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOrderDetail:
    def test_get_order_detail(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Detail")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 2, "unit_price": "1000.00"},
        ])

        resp = api_client.get(_order_detail_url(order_id))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == order_id
        assert len(data["lines"]) == 1
        assert "subtotal_unpaid" in data
        assert data["subtotal_unpaid"] == "2000.00"

    def test_get_order_detail_not_found(self, api_client):
        resp = api_client.get(_order_detail_url(99999))
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES & INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEdgeCases:
    def test_subtotal_unpaid_excludes_cancelled_lines(self, api_client, warehouse, product, product_b):
        r = _create_table(api_client, name="Mesa Subtotal")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
            {"product_id": product_b.id, "qty": 1, "unit_price": "500.00"},
        ])

        # Cancel the first line
        first_line = OpenOrderLine.objects.filter(order_id=order_id).order_by("id").first()
        api_client.delete(_delete_line_url(order_id, first_line.id))

        resp = api_client.get(_order_detail_url(order_id))
        assert resp.json()["subtotal_unpaid"] == "500.00"

    def test_checkout_no_unpaid_lines_returns_error(self, api_client, warehouse, product, tenant):
        """Checkout with all lines cancelled returns error."""
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa NoUnpaid")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        # Cancel the only line
        line_id = OpenOrderLine.objects.filter(order_id=order_id).first().id
        api_client.delete(_delete_line_url(order_id, line_id))

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "1000.00"}],
        }, format="json")
        # Should fail because no unpaid lines exist
        assert resp.status_code in (400, 404)

    def test_table_list_shows_active_order_summary(self, api_client, warehouse, product):
        r = _create_table(api_client, name="Mesa Summary")
        table_id = r.json()["id"]
        _open_order(api_client, table_id, warehouse_id=warehouse.id)
        order_id = OpenOrder.objects.filter(table_id=table_id).first().id
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 2, "unit_price": "750.00"},
        ])

        resp = api_client.get(URL_TABLES)
        tables = resp.json()
        mesa = next(t for t in tables if t["id"] == table_id)
        assert mesa["status"] == "OPEN"
        assert mesa["active_order"] is not None
        assert mesa["active_order"]["items_count"] == 1
        assert Decimal(mesa["active_order"]["subtotal"]) == Decimal("1500")

    def test_checkout_debit_payment(self, api_client, warehouse, product, tenant):
        """Verify debit payment method works."""
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa Debit")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "debit", "amount": "1000.00"}],
        }, format="json")
        assert resp.status_code == 201

        sale_id = resp.json()["id"]
        payment = SalePayment.objects.get(sale_id=sale_id)
        assert payment.method == "debit"

    def test_checkout_transfer_payment(self, api_client, warehouse, product, tenant):
        """Verify transfer payment method works."""
        _ensure_stock(tenant, warehouse, product)

        r = _create_table(api_client, name="Mesa Transfer")
        table_id = r.json()["id"]
        order_id = _open_order(api_client, table_id, warehouse_id=warehouse.id).json()["id"]
        _add_lines(api_client, order_id, [
            {"product_id": product.id, "qty": 1, "unit_price": "1000.00"},
        ])

        resp = api_client.post(_checkout_url(order_id), {
            "mode": "all",
            "payments": [{"method": "transfer", "amount": "1000.00"}],
        }, format="json")
        assert resp.status_code == 201

        sale_id = resp.json()["id"]
        payment = SalePayment.objects.get(sale_id=sale_id)
        assert payment.method == "transfer"
