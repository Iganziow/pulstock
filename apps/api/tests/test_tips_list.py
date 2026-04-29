"""
Tests para /api/sales/tips-list/ — endpoint nuevo de tabla detallada de
propinas, estilo Fudo. Reemplaza los gráficos por una vista filtrable
y paginada útil cuando hay muchos registros.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import Product
from inventory.models import StockItem
from sales.models import Sale


def _make_sale(tenant, store, warehouse, owner, *, total, tip, method="cash",
               days_ago=0, table_name=None):
    """Crea una Sale con SalePayment + tip. Si table_name, vincula a OpenOrder."""
    from sales.models import SalePayment
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse,
        created_by=owner, subtotal=Decimal(str(total)),
        total=Decimal(str(total)), tip=Decimal(str(tip)),
        status="COMPLETED", sale_type="VENTA",
        sale_number=Sale.objects.filter(tenant=tenant).count() + 1,
    )
    if days_ago:
        when = timezone.now() - timedelta(days=days_ago)
        Sale.objects.filter(id=sale.id).update(created_at=when)
    SalePayment.objects.create(
        sale=sale, tenant=tenant, method=method,
        amount=Decimal(str(total)) + Decimal(str(tip)),
    )
    if table_name:
        from tables.models import Table, OpenOrder
        table, _ = Table.objects.get_or_create(
            tenant=tenant, store=store, name=table_name,
            defaults={"status": "FREE"},
        )
        order = OpenOrder.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            table=table, opened_by=owner, status="CLOSED",
        )
        Sale.objects.filter(id=sale.id).update(open_order=order)
    return sale


@pytest.mark.django_db
class TestTipsListEndpoint:
    def test_returns_only_sales_with_tip(self, api_client, tenant, store, warehouse, owner):
        # 2 ventas con tip, 1 sin tip
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100)
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=200)
        _make_sale(tenant, store, warehouse, owner, total=3000, tip=0)

        r = api_client.get("/api/sales/tips-list/")
        assert r.status_code == 200, r.data
        assert r.data["count"] == 2
        assert all(Decimal(row["tip_amount"]) > 0 for row in r.data["results"])

    def test_totals_calculated_correctly(self, api_client, tenant, store, warehouse, owner):
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100)
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=300)

        r = api_client.get("/api/sales/tips-list/")
        assert Decimal(r.data["totals"]["total_tips"]) == Decimal("400")
        assert Decimal(r.data["totals"]["total_sales"]) == Decimal("3000")
        assert r.data["totals"]["count"] == 2
        # avg = 400 / 2 = 200
        assert Decimal(r.data["totals"]["avg_tip"]) == Decimal("200")

    def test_filter_by_payment_method(self, api_client, tenant, store, warehouse, owner):
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100, method="cash")
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=200, method="debit")
        _make_sale(tenant, store, warehouse, owner, total=3000, tip=300, method="card")

        r = api_client.get("/api/sales/tips-list/?payment_method=debit")
        assert r.data["count"] == 1
        assert Decimal(r.data["totals"]["total_tips"]) == Decimal("200")

    def test_filter_by_cashier(self, api_client, tenant, store, warehouse, owner):
        from core.models import User
        owner2 = User.objects.create_user(
            username="garzon2", password="x", tenant=tenant, active_store=store,
        )
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100)
        sale2 = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner2, subtotal=Decimal("2000"),
            total=Decimal("2000"), tip=Decimal("200"),
            status="COMPLETED", sale_type="VENTA",
        )
        from sales.models import SalePayment
        SalePayment.objects.create(
            sale=sale2, tenant=tenant, method="cash",
            amount=Decimal("2200"),
        )

        r = api_client.get(f"/api/sales/tips-list/?cashier_id={owner.id}")
        assert r.data["count"] == 1
        assert r.data["results"][0]["cashier_id"] == owner.id

    def test_filter_by_date_range(self, api_client, tenant, store, warehouse, owner):
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100, days_ago=0)
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=200, days_ago=15)
        _make_sale(tenant, store, warehouse, owner, total=3000, tip=300, days_ago=60)

        today = date.today()
        from_date = (today - timedelta(days=20)).isoformat()
        r = api_client.get(f"/api/sales/tips-list/?date_from={from_date}&date_to={today.isoformat()}")
        # Solo las 2 ventas dentro del rango (días 0 y 15)
        assert r.data["count"] == 2

    def test_table_name_for_table_sales(self, api_client, tenant, store, warehouse, owner):
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100, table_name="5")
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=200)  # sin mesa

        r = api_client.get("/api/sales/tips-list/")
        assert r.data["count"] == 2
        rows_by_tip = {row["tip_amount"]: row for row in r.data["results"]}
        # La de $100 vino de mesa "5"
        assert rows_by_tip["100.00"]["table_name"] == "5"
        # La de $200 no tiene mesa
        assert rows_by_tip["200.00"]["table_name"] is None

    def test_payment_method_label_in_spanish(self, api_client, tenant, store, warehouse, owner):
        _make_sale(tenant, store, warehouse, owner, total=1000, tip=100, method="debit")
        r = api_client.get("/api/sales/tips-list/")
        assert r.data["results"][0]["payment_method"] == "debit"
        assert r.data["results"][0]["payment_method_label"] == "Tarj. Débito"

    def test_pagination(self, api_client, tenant, store, warehouse, owner):
        # Crear 5 ventas con tip
        for i in range(5):
            _make_sale(tenant, store, warehouse, owner, total=1000 + i, tip=10 + i)

        r = api_client.get("/api/sales/tips-list/?page_size=2&page=1")
        assert r.data["count"] == 5
        assert r.data["page"] == 1
        assert r.data["page_size"] == 2
        assert r.data["total_pages"] == 3
        assert len(r.data["results"]) == 2

        r2 = api_client.get("/api/sales/tips-list/?page_size=2&page=3")
        assert r2.data["page"] == 3
        assert len(r2.data["results"]) == 1  # solo 1 en la última página

    def test_void_sales_excluded(self, api_client, tenant, store, warehouse, owner):
        s = _make_sale(tenant, store, warehouse, owner, total=1000, tip=100)
        Sale.objects.filter(id=s.id).update(status="VOID")
        _make_sale(tenant, store, warehouse, owner, total=2000, tip=200)

        r = api_client.get("/api/sales/tips-list/")
        # Solo la COMPLETED queda
        assert r.data["count"] == 1
        assert Decimal(r.data["totals"]["total_tips"]) == Decimal("200")

    def test_mixed_payment_method_label(self, api_client, tenant, store, warehouse, owner):
        """Si la venta tiene split (cash + debit), payment_method='mixed'."""
        from sales.models import SalePayment
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse,
            created_by=owner, subtotal=Decimal("1000"),
            total=Decimal("1000"), tip=Decimal("100"),
            status="COMPLETED", sale_type="VENTA",
        )
        SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("550"))
        SalePayment.objects.create(sale=sale, tenant=tenant, method="debit", amount=Decimal("550"))

        r = api_client.get("/api/sales/tips-list/")
        assert r.data["count"] == 1
        assert r.data["results"][0]["payment_method"] == "mixed"
        assert r.data["results"][0]["payment_method_label"] == "Mixto"

    def test_results_sorted_by_date_desc(self, api_client, tenant, store, warehouse, owner):
        s1 = _make_sale(tenant, store, warehouse, owner, total=1000, tip=100, days_ago=5)
        s2 = _make_sale(tenant, store, warehouse, owner, total=2000, tip=200, days_ago=2)
        s3 = _make_sale(tenant, store, warehouse, owner, total=3000, tip=300, days_ago=10)

        r = api_client.get("/api/sales/tips-list/?date_from=2020-01-01")
        ids_in_order = [row["sale_id"] for row in r.data["results"]]
        # Más reciente primero (s2 = 2 días, s1 = 5, s3 = 10)
        assert ids_in_order == [s2.id, s1.id, s3.id]
