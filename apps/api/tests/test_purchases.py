"""
Tests para PurchaseCreate, PurchasePost y lógica de costo promedio ponderado.

Cubre:
- _weighted_avg_cost: casos base, stock vacío, múltiples recepciones
- PurchasePost actualiza on_hand y avg_cost en StockItem
- PurchasePost genera StockMove IN
- PurchasePost es idempotente (doble post rechazado)
- PurchaseVoid revierte stock
"""
import pytest
from decimal import Decimal

from inventory.models import StockItem, StockMove
from purchases.models import Purchase, PurchaseLine
from purchases.views import _weighted_avg_cost


# ──────────────────────────────────────────────
# Unidad: _weighted_avg_cost
# ──────────────────────────────────────────────

def test_weighted_avg_cost_first_receipt():
    """Primera recepción: avg_cost == unit_cost recibido."""
    result = _weighted_avg_cost(
        old_qty=Decimal("0"),
        old_avg=Decimal("0"),
        in_qty=Decimal("10"),
        in_cost=Decimal("500"),
    )
    assert result == Decimal("500.000")


def test_weighted_avg_cost_blended():
    """Segunda recepción con precio diferente calcula promedio ponderado correcto."""
    # 10 unidades a $500 → luego 10 unidades a $700
    # nuevo promedio = (10*500 + 10*700) / 20 = 600
    result = _weighted_avg_cost(
        old_qty=Decimal("10"),
        old_avg=Decimal("500"),
        in_qty=Decimal("10"),
        in_cost=Decimal("700"),
    )
    assert result == Decimal("600.000")


def test_weighted_avg_cost_partial_receipt():
    """Recepción pequeña sobre stock grande: promedio se mueve poco."""
    # 100 unidades a $1000 → luego 1 unidad a $2000
    # nuevo promedio = (100*1000 + 1*2000) / 101 ≈ 1009.901
    result = _weighted_avg_cost(
        old_qty=Decimal("100"),
        old_avg=Decimal("1000"),
        in_qty=Decimal("1"),
        in_cost=Decimal("2000"),
    )
    assert result == Decimal("1009.901")


def test_weighted_avg_cost_zero_old_qty():
    """Si el stock estaba en cero, el promedio es el costo de la nueva recepción."""
    result = _weighted_avg_cost(
        old_qty=Decimal("0"),
        old_avg=Decimal("999"),  # avg anterior irrelevante si qty=0
        in_qty=Decimal("5"),
        in_cost=Decimal("300"),
    )
    assert result == Decimal("300.000")


# ──────────────────────────────────────────────
# Fixtures helpers
# ──────────────────────────────────────────────

def _purchase_payload(warehouse_id, product_id, qty, unit_cost):
    return {
        "warehouse_id": warehouse_id,
        "lines": [{"product_id": product_id, "qty": str(qty), "unit_cost": str(unit_cost)}],
    }


# ──────────────────────────────────────────────
# PurchasePost
# ──────────────────────────────────────────────

@pytest.mark.django_db
def test_purchase_post_creates_stock(api_client, tenant, warehouse, product):
    """Publicar una compra crea el StockItem con qty y avg_cost correctos."""
    resp = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=10, unit_cost=500),
        format="json",
    )
    assert resp.status_code == 201
    purchase_id = resp.data["id"]

    post_resp = api_client.post(f"/api/purchases/{purchase_id}/post/")
    assert post_resp.status_code == 200

    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("10.000")
    assert si.avg_cost == Decimal("500.000")
    assert si.stock_value == Decimal("5000.000")


@pytest.mark.django_db
def test_purchase_post_updates_avg_cost(api_client, tenant, warehouse, product):
    """Segunda compra a precio diferente actualiza avg_cost con promedio ponderado."""
    # Primera compra: 10 unidades a $400
    r1 = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=10, unit_cost=400),
        format="json",
    )
    api_client.post(f"/api/purchases/{r1.data['id']}/post/")

    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.avg_cost == Decimal("400.000")

    # Segunda compra: 10 unidades a $600 → promedio esperado = 500
    r2 = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=10, unit_cost=600),
        format="json",
    )
    api_client.post(f"/api/purchases/{r2.data['id']}/post/")

    si.refresh_from_db()
    assert si.on_hand == Decimal("20.000")
    assert si.avg_cost == Decimal("500.000")


@pytest.mark.django_db
def test_purchase_post_generates_stockmove_in(api_client, tenant, warehouse, product):
    """Publicar compra genera StockMove IN con value_delta positivo."""
    r = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=5, unit_cost=300),
        format="json",
    )
    api_client.post(f"/api/purchases/{r.data['id']}/post/")

    move = StockMove.objects.get(ref_type="PURCHASE", move_type=StockMove.IN)
    assert move.qty == Decimal("5.000")
    assert move.value_delta == Decimal("1500.000")  # 5 * 300
    assert move.cost_snapshot == Decimal("300.000")


@pytest.mark.django_db
def test_purchase_post_idempotent(api_client, tenant, warehouse, product):
    """Publicar la misma compra dos veces no duplica el stock."""
    r = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=5, unit_cost=200),
        format="json",
    )
    purchase_id = r.data["id"]

    resp1 = api_client.post(f"/api/purchases/{purchase_id}/post/")
    resp2 = api_client.post(f"/api/purchases/{purchase_id}/post/")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp2.data.get("detail") == "Purchase already posted"

    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("5.000")  # no duplicado
    assert StockMove.objects.count() == 1


@pytest.mark.django_db
def test_purchase_void_reverts_stock(api_client, tenant, warehouse, product):
    """Anular compra postada revierte el stock."""
    r = api_client.post(
        "/api/purchases/create/",
        _purchase_payload(warehouse.id, product.id, qty=8, unit_cost=250),
        format="json",
    )
    purchase_id = r.data["id"]
    api_client.post(f"/api/purchases/{purchase_id}/post/")

    si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=product)
    assert si.on_hand == Decimal("8.000")

    void_resp = api_client.post(f"/api/purchases/{purchase_id}/void/")
    assert void_resp.status_code == 200

    si.refresh_from_db()
    assert si.on_hand == Decimal("0.000")
