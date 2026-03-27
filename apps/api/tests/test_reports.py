"""
Tests for the reports module endpoints.
"""
import pytest
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventory.models import StockItem, StockMove
from sales.models import Sale, SaleLine, SalePayment

_sub = pytest.mark.usefixtures("forecast_subscription")


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_stock_item(tenant, warehouse, product, on_hand, avg_cost):
    """Create a StockItem with calculated stock_value."""
    return StockItem.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        on_hand=Decimal(str(on_hand)),
        avg_cost=Decimal(str(avg_cost)),
        stock_value=Decimal(str(on_hand)) * Decimal(str(avg_cost)),
    )


def _make_sale(tenant, store, warehouse, owner, lines, *, days_ago=0):
    """
    Create a complete Sale with SaleLines and a SalePayment.
    lines: list of (product, qty, unit_price, unit_cost) tuples.
    """
    now = timezone.now() - timedelta(days=days_ago)
    sale = Sale.objects.create(
        tenant=tenant,
        store=store,
        warehouse=warehouse,
        created_by=owner,
        created_at=now,
        status=Sale.STATUS_COMPLETED,
    )
    total_revenue = Decimal("0")
    total_cost = Decimal("0")
    for product, qty, unit_price, unit_cost in lines:
        qty = Decimal(str(qty))
        unit_price = Decimal(str(unit_price))
        unit_cost = Decimal(str(unit_cost))
        line_total = qty * unit_price
        line_cost = qty * unit_cost
        SaleLine.objects.create(
            sale=sale,
            tenant=tenant,
            product=product,
            qty=qty,
            unit_price=unit_price,
            line_total=line_total,
            unit_cost_snapshot=unit_cost,
            line_cost=line_cost,
            line_gross_profit=line_total - line_cost,
        )
        total_revenue += line_total
        total_cost += line_cost

    sale.subtotal = total_revenue
    sale.total = total_revenue
    sale.total_cost = total_cost
    sale.gross_profit = total_revenue - total_cost
    sale.save()

    SalePayment.objects.create(
        sale=sale,
        tenant=tenant,
        method=SalePayment.METHOD_CASH,
        amount=total_revenue,
    )
    return sale


def _make_loss(tenant, warehouse, product, qty, reason, *, days_ago=0, cost_snapshot=None):
    """Create an OUT StockMove with ref_type=ISSUE (loss/merma)."""
    avg_cost = cost_snapshot or Decimal("100")
    return StockMove.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        move_type=StockMove.OUT,
        qty=Decimal(str(qty)),
        reason=reason,
        ref_type="ISSUE",
        cost_snapshot=avg_cost,
        value_delta=-(Decimal(str(qty)) * avg_cost),
        created_at=timezone.now() - timedelta(days=days_ago),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. STOCK VALUED REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestStockValuedReport:
    URL = "/api/reports/stock-valued/"

    def test_totals_correct(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200

        data = resp.json()
        totals = data["totals"]
        # 10*500 + 5*200 = 6000
        assert Decimal(totals["total_qty"]) == Decimal("15.000")
        assert Decimal(totals["total_value"]) == Decimal("6000.000")
        assert len(data["results"]) == 2

    def test_filter_by_warehouse(self, api_client, tenant, store, warehouse, product):
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega 2")
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, wh2, product, on_hand=3, avg_cost="100")

        # Filter specific warehouse
        resp = api_client.get(self.URL, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert Decimal(results[0]["on_hand"]) == Decimal("10.000")

    def test_search_by_name(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="100")

        resp = api_client.get(self.URL, {"q": "Producto B"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "Producto B"

    def test_truncation_meta(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=1, avg_cost="100")
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["truncated"] is False
        assert meta["total_count"] == 1
        assert meta["limit"] == 5000

    def test_empty_stock(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["totals"]["total_qty"]) == Decimal("0")
        assert data["results"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. LOSSES REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestLossesReport:
    URL = "/api/reports/losses/"

    def test_aggregate_by_reason(self, api_client, tenant, warehouse, product, product_b):
        _make_loss(tenant, warehouse, product, qty=3, reason="EXPIRED", cost_snapshot=Decimal("100"))
        _make_loss(tenant, warehouse, product_b, qty=2, reason="DAMAGED", cost_snapshot=Decimal("200"))
        _make_loss(tenant, warehouse, product, qty=1, reason="EXPIRED", cost_snapshot=Decimal("100"))

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()

        by_reason = {r["reason"]: r for r in data["by_reason"]}
        assert "EXPIRED" in by_reason
        assert "DAMAGED" in by_reason
        assert Decimal(by_reason["EXPIRED"]["qty"]) == Decimal("4.000")
        assert Decimal(by_reason["DAMAGED"]["qty"]) == Decimal("2.000")

        # Total cost: EXPIRED=4*100=400, DAMAGED=2*200=400, total=800
        assert Decimal(data["totals"]["qty"]) == Decimal("6.000")

    def test_date_filter(self, api_client, tenant, warehouse, product):
        _make_loss(tenant, warehouse, product, qty=5, reason="EXPIRED", days_ago=10)
        _make_loss(tenant, warehouse, product, qty=3, reason="EXPIRED", days_ago=2)

        today = timezone.now().date()
        date_from = (today - timedelta(days=5)).isoformat()
        date_to = today.isoformat()

        resp = api_client.get(self.URL, {"date_from": date_from, "date_to": date_to})
        assert resp.status_code == 200
        data = resp.json()
        # Only the recent loss (3 units) should appear
        assert Decimal(data["totals"]["qty"]) == Decimal("3.000")

    def test_filter_by_reason(self, api_client, tenant, warehouse, product):
        _make_loss(tenant, warehouse, product, qty=5, reason="EXPIRED")
        _make_loss(tenant, warehouse, product, qty=3, reason="DAMAGED")

        resp = api_client.get(self.URL, {"reason": "EXPIRED"})
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["totals"]["qty"]) == Decimal("5.000")
        assert len(data["by_reason"]) == 1

    def test_no_losses(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["totals"]["qty"]) == Decimal("0")
        assert data["by_reason"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. SALES SUMMARY REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestSalesSummaryReport:
    URL = "/api/reports/sales-summary/"

    def test_revenue_cost_margin(self, api_client, tenant, store, warehouse, owner, product, product_b):
        # Sale 1: product 5 units at $1000, cost $500
        _make_sale(tenant, store, warehouse, owner, [
            (product, 5, "1000", "500"),
        ])
        # Sale 2: product_b 3 units at $500, cost $200
        _make_sale(tenant, store, warehouse, owner, [
            (product_b, 3, "500", "200"),
        ])

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]

        # Revenue: 5*1000 + 3*500 = 6500
        assert Decimal(kpis["total_revenue"]) == Decimal("6500.00")
        # Cost: 5*500 + 3*200 = 3100
        assert Decimal(kpis["total_cost"]) == Decimal("3100.000")
        # Profit: 6500 - 3100 = 3400
        assert Decimal(kpis["gross_profit"]) == Decimal("3400.000")
        # Margin: 3400/6500*100 ~= 52.3%
        margin = Decimal(kpis["margin_pct"])
        assert margin > Decimal("52") and margin < Decimal("53")
        assert kpis["sale_count"] == 2

    def test_daily_breakdown(self, api_client, tenant, store, warehouse, owner, product):
        _make_sale(tenant, store, warehouse, owner, [
            (product, 2, "1000", "500"),
        ], days_ago=1)
        _make_sale(tenant, store, warehouse, owner, [
            (product, 3, "1000", "500"),
        ], days_ago=0)

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=2)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        daily = resp.json()["daily"]
        assert len(daily) >= 1
        # Each day entry should have revenue, cost, count
        for d in daily:
            assert "date" in d
            assert "revenue" in d
            assert "cost" in d
            assert "count" in d

    def test_empty_sales(self, api_client):
        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": today.isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert Decimal(kpis["total_revenue"]) == Decimal("0")
        assert kpis["sale_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. TOP PRODUCTS REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestTopProductsReport:
    URL = "/api/reports/top-products/"

    def _setup_sales(self, tenant, store, warehouse, owner, product, product_b):
        # product: 10 units at $1000, cost $500 => revenue=10000, profit=5000
        _make_sale(tenant, store, warehouse, owner, [
            (product, 10, "1000", "500"),
        ])
        # product_b: 20 units at $500, cost $200 => revenue=10000, profit=6000
        _make_sale(tenant, store, warehouse, owner, [
            (product_b, 20, "500", "200"),
        ])

    def test_sort_by_revenue(self, api_client, tenant, store, warehouse, owner, product, product_b):
        self._setup_sales(tenant, store, warehouse, owner, product, product_b)
        today = timezone.now().date()

        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "sort": "revenue",
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        # Both have same revenue (10000), so order may vary
        revenues = [Decimal(r["revenue"]) for r in results]
        assert all(r == Decimal("10000.00") for r in revenues)

    def test_sort_by_qty(self, api_client, tenant, store, warehouse, owner, product, product_b):
        self._setup_sales(tenant, store, warehouse, owner, product, product_b)
        today = timezone.now().date()

        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "sort": "qty",
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        # product_b has more qty (20 > 10), should come first
        assert Decimal(results[0]["qty"]) == Decimal("20.000")

    def test_sort_by_profit(self, api_client, tenant, store, warehouse, owner, product, product_b):
        self._setup_sales(tenant, store, warehouse, owner, product, product_b)
        today = timezone.now().date()

        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "sort": "profit",
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        # product_b has more profit (6000 > 5000), should come first
        assert Decimal(results[0]["profit"]) == Decimal("6000.000")

    def test_limit(self, api_client, tenant, store, warehouse, owner, product, product_b):
        self._setup_sales(tenant, store, warehouse, owner, product, product_b)
        today = timezone.now().date()

        # View clamps min limit to 5, so use limit=5 with only 2 products
        # to verify the parameter is respected (returns fewer than limit)
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "limit": 5,
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        meta = resp.json()["meta"]
        assert meta["limit"] == 5
        assert len(results) <= 5


# ═══════════════════════════════════════════════════════════════════════════
# 5. DEAD STOCK REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestDeadStockReport:
    URL = "/api/reports/dead-stock/"

    def test_dead_stock_no_sales(self, api_client, tenant, store, warehouse, owner, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")
        # No sales at all -> both are dead stock

        resp = api_client.get(self.URL, {"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["product_count"] == 2

    def test_excludes_recently_sold(self, api_client, tenant, store, warehouse, owner, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        # product was sold recently
        _make_sale(tenant, store, warehouse, owner, [
            (product, 1, "1000", "500"),
        ], days_ago=2)

        resp = api_client.get(self.URL, {"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        # Only product_b should be dead stock
        assert data["totals"]["product_count"] == 1
        assert data["results"][0]["product_name"] == "Producto B"

    def test_dead_stock_value(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["totals"]["total_value"]) == Decimal("5000.000")

    def test_filter_by_warehouse(self, api_client, tenant, store, warehouse, product):
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Muerta")
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, wh2, product, on_hand=5, avg_cost="100")

        resp = api_client.get(self.URL, {"warehouse_id": wh2.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["product_count"] == 1
        assert data["results"][0]["warehouse_id"] == wh2.id


# ═══════════════════════════════════════════════════════════════════════════
# 6. INVENTORY COUNT SHEET
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestInventoryCountSheet:
    URL = "/api/reports/inventory-count-sheet/"

    def test_basic_list(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert data["totals"]["product_count"] == 2

    def test_has_required_fields(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        item = resp.json()["results"][0]
        assert "product_id" in item
        assert "product_name" in item
        assert "stock_system" in item
        assert "avg_cost" in item
        assert "stock_physical" in item  # empty string for fill-in
        assert "difference" in item      # empty string for fill-in

    def test_filter_by_warehouse(self, api_client, tenant, store, warehouse, product):
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Conteo")
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, wh2, product, on_hand=5, avg_cost="100")

        resp = api_client.get(self.URL, {"warehouse_id": wh2.id})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert Decimal(results[0]["stock_system"]) == Decimal("5.000")

    def test_excludes_zero_stock_by_default(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=0, avg_cost="200")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

    def test_show_zero_flag(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=0, avg_cost="200")

        resp = api_client.get(self.URL, {"show_zero": "true"})
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_header_info(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        header = resp.json()["header"]
        assert "store_name" in header
        assert "generated_at" in header
        assert "generated_by" in header

    def test_truncation_meta_count_sheet(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=1, avg_cost="100")
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["truncated"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 7. TRANSFER SUGGESTION SHEET REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestTransferSuggestionSheetReport:
    URL = "/api/reports/transfer-suggestion-sheet/"

    def _make_sale_move(self, tenant, warehouse, product, qty, *, days_ago=0):
        """Create an OUT StockMove with ref_type=SALE to simulate sales velocity."""
        return StockMove.objects.create(
            tenant=tenant,
            warehouse=warehouse,
            product=product,
            move_type=StockMove.OUT,
            qty=Decimal(str(qty)),
            ref_type="SALE",
            cost_snapshot=Decimal("100"),
            value_delta=-(Decimal(str(qty)) * Decimal("100")),
            created_at=timezone.now() - timedelta(days=days_ago),
        )

    def test_rotation_mode(self, api_client, tenant, store, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=5, avg_cost="100")
        self._make_sale_move(tenant, warehouse, product, qty=30, days_ago=15)

        resp = api_client.get(self.URL, {"mode": "rotation", "sales_days": 30, "target_days": 14})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        r = data["results"][0]
        assert Decimal(r["avg_sales_day"]) == Decimal("1.000")
        assert Decimal(r["suggested"]) == Decimal("9.000")

    def test_simple_mode(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=3, avg_cost="100")

        resp = api_client.get(self.URL, {"mode": "simple", "target_qty": 10})
        assert resp.status_code == 200
        r = resp.json()["results"][0]
        assert Decimal(r["suggested"]) == Decimal("7.000")

    def test_auto_mode(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=5, avg_cost="100")
        self._make_sale_move(tenant, warehouse, product, qty=30, days_ago=15)

        resp = api_client.get(self.URL, {"mode": "auto"})
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["mode"] == "auto"
        assert meta["used_mode"] in ("rotation", "mixed")

    def test_header_info(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=5, avg_cost="100")

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        header = resp.json()["header"]
        assert "store_name" in header
        assert "generated_at" in header


# ═══════════════════════════════════════════════════════════════════════════
# 8. PROFITABILITY REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestProfitabilityReport:
    URL = "/api/reports/profitability/"

    def test_by_product(self, api_client, tenant, store, warehouse, owner, product, product_b):
        _make_sale(tenant, store, warehouse, owner, [
            (product, 5, "1000", "500"),
            (product_b, 10, "500", "200"),
        ])

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "group_by": "product",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        for r in data["results"]:
            assert "margin_pct" in r
            assert "profit" in r

    def test_by_category(self, api_client, tenant, store, warehouse, owner, product, product_b):
        from catalog.models import Category
        cat = Category.objects.create(tenant=tenant, name="Bebidas", is_active=True)
        product.category = cat
        product.save()
        product_b.category = cat
        product_b.save()

        _make_sale(tenant, store, warehouse, owner, [
            (product, 5, "1000", "500"),
            (product_b, 10, "500", "200"),
        ])

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "group_by": "category",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1
        assert data["results"][0]["category"] == "Bebidas"

    def test_totals(self, api_client, tenant, store, warehouse, owner, product):
        _make_sale(tenant, store, warehouse, owner, [
            (product, 10, "1000", "400"),
        ])

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        totals = resp.json()["totals"]
        assert Decimal(totals["revenue"]) == Decimal("10000.00")
        assert Decimal(totals["profit"]) == Decimal("6000.000")
        assert Decimal(totals["margin_pct"]) == Decimal("60.0")


# ═══════════════════════════════════════════════════════════════════════════
# 9. INVENTORY DIFF REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestInventoryDiffReport:
    URL = "/api/reports/inventory-diff/"

    def test_shortage_surplus_match(self, api_client, tenant, warehouse, product, product_b):
        from catalog.models import Product
        product_c = Product.objects.create(tenant=tenant, name="Producto C", price=Decimal("300"), is_active=True)

        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")
        _make_stock_item(tenant, warehouse, product_c, on_hand=8, avg_cost="150")

        resp = api_client.post(self.URL, {
            "counts": [
                {"product_id": product.id, "warehouse_id": warehouse.id, "physical": 7},
                {"product_id": product_b.id, "warehouse_id": warehouse.id, "physical": 8},
                {"product_id": product_c.id, "warehouse_id": warehouse.id, "physical": 8},
            ]
        }, format="json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["shortages"] == 1
        assert data["totals"]["surpluses"] == 1
        assert data["totals"]["matches"] == 1

    def test_diff_values(self, api_client, tenant, warehouse, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")

        resp = api_client.post(self.URL, {
            "counts": [
                {"product_id": product.id, "warehouse_id": warehouse.id, "physical": 7},
            ]
        }, format="json")
        assert resp.status_code == 200
        r = resp.json()["results"][0]
        assert r["status"] == "shortage"
        assert Decimal(r["difference_qty"]) == Decimal("-3.000")
        assert Decimal(r["difference_value"]) == Decimal("-1500.000")

    def test_totals_summary(self, api_client, tenant, warehouse, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        resp = api_client.post(self.URL, {
            "counts": [
                {"product_id": product.id, "warehouse_id": warehouse.id, "physical": 8},
                {"product_id": product_b.id, "warehouse_id": warehouse.id, "physical": 7},
            ]
        }, format="json")
        assert resp.status_code == 200
        totals = resp.json()["totals"]
        assert totals["counted"] == 2
        assert Decimal(totals["shortage_qty"]) == Decimal("2.000")
        assert Decimal(totals["shortage_value"]) == Decimal("200.000")
        assert Decimal(totals["surplus_qty"]) == Decimal("2.000")
        assert Decimal(totals["surplus_value"]) == Decimal("400.000")


# ═══════════════════════════════════════════════════════════════════════════
# 10. AUDIT TRAIL REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestAuditTrailReport:
    URL = "/api/reports/audit-trail/"

    def _make_moves(self, tenant, warehouse, product, owner):
        for i in range(5):
            StockMove.objects.create(
                tenant=tenant, warehouse=warehouse, product=product,
                move_type=StockMove.IN, qty=Decimal("10"),
                ref_type="PURCHASE", cost_snapshot=Decimal("100"),
                value_delta=Decimal("1000"), created_by=owner,
                created_at=timezone.now() - timedelta(hours=i),
            )
        for i in range(3):
            StockMove.objects.create(
                tenant=tenant, warehouse=warehouse, product=product,
                move_type=StockMove.OUT, qty=Decimal("5"),
                ref_type="SALE", cost_snapshot=Decimal("100"),
                value_delta=Decimal("-500"), created_by=owner,
                created_at=timezone.now() - timedelta(hours=i),
            )

    def test_pagination(self, api_client, tenant, warehouse, product, owner):
        self._make_moves(tenant, warehouse, product, owner)

        resp = api_client.get(self.URL, {"page": 1, "page_size": 10})
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["total"] == 8
        assert meta["page"] == 1
        assert meta["total_pages"] == 1
        assert len(resp.json()["results"]) == 8

    def test_filter_by_ref_type(self, api_client, tenant, warehouse, product, owner):
        self._make_moves(tenant, warehouse, product, owner)

        resp = api_client.get(self.URL, {"ref_type": "SALE"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 3
        assert all(r["ref_type"] == "SALE" for r in results)

    def test_by_type_aggregation(self, api_client, tenant, warehouse, product, owner):
        self._make_moves(tenant, warehouse, product, owner)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        by_type = {r["ref_type"]: r for r in data["by_type"]}
        assert "PURCHASE" in by_type
        assert "SALE" in by_type
        assert by_type["PURCHASE"]["count"] == 5
        assert by_type["SALE"]["count"] == 3

    def test_summary(self, api_client, tenant, warehouse, product, owner):
        self._make_moves(tenant, warehouse, product, owner)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert summary["move_count"] == 8
        assert Decimal(summary["total_in_qty"]) == Decimal("50.000")
        assert Decimal(summary["total_out_qty"]) == Decimal("15.000")


# ═══════════════════════════════════════════════════════════════════════════
# 11. ABC ANALYSIS REPORT
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestABCAnalysisReport:
    URL = "/api/reports/abc-analysis/"

    def _setup_varied_sales(self, tenant, store, warehouse, owner):
        """Create 5 products with varied revenues for ABC classification.
        Revenue distribution: 40k, 25k, 15k, 10k, 5k = 95k total
        Cumulative: 42.1%(A), 68.4%(A), 84.2%(B), 94.7%(B), 100%(C)
        """
        from catalog.models import Product
        products = []
        for name, qty, price, cost in [
            ("Prod-Top1", 40, "1000", "500"),   # 40k
            ("Prod-Top2", 50, "500", "200"),     # 25k
            ("Prod-Mid1", 30, "500", "300"),     # 15k
            ("Prod-Mid2", 20, "500", "250"),     # 10k
            ("Prod-Low1", 50, "100", "50"),      #  5k
        ]:
            p = Product.objects.create(tenant=tenant, name=name, price=Decimal(price), is_active=True)
            products.append(p)
            _make_sale(tenant, store, warehouse, owner, [(p, qty, price, cost)])
        return products

    def test_abc_classification(self, api_client, tenant, store, warehouse, owner):
        self._setup_varied_sales(tenant, store, warehouse, owner)

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 5
        assert results[0]["rank"] == 1
        # Top products should be class A (cumulative <= 80%)
        assert results[0]["abc_class"] == "A"
        # Last product should be class C
        assert results[-1]["abc_class"] == "C"

    def test_criterion_profit(self, api_client, tenant, store, warehouse, owner):
        self._setup_varied_sales(tenant, store, warehouse, owner)

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
            "criterion": "profit",
        })
        assert resp.status_code == 200
        assert resp.json()["meta"]["criterion"] == "profit"

    def test_class_summary(self, api_client, tenant, store, warehouse, owner):
        self._setup_varied_sales(tenant, store, warehouse, owner)

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        cs = resp.json()["class_summary"]
        assert "A" in cs and "B" in cs and "C" in cs
        total = cs["A"]["count"] + cs["B"]["count"] + cs["C"]["count"]
        assert total == 5

    def test_includes_stock_info(self, api_client, tenant, store, warehouse, owner, product):
        _make_stock_item(tenant, warehouse, product, on_hand=25, avg_cost="100")
        _make_sale(tenant, store, warehouse, owner, [(product, 10, "1000", "500")])

        today = timezone.now().date()
        resp = api_client.get(self.URL, {
            "date_from": (today - timedelta(days=1)).isoformat(),
            "date_to": today.isoformat(),
        })
        assert resp.status_code == 200
        r = resp.json()["results"][0]
        assert Decimal(r["current_stock"]) == Decimal("25.000")
        assert Decimal(r["stock_value"]) == Decimal("2500.000")
