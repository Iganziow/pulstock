"""
Invariante de valorización (jul 2026): stock_value = on_hand × avg_cost SIEMPRE.

Antes se mantenía por deltas acumulados (F("stock_value") ± valor) y drifteaba:
- Venta de producto con avg_cost=0 usaba el fallback Product.cost para el costo
  de la línea (correcto para el margen) pero lo RESTABA de un stock_value=0
  → stock_value NEGATIVO (49 ítems corruptos en prod, ej. "Gretel 85 gr" -4.880).
- Void tras cambio de avg_cost restauraba el value_delta original → drift.

Fix: todas las escrituras recalculan el invariante (stock_value_expr / v3(qty*avg)).
El command recalc_stock_value limpia la data histórica drifteada.
"""
import pytest
from decimal import Decimal

from django.core.management import call_command

from catalog.models import Product, Unit
from inventory.models import StockItem
from sales.services import create_sale

D = Decimal
Q3 = D("0.001")


def _seed(tenant, warehouse, name, *, on_hand, avg_cost, product_cost="0",
          allow_neg=False, price="1000"):
    p = Product.objects.create(
        tenant=tenant, name=name, sku=name.replace(" ", "_"),
        price=D(price), cost=D(str(product_cost)), is_active=True,
        allow_negative_stock=allow_neg,
    )
    si = StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=p,
        on_hand=D(str(on_hand)), avg_cost=D(str(avg_cost)),
        stock_value=(D(str(on_hand)) * D(str(avg_cost))).quantize(Q3),
    )
    return p, si


def _assert_invariant(si):
    si.refresh_from_db()
    expected = (si.on_hand * si.avg_cost).quantize(Q3)
    assert si.stock_value == expected, (
        f"stock_value={si.stock_value} != on_hand({si.on_hand}) × avg_cost({si.avg_cost}) = {expected}"
    )
    return si


# ─────────────────────────────────────────────────────────────────────────────
# El bug de prod: venta con fallback Product.cost sobre avg_cost=0
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sale_with_cost_fallback_does_not_go_negative(tenant, store, warehouse, owner):
    """avg_cost=0 + Product.cost=500 (fallback para el margen): la venta NO debe
    restar el fallback del stock_value → queda 0, no -1000. (Repro 'Gretel')."""
    p, si = _seed(tenant, warehouse, "Gretel 85 gr", on_hand=10, avg_cost=0, product_cost=500)
    res = create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": p.id, "qty": "2", "unit_price": "1000"}],
        payments_in=[{"method": "cash", "amount": "2000"}], sale_type="VENTA",
    )
    si = _assert_invariant(si)
    assert si.on_hand == D("8.000")
    assert si.stock_value == D("0.000")  # NO -1000
    # El margen de la venta SÍ usa el fallback (eso no cambia):
    line = res["sale"].lines.first()
    assert line.unit_cost_snapshot == D("500.000")


@pytest.mark.django_db
def test_normal_sale_maintains_invariant(tenant, store, warehouse, owner):
    p, si = _seed(tenant, warehouse, "Café grano", on_hand=10, avg_cost=100)
    create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": p.id, "qty": "3", "unit_price": "1000"}],
        payments_in=[{"method": "cash", "amount": "3000"}], sale_type="VENTA",
    )
    si = _assert_invariant(si)
    assert si.stock_value == D("700.000")  # 7 × 100


@pytest.mark.django_db
def test_void_after_cost_change_maintains_invariant(tenant, store, warehouse, owner, api_client):
    """Venta a costo 100 → el costo sube a 150 (compra posterior) → void.
    El delta viejo restauraba +300 (drift); el invariante da 10 × 150 = 1500."""
    p, si = _seed(tenant, warehouse, "Torta murta", on_hand=10, avg_cost=100)
    res = create_sale(
        user=owner, tenant_id=tenant.id, store_id=store.id, warehouse_id=warehouse.id,
        lines_in=[{"product_id": p.id, "qty": "3", "unit_price": "1000"}],
        payments_in=[{"method": "cash", "amount": "3000"}], sale_type="VENTA",
    )
    # Simula compra posterior que sube el avg_cost a 150 (invariante consistente)
    StockItem.objects.filter(id=si.id).update(
        avg_cost=D("150.000"), stock_value=D("1050.000"),  # 7 × 150
    )
    r = api_client.post(f"/api/sales/sales/{res['sale'].id}/void/", format="json")
    assert r.status_code == 200, getattr(r, "data", r)
    si = _assert_invariant(si)
    assert si.on_hand == D("10.000")
    assert si.stock_value == D("1500.000")  # 10 × 150 (no 1050+300=1350)


# ─────────────────────────────────────────────────────────────────────────────
# Ajuste / salida / recepción / transferencia
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_adjust_and_issue_maintain_invariant(tenant, warehouse, api_client):
    p, si = _seed(tenant, warehouse, "Servilletas", on_hand=20, avg_cost=50)
    r = api_client.post("/api/inventory/adjust/", {
        "warehouse_id": warehouse.id, "product_id": p.id, "qty": "-5", "note": "merma",
    }, format="json")
    assert r.status_code == 201, r.data
    si = _assert_invariant(si)
    assert si.stock_value == D("750.000")  # 15 × 50

    r = api_client.post("/api/inventory/issue/", {
        "warehouse_id": warehouse.id, "product_id": p.id, "qty": "5",
        "reason": "MERMA", "note": "salida",
    }, format="json")
    assert r.status_code == 201, r.data
    si = _assert_invariant(si)
    assert si.stock_value == D("500.000")  # 10 × 50


@pytest.mark.django_db
def test_receive_with_cost_maintains_invariant(tenant, warehouse, api_client):
    """Recepción con costo recalcula el PPP y el stock_value debe ser
    exactamente new_qty × new_avg (redondeado), no la suma exacta acumulada."""
    p, si = _seed(tenant, warehouse, "Leche entera", on_hand=10, avg_cost=800)
    r = api_client.post("/api/inventory/receive/", {
        "warehouse_id": warehouse.id, "product_id": p.id,
        "qty": "5", "unit_cost": "900",
    }, format="json")
    assert r.status_code == 201, r.data
    si = _assert_invariant(si)  # avg = (8000+4500)/15 = 833.333 → sv = 15 × 833.333


@pytest.mark.django_db
def test_transfer_maintains_invariant_both_sides(tenant, warehouse_a, warehouse_b, api_client):
    p, si_a = _seed(tenant, warehouse_a, "Syrup vainilla", on_hand=30, avg_cost=20)
    # destino con costo distinto y drift preexistente (simula la corrupción)
    si_b = StockItem.objects.create(
        tenant=tenant, warehouse=warehouse_b, product=p,
        on_hand=D("10.000"), avg_cost=D("30.000"), stock_value=D("999.000"),  # drift
    )
    r = api_client.post("/api/inventory/transfer/", {
        "from_warehouse_id": warehouse_a.id, "to_warehouse_id": warehouse_b.id,
        "lines": [{"product_id": p.id, "qty": "10"}],
    }, format="json")
    assert r.status_code == 201, r.data
    _assert_invariant(si_a)
    _assert_invariant(si_b)  # el destino se resincroniza al invariante


# ─────────────────────────────────────────────────────────────────────────────
# Command de limpieza
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_recalc_command_fixes_drifted_and_keeps_healthy(tenant, warehouse):
    healthy_p, healthy_si = _seed(tenant, warehouse, "Sano", on_hand=4, avg_cost=250)
    bad_p, bad_si = _seed(tenant, warehouse, "Corrupto negativo", on_hand=2, avg_cost=1220)
    StockItem.objects.filter(id=bad_si.id).update(stock_value=D("-4880.000"))

    # DRY-RUN: no escribe
    call_command("recalc_stock_value", "--tenant", str(tenant.id))
    bad_si.refresh_from_db()
    assert bad_si.stock_value == D("-4880.000")

    # APPLY: corrige el drifteado, no toca el sano
    call_command("recalc_stock_value", "--tenant", str(tenant.id), "--apply")
    bad_si.refresh_from_db()
    healthy_si.refresh_from_db()
    assert bad_si.stock_value == D("2440.000")  # 2 × 1220
    assert healthy_si.stock_value == D("1000.000")  # intacto
