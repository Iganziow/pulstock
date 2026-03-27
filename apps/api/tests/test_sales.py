"""
Tests para SaleCreate y SaleVoid.

Cubre:
- Deducción de stock al vender
- Snapshot de costo promedio ponderado en SaleLine
- Venta con stock insuficiente (debe rechazarse)
- Idempotencia: mismo idempotency_key devuelve la venta existente
- SaleVoid restaura stock y registra StockMove IN
- SaleVoid es idempotente (doble void no duplica)
"""
import pytest
from decimal import Decimal

from inventory.models import StockItem, StockMove
from sales.models import Sale, SaleLine


def _seed_stock(tenant, warehouse, product, qty, avg_cost):
    """Crea o actualiza un StockItem con qty y avg_cost dados."""
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        defaults={
            "on_hand": Decimal("0.000"),
            "avg_cost": Decimal("0.000"),
            "stock_value": Decimal("0.000"),
        },
    )
    si.on_hand = Decimal(str(qty))
    si.avg_cost = Decimal(str(avg_cost))
    si.stock_value = (si.on_hand * si.avg_cost).quantize(Decimal("0.001"))
    si.save()
    return si


def _sale_payload(warehouse_id, product_id, qty, unit_price, idempotency_key=""):
    payload = {
        "warehouse_id": warehouse_id,
        "lines": [{"product_id": product_id, "qty": str(qty), "unit_price": str(unit_price)}],
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return payload


# ──────────────────────────────────────────────
# SaleCreate
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_sale_create_deducts_stock(api_client, tenant, warehouse, product):
    """Crear una venta descuenta el stock correctamente."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost=500)

    resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=3, unit_price=1000),
        format="json",
    )

    assert resp.status_code == 201
    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("7.000")


@pytest.mark.django_db
def test_sale_create_records_cost_snapshot(api_client, tenant, warehouse, product):
    """El costo unitario en SaleLine debe ser el avg_cost del StockItem al momento de vender."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost="750.000")

    resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=2, unit_price=1500),
        format="json",
    )

    assert resp.status_code == 201
    sale = Sale.objects.get(pk=resp.data["id"])
    line = sale.lines.first()
    assert line.unit_cost_snapshot == Decimal("750.000")
    assert line.line_cost == Decimal("1500.000")   # 2 * 750
    assert sale.total_cost == Decimal("1500.000")
    assert sale.gross_profit == Decimal("1500.00")  # 3000 - 1500


@pytest.mark.django_db
def test_sale_create_insufficient_stock_rejected(api_client, tenant, warehouse, product):
    """Venta con más qty que stock disponible debe devolver 409 sin crear nada."""
    _seed_stock(tenant, warehouse, product, qty=2, avg_cost=500)

    resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=5, unit_price=1000),
        format="json",
    )

    assert resp.status_code == 409
    assert "shortages" in resp.data
    assert Sale.objects.count() == 0
    # Stock no debe haber cambiado
    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("2.000")


@pytest.mark.django_db
def test_sale_create_creates_stockmove_out(api_client, tenant, warehouse, product):
    """Crear venta genera un StockMove OUT con value_delta negativo."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost=400)

    resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=4, unit_price=1000),
        format="json",
    )

    assert resp.status_code == 201
    move = StockMove.objects.get(ref_type="SALE", move_type=StockMove.OUT)
    assert move.qty == Decimal("4.000")
    assert move.value_delta == Decimal("-1600.000")  # -(4 * 400)


@pytest.mark.django_db
def test_sale_create_idempotency_returns_existing(api_client, tenant, warehouse, product):
    """Dos requests con el mismo idempotency_key devuelven la misma venta (sin duplicar)."""
    _seed_stock(tenant, warehouse, product, qty=20, avg_cost=300)

    payload = _sale_payload(warehouse.id, product.id, qty=3, unit_price=900, idempotency_key="KEY-001")

    resp1 = api_client.post("/api/sales/sales/", payload, format="json")
    resp2 = api_client.post("/api/sales/sales/", payload, format="json")

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.data["id"] == resp2.data["id"]
    assert resp2.data.get("idempotent") is True

    # Solo se creó una venta y se descontó stock una sola vez
    assert Sale.objects.count() == 1
    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("17.000")


# ──────────────────────────────────────────────
# SaleVoid
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_sale_void_restores_stock(api_client, tenant, warehouse, product):
    """Anular una venta devuelve el stock al inventario."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost=500)

    create_resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=4, unit_price=1000),
        format="json",
    )
    assert create_resp.status_code == 201
    sale_id = create_resp.data["id"]

    # stock después de venta
    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("6.000")

    void_resp = api_client.post(f"/api/sales/sales/{sale_id}/void/")
    assert void_resp.status_code == 200

    si.refresh_from_db()
    assert si.on_hand == Decimal("10.000")


@pytest.mark.django_db
def test_sale_void_creates_stockmove_in(api_client, tenant, warehouse, product):
    """Anular una venta crea un StockMove IN con value_delta positivo."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost=600)

    create_resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=2, unit_price=1200),
        format="json",
    )
    sale_id = create_resp.data["id"]

    api_client.post(f"/api/sales/sales/{sale_id}/void/")

    void_move = StockMove.objects.get(ref_type="SALE_VOID", move_type=StockMove.IN)
    assert void_move.qty == Decimal("2.000")
    assert void_move.value_delta == Decimal("1200.000")  # 2 * 600


@pytest.mark.django_db
def test_sale_void_is_idempotent(api_client, tenant, warehouse, product):
    """Anular dos veces la misma venta no duplica el stock."""
    _seed_stock(tenant, warehouse, product, qty=10, avg_cost=500)

    create_resp = api_client.post(
        "/api/sales/sales/",
        _sale_payload(warehouse.id, product.id, qty=3, unit_price=1000),
        format="json",
    )
    sale_id = create_resp.data["id"]

    resp1 = api_client.post(f"/api/sales/sales/{sale_id}/void/")
    resp2 = api_client.post(f"/api/sales/sales/{sale_id}/void/")

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("10.000")  # stock original restaurado, no duplicado
    assert StockMove.objects.filter(ref_type="SALE_VOID").count() == 1
