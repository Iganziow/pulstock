"""
Tests del sync de PPP — Mario 18/05/26.

Hasta este fix, editar Product.cost desde el catalogo NO afectaba el
StockItem.avg_cost (que es lo que el sistema usa para calcular costo de
ventas). Era un placebo. Ahora el PATCH al producto:
  1. Actualiza Product.cost
  2. Sincroniza StockItem.avg_cost en TODAS las bodegas del tenant
  3. Recalcula stock_value = on_hand × new_avg_cost
  4. Crea StockMove ADJ con reason='MANUAL_COST_ADJUST' (auditoria)
"""
import pytest
from decimal import Decimal

from catalog.models import Product
from inventory.models import StockItem, StockMove
from core.models import Warehouse


PATCH_URL = "/api/catalog/products/{}/"


def _make_product(tenant, name="Leche entera", cost=Decimal("1000")):
    return Product.objects.create(
        tenant=tenant, name=name,
        price=Decimal("2000"), cost=cost,
        is_active=True,
    )


def _make_stock(tenant, warehouse, product, on_hand="100.000", avg_cost="1000.000"):
    si, _ = StockItem.objects.get_or_create(
        tenant=tenant, warehouse=warehouse, product=product,
        defaults={
            "on_hand": Decimal(on_hand),
            "avg_cost": Decimal(avg_cost),
            "stock_value": (Decimal(on_hand) * Decimal(avg_cost)).quantize(Decimal("0.001")),
        },
    )
    return si


@pytest.mark.django_db
def test_patch_cost_syncs_stockitem_avg_cost(api_client, tenant, warehouse):
    """Editar cost desde el catalogo actualiza StockItem.avg_cost."""
    p = _make_product(tenant, cost=Decimal("1000"))
    si = _make_stock(tenant, warehouse, p, on_hand="50.000", avg_cost="1000.000")
    assert si.avg_cost == Decimal("1000.000")
    assert si.stock_value == Decimal("50000.000")

    resp = api_client.patch(PATCH_URL.format(p.id), {"cost": "1.00"}, format="json")
    assert resp.status_code == 200, resp.content

    si.refresh_from_db()
    assert si.avg_cost == Decimal("1.000"), f"avg_cost no se sincronizo: {si.avg_cost}"
    assert si.stock_value == Decimal("50.000"), f"stock_value mal recalculado: {si.stock_value}"

    p.refresh_from_db()
    assert p.cost == Decimal("1.00")


@pytest.mark.django_db
def test_patch_cost_creates_audit_stockmove(api_client, tenant, warehouse):
    """Cada cambio de cost via catalogo deja un StockMove de auditoria."""
    p = _make_product(tenant, cost=Decimal("500"))
    _make_stock(tenant, warehouse, p, on_hand="20.000", avg_cost="500.000")

    moves_before = StockMove.objects.filter(product=p).count()
    resp = api_client.patch(PATCH_URL.format(p.id), {"cost": "10.00"}, format="json")
    assert resp.status_code == 200

    moves = StockMove.objects.filter(
        product=p, reason="MANUAL_COST_ADJUST",
    ).order_by("-created_at")
    assert moves.count() == moves_before + 1
    m = moves.first()
    assert m.move_type == StockMove.ADJ
    assert m.qty == Decimal("0")
    assert m.cost_snapshot == Decimal("10.000")
    # value_delta = nuevo - viejo = (20 × 10) - (20 × 500) = -9800
    assert m.value_delta == Decimal("-9800.000")
    assert "500" in m.note and "10" in m.note


@pytest.mark.django_db
def test_patch_without_cost_change_does_not_touch_stock(api_client, tenant, warehouse):
    """Si no se manda cost en el PATCH, no se toca el StockItem."""
    p = _make_product(tenant, cost=Decimal("500"))
    si = _make_stock(tenant, warehouse, p, on_hand="20.000", avg_cost="500.000")
    moves_before = StockMove.objects.filter(product=p).count()

    resp = api_client.patch(PATCH_URL.format(p.id), {"name": "Nuevo nombre"}, format="json")
    assert resp.status_code == 200

    si.refresh_from_db()
    assert si.avg_cost == Decimal("500.000"), "no debio cambiar avg_cost"
    assert StockMove.objects.filter(product=p).count() == moves_before, "no debio crear move"


@pytest.mark.django_db
def test_patch_cost_same_value_does_not_create_move(api_client, tenant, warehouse):
    """Si mando cost pero es igual al anterior, no se crea move (idempotencia)."""
    p = _make_product(tenant, cost=Decimal("500"))
    _make_stock(tenant, warehouse, p, on_hand="20.000", avg_cost="500.000")
    moves_before = StockMove.objects.filter(product=p).count()

    resp = api_client.patch(PATCH_URL.format(p.id), {"cost": "500"}, format="json")
    assert resp.status_code == 200

    assert StockMove.objects.filter(product=p).count() == moves_before


@pytest.mark.django_db
def test_patch_cost_syncs_all_warehouses(api_client, tenant, store, warehouse):
    """Si el producto tiene stock en N bodegas, TODAS se sincronizan."""
    wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega 2", is_active=True)
    p = _make_product(tenant, cost=Decimal("1000"))
    si1 = _make_stock(tenant, warehouse, p, on_hand="50.000", avg_cost="1000.000")
    si2 = _make_stock(tenant, wh2, p, on_hand="30.000", avg_cost="900.000")  # distinto

    resp = api_client.patch(PATCH_URL.format(p.id), {"cost": "1.00"}, format="json")
    assert resp.status_code == 200

    si1.refresh_from_db(); si2.refresh_from_db()
    assert si1.avg_cost == Decimal("1.000")
    assert si2.avg_cost == Decimal("1.000")
    # Stock_value recalculado en cada bodega segun su on_hand
    assert si1.stock_value == Decimal("50.000")
    assert si2.stock_value == Decimal("30.000")
    # 2 StockMoves de auditoria (1 por bodega)
    moves = StockMove.objects.filter(product=p, reason="MANUAL_COST_ADJUST")
    assert moves.count() == 2
    assert {m.warehouse_id for m in moves} == {warehouse.id, wh2.id}
