"""
Comprehensive tests for the inventory module.

Endpoints tested:
  POST /api/inventory/adjust/
  POST /api/inventory/receive/
  POST /api/inventory/issue/
  GET  /api/inventory/stock/?warehouse_id=
  GET  /api/inventory/moves/?warehouse_id=
  POST /api/inventory/transfer/
  GET  /api/inventory/kardex/?warehouse_id=&product_id=
"""
import pytest
from decimal import Decimal

from core.models import Warehouse
from inventory.models import StockItem, StockMove


URL_ADJUST = "/api/inventory/adjust/"
URL_RECEIVE = "/api/inventory/receive/"
URL_ISSUE = "/api/inventory/issue/"
URL_STOCK = "/api/inventory/stock/"
URL_MOVES = "/api/inventory/moves/"
URL_TRANSFER = "/api/inventory/transfer/"
URL_KARDEX = "/api/inventory/kardex/"


# ── helpers ──────────────────────────────────────────────
def _seed_stock(tenant, warehouse, product, on_hand, avg_cost=Decimal("0.000")):
    """Create or update a StockItem with specific values."""
    si, _ = StockItem.objects.update_or_create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        defaults={
            "on_hand": on_hand,
            "avg_cost": avg_cost,
            "stock_value": on_hand * avg_cost,
        },
    )
    return si


# ==========================================================
# ADJUST
# ==========================================================
@pytest.mark.django_db
class TestStockAdjust:
    """POST /api/inventory/adjust/"""

    def test_positive_adjust_creates_stock(self, api_client, tenant, warehouse, product):
        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "note": "Initial load",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("10.000")

        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
        assert si.on_hand == Decimal("10.000")

        # A StockMove record must exist
        move = StockMove.objects.filter(
            tenant=tenant, warehouse=warehouse, product=product, move_type=StockMove.ADJ,
        ).first()
        assert move is not None
        assert move.qty == Decimal("10.000")
        assert move.ref_type == "ADJUST"

    def test_negative_adjust_reduces_stock(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("20.000"), Decimal("100.000"))

        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-5.000",
            "note": "Shrinkage",
        })
        assert resp.status_code == 201
        assert Decimal(resp.json()["new_stock"]) == Decimal("15.000")

    def test_negative_adjust_beyond_stock_returns_409(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("3.000"))

        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-10.000",
        })
        assert resp.status_code == 409
        assert "Insufficient" in resp.json()["detail"]

    def test_cost_only_adjust_qty_zero_with_new_avg_cost(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))

        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "0",
            "new_avg_cost": "150.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("10.000")  # qty unchanged
        assert Decimal(data["avg_cost"]) == Decimal("150.000")
        assert Decimal(data["stock_value"]) == Decimal("1500.000")  # 10 * 150

    def test_qty_zero_without_new_avg_cost_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "0",
        })
        assert resp.status_code == 400

    def test_adjust_with_new_avg_cost_and_positive_qty(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("5.000"), Decimal("100.000"))

        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
            "new_avg_cost": "200.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("10.000")
        assert Decimal(data["avg_cost"]) == Decimal("200.000")
        assert Decimal(data["stock_value"]) == Decimal("2000.000")

    def test_adjust_creates_move_with_cost_snapshot(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("50.000"))

        api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-3.000",
        })

        move = StockMove.objects.filter(
            tenant=tenant, warehouse=warehouse, product=product, move_type=StockMove.ADJ,
        ).order_by("-id").first()
        assert move is not None
        assert move.cost_snapshot == Decimal("50.000")
        assert move.value_delta == Decimal("-150.000")  # -3 * 50


# ==========================================================
# RECEIVE
# ==========================================================
@pytest.mark.django_db
class TestStockReceive:
    """POST /api/inventory/receive/"""

    def test_receive_with_unit_cost_recalculates_avg(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))

        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "200.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("20.000")
        # weighted avg: (10*100 + 10*200) / 20 = 150
        assert Decimal(data["avg_cost"]) == Decimal("150.000")
        assert Decimal(data["stock_value"]) == Decimal("3000.000")

    def test_receive_without_unit_cost_keeps_avg(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))

        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("15.000")
        assert Decimal(data["avg_cost"]) == Decimal("100.000")  # unchanged

    def test_receive_qty_zero_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "0",
        })
        assert resp.status_code == 400

    def test_receive_negative_qty_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-5",
        })
        assert resp.status_code == 400

    def test_receive_creates_in_move(self, api_client, tenant, warehouse, product):
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "7.000",
            "unit_cost": "50.000",
        })
        assert resp.status_code == 201
        move_id = resp.json()["move_id"]
        move = StockMove.objects.get(id=move_id)
        assert move.move_type == StockMove.IN
        assert move.qty == Decimal("7.000")
        assert move.unit_cost == Decimal("50.000")
        assert move.ref_type == "RECEIVE"
        assert move.cost_snapshot == Decimal("50.000")
        assert move.value_delta == Decimal("350.000")  # 7 * 50

    def test_receive_on_empty_stock_sets_avg_cost(self, api_client, tenant, warehouse, product):
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "250.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["avg_cost"]) == Decimal("250.000")
        assert Decimal(data["stock_value"]) == Decimal("2500.000")


# ==========================================================
# ISSUE
# ==========================================================
@pytest.mark.django_db
class TestStockIssue:
    """POST /api/inventory/issue/"""

    @pytest.mark.parametrize("reason", ["MERMA", "VENCIDO", "USO_INTERNO", "OTRO"])
    def test_issue_valid_reasons(self, api_client, tenant, warehouse, product, reason):
        _seed_stock(tenant, warehouse, product, Decimal("20.000"), Decimal("100.000"))

        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
            "reason": reason,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["issue_reason"] == reason
        # stock refreshed each parametrize run via _seed_stock update_or_create
        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
        assert si.on_hand == Decimal("15.000")

    def test_issue_insufficient_stock_returns_409(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("2.000"))

        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "reason": "MERMA",
        })
        assert resp.status_code == 409
        assert "Insufficient" in resp.json()["detail"]

    def test_issue_invalid_reason_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "1.000",
            "reason": "INVALID_REASON",
        })
        assert resp.status_code == 400

    def test_issue_creates_out_move_with_cost(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("80.000"))

        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "3.000",
            "reason": "MERMA",
        })
        assert resp.status_code == 201
        move = StockMove.objects.get(id=resp.json()["move_id"])
        assert move.move_type == StockMove.OUT
        assert move.cost_snapshot == Decimal("80.000")
        assert move.value_delta == Decimal("-240.000")  # -(3 * 80)

    def test_issue_zero_qty_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "0",
            "reason": "MERMA",
        })
        assert resp.status_code == 400

    def test_issue_updates_stock_value(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))
        # stock_value = 10 * 100 = 1000

        api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "4.000",
            "reason": "VENCIDO",
        })
        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
        assert si.on_hand == Decimal("6.000")
        # stock_value should be 1000 - (4*100) = 600
        assert si.stock_value == Decimal("600.000")


# ==========================================================
# TRANSFER
# ==========================================================
@pytest.mark.django_db
class TestStockTransfer:
    """POST /api/inventory/transfer/"""

    @pytest.fixture
    def warehouse_b(self, tenant, store):
        obj, _ = Warehouse.objects.get_or_create(
            tenant=tenant,
            store=store,
            name="Bodega Secundaria",
        )
        return obj

    def test_transfer_moves_stock(self, api_client, tenant, warehouse, warehouse_b, product):
        _seed_stock(tenant, warehouse, product, Decimal("20.000"), Decimal("100.000"))

        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [{"product_id": product.id, "qty": "8.000"}],
        }, format="json")
        assert resp.status_code == 201

        si_from = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
        si_to = StockItem.objects.get(tenant=tenant, warehouse=warehouse_b, product=product)
        assert si_from.on_hand == Decimal("12.000")
        assert si_to.on_hand == Decimal("8.000")

    def test_transfer_insufficient_stock_returns_409(self, api_client, tenant, warehouse, warehouse_b, product):
        _seed_stock(tenant, warehouse, product, Decimal("3.000"))

        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [{"product_id": product.id, "qty": "10.000"}],
        }, format="json")
        assert resp.status_code == 409

    def test_transfer_same_warehouse_returns_400(self, api_client, warehouse, product):
        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse.id,
            "lines": [{"product_id": product.id, "qty": "1.000"}],
        }, format="json")
        assert resp.status_code == 400

    def test_transfer_recalculates_destination_avg_cost(
        self, api_client, tenant, warehouse, warehouse_b, product
    ):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))
        _seed_stock(tenant, warehouse_b, product, Decimal("10.000"), Decimal("200.000"))

        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [{"product_id": product.id, "qty": "10.000"}],
        }, format="json")
        assert resp.status_code == 201

        si_to = StockItem.objects.get(tenant=tenant, warehouse=warehouse_b, product=product)
        # dest had 10 @ 200 = 2000, received 10 @ 100 (origin avg_cost) = 1000
        # new avg = 3000 / 20 = 150
        assert si_to.on_hand == Decimal("20.000")
        assert si_to.avg_cost == Decimal("150.000")
        assert si_to.stock_value == Decimal("3000.000")

    def test_transfer_creates_two_moves(self, api_client, tenant, warehouse, warehouse_b, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("50.000"))

        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [{"product_id": product.id, "qty": "5.000"}],
        }, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["moves"]) == 1  # 1 line -> 1 pair
        pair = data["moves"][0]

        out_move = StockMove.objects.get(id=pair["out_move_id"])
        in_move = StockMove.objects.get(id=pair["in_move_id"])

        assert out_move.move_type == StockMove.OUT
        assert out_move.warehouse_id == warehouse.id
        assert out_move.ref_type == "TRANSFER"

        assert in_move.move_type == StockMove.IN
        assert in_move.warehouse_id == warehouse_b.id
        assert in_move.ref_type == "TRANSFER"

        # cost snapshot from origin
        assert out_move.cost_snapshot == Decimal("50.000")
        assert in_move.cost_snapshot == Decimal("50.000")

    def test_transfer_multiple_lines(
        self, api_client, tenant, warehouse, warehouse_b, product, product_b
    ):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))
        _seed_stock(tenant, warehouse, product_b, Decimal("20.000"), Decimal("50.000"))

        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [
                {"product_id": product.id, "qty": "3.000"},
                {"product_id": product_b.id, "qty": "5.000"},
            ],
        }, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["line_ids"]) == 2
        assert len(data["moves"]) == 2

    def test_transfer_empty_lines_returns_400(self, api_client, warehouse, warehouse_b):
        resp = api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [],
        }, format="json")
        assert resp.status_code == 400

    def test_transfer_origin_avg_cost_unchanged(
        self, api_client, tenant, warehouse, warehouse_b, product
    ):
        _seed_stock(tenant, warehouse, product, Decimal("20.000"), Decimal("100.000"))

        api_client.post(URL_TRANSFER, {
            "from_warehouse_id": warehouse.id,
            "to_warehouse_id": warehouse_b.id,
            "lines": [{"product_id": product.id, "qty": "5.000"}],
        }, format="json")

        si_from = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
        assert si_from.avg_cost == Decimal("100.000")  # unchanged


# ==========================================================
# STOCK LIST
# ==========================================================
@pytest.mark.django_db
class TestStockList:
    """GET /api/inventory/stock/?warehouse_id="""

    def test_stock_list_returns_products(self, api_client, tenant, warehouse, product, product_b):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))
        _seed_stock(tenant, warehouse, product_b, Decimal("5.000"), Decimal("50.000"))

        resp = api_client.get(URL_STOCK, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["warehouse_id"] == warehouse.id
        assert data["count"] >= 2

        # find our seeded products in the results
        names = {r["name"] for r in data["results"]}
        assert "Producto Test" in names
        assert "Producto B" in names

    def test_stock_list_requires_warehouse_id(self, api_client):
        resp = api_client.get(URL_STOCK)
        assert resp.status_code == 400

    def test_stock_list_shows_on_hand_and_avg_cost(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("15.000"), Decimal("75.000"))

        resp = api_client.get(URL_STOCK, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        results = resp.json()["results"]
        item = next(r for r in results if r["product_id"] == product.id)
        assert Decimal(item["on_hand"]) == Decimal("15.000")
        assert Decimal(item["avg_cost"]) == Decimal("75.000")

    def test_stock_list_paginated(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"))

        resp = api_client.get(URL_STOCK, {"warehouse_id": warehouse.id, "page": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "results" in data


# ==========================================================
# MOVES LIST
# ==========================================================
@pytest.mark.django_db
class TestStockMoveList:
    """GET /api/inventory/moves/?warehouse_id="""

    def test_moves_list_after_operations(self, api_client, tenant, warehouse, product):
        # Create some moves via receive and issue
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "100.000",
        })
        api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "3.000",
            "reason": "MERMA",
        })

        resp = api_client.get(URL_MOVES, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) >= 2

        # Check move types present
        types = {r["move_type"] for r in results}
        assert "IN" in types
        assert "OUT" in types

    def test_moves_list_filter_by_move_type(self, api_client, tenant, warehouse, product):
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
        })
        api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-2.000",
        })

        resp = api_client.get(URL_MOVES, {"warehouse_id": warehouse.id, "move_type": "IN"})
        assert resp.status_code == 200
        for r in resp.json()["results"]:
            assert r["move_type"] == "IN"

    def test_moves_include_cost_fields(self, api_client, tenant, warehouse, product):
        _seed_stock(tenant, warehouse, product, Decimal("10.000"), Decimal("100.000"))
        api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "2.000",
            "reason": "USO_INTERNO",
        })

        resp = api_client.get(URL_MOVES, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        move = resp.json()["results"][0]
        assert "cost_snapshot" in move
        assert "value_delta" in move


# ==========================================================
# KARDEX
# ==========================================================
@pytest.mark.django_db
class TestKardex:
    """GET /api/inventory/kardex/?warehouse_id=&product_id="""

    def test_kardex_running_balance(self, api_client, tenant, warehouse, product):
        # Receive 10, then issue 3 -> balances should be 10, 7
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "100.000",
        })
        api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "3.000",
            "reason": "MERMA",
        })

        resp = api_client.get(URL_KARDEX, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
        })
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"]["results"]
        assert len(results) == 2

        # first move: IN 10 -> balance 10
        assert Decimal(results[0]["balance"]) == Decimal("10.000")
        assert results[0]["move_type"] == "IN"

        # second move: OUT 3 -> balance 7
        assert Decimal(results[1]["balance"]) == Decimal("7.000")
        assert results[1]["move_type"] == "OUT"

    def test_kardex_requires_warehouse_id(self, api_client):
        resp = api_client.get(URL_KARDEX)
        assert resp.status_code == 400

    def test_kardex_date_filtering(self, api_client, tenant, warehouse, product):
        from django.utils import timezone
        import datetime

        # Receive stock
        resp_recv = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "100.000",
        })
        assert resp_recv.status_code == 201, f"Receive failed: {resp_recv.json()}"

        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        yesterday = today - datetime.timedelta(days=1)

        # Filter to today only: should return the move
        resp = api_client.get(URL_KARDEX, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "from": str(today),
            "to": str(today),
        })
        assert resp.status_code == 200
        results = resp.json()["results"]["results"]
        assert len(results) >= 1

        # Filter to yesterday only: should return nothing
        resp = api_client.get(URL_KARDEX, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "from": str(yesterday),
            "to": str(yesterday),
        })
        assert resp.status_code == 200
        results = resp.json()["results"]["results"]
        assert len(results) == 0

    def test_kardex_without_product_id(self, api_client, tenant, warehouse, product, product_b):
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
        })
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product_b.id,
            "qty": "3.000",
        })

        resp = api_client.get(URL_KARDEX, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        results = resp.json()["results"]["results"]
        # Should contain moves for both products
        product_ids = {r["product"]["id"] for r in results}
        assert product.id in product_ids
        assert product_b.id in product_ids

    def test_kardex_includes_cost_fields(self, api_client, tenant, warehouse, product):
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
            "unit_cost": "100.000",
        })

        resp = api_client.get(URL_KARDEX, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
        })
        assert resp.status_code == 200
        row = resp.json()["results"]["results"][0]
        assert "cost_snapshot" in row
        assert "value_delta" in row
        assert "unit_cost" in row

    def test_kardex_opening_balance_with_date_filter(self, api_client, tenant, warehouse, product):
        """
        When filtering by date, the opening balance should reflect
        all moves before the 'from' date.
        """
        from django.utils import timezone
        import datetime

        # Receive 10 and backdate the move
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "100.000",
        })
        yesterday = timezone.now() - datetime.timedelta(days=1)
        StockMove.objects.filter(
            tenant=tenant, warehouse=warehouse, product=product
        ).update(created_at=yesterday)

        # Receive 5 more today
        api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
            "unit_cost": "100.000",
        })

        today = timezone.localdate()
        resp = api_client.get(URL_KARDEX, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "from": str(today),
        })
        assert resp.status_code == 200
        results = resp.json()["results"]["results"]
        assert len(results) == 1
        # Opening balance of 10 + today's 5 = 15
        assert Decimal(results[0]["balance"]) == Decimal("15.000")


# ==========================================================
# INTEGRATION: end-to-end flow
# ==========================================================
@pytest.mark.django_db
class TestInventoryIntegration:
    """Full workflow: receive -> adjust -> issue -> verify stock."""

    def test_full_flow(self, api_client, tenant, warehouse, product):
        # 1. Receive 20 units at cost 100
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "20.000",
            "unit_cost": "100.000",
        })
        assert resp.status_code == 201

        # 2. Receive 10 more at cost 200 -> avg should be (20*100+10*200)/30 = 133.333
        resp = api_client.post(URL_RECEIVE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "10.000",
            "unit_cost": "200.000",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert Decimal(data["new_stock"]) == Decimal("30.000")
        expected_avg = (Decimal("20") * Decimal("100") + Decimal("10") * Decimal("200")) / Decimal("30")
        assert abs(Decimal(data["avg_cost"]) - expected_avg) < Decimal("0.01")

        # 3. Issue 5 for MERMA
        resp = api_client.post(URL_ISSUE, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "5.000",
            "reason": "MERMA",
        })
        assert resp.status_code == 201
        assert Decimal(resp.json()["new_stock"]) == Decimal("25.000")

        # 4. Adjust -5
        resp = api_client.post(URL_ADJUST, {
            "warehouse_id": warehouse.id,
            "product_id": product.id,
            "qty": "-5.000",
        })
        assert resp.status_code == 201
        assert Decimal(resp.json()["new_stock"]) == Decimal("20.000")

        # 5. Stock list should show 20
        resp = api_client.get(URL_STOCK, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        item = next(r for r in resp.json()["results"] if r["product_id"] == product.id)
        assert Decimal(item["on_hand"]) == Decimal("20.000")

        # 6. Moves list should have 4 entries
        resp = api_client.get(URL_MOVES, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        moves = [r for r in resp.json()["results"] if r["product"]["id"] == product.id]
        assert len(moves) == 4
