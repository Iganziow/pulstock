"""
Fix auditoría (09/06/26): _session_summary clasificaba LEGACY vs FASE A
comparando sum(SalePayment) contra Sale.SUBTOTAL (pre-descuento). Con un
descuento >= propina, una venta legacy (payment incluye tip embebido) se
mal-clasificaba como Fase A → el cash tip embebido se sumaba OTRA VEZ a
expected_cash → descuadre de caja.

El fix usa Sale.TOTAL (neto post-descuento, sin tip), que es el discriminador
robusto:
  - LEGACY: payment = total + tip  → sum_payments − total = tip > 0
  - FASE A: payment = total        → sum_payments − total = 0

Escenario reproducido:
  venta: subtotal $5.000, descuento $500 → total $4.500, propina cash $300
  payment cash = $4.800 (legacy: incluye la propina)
  Con SUBTOTAL: 4800 − 5000 = −200 → (mal) Fase A → suma 300 de más.
  Con TOTAL:    4800 − 4500 = +300 → (bien) Legacy → no duplica.

expected_cash correcto = fondo 10.000 + 4.800 = 14.800
(la propina ya está dentro de los $4.800 cobrados, no es cash extra).
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from caja.models import CashRegister, CashSession
from sales.models import Sale, SalePayment, SaleTip


@pytest.fixture
def register(db, tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja", is_active=True)


@pytest.mark.django_db
def test_legacy_sale_with_discount_ge_tip_cuadra(
    auth_client, owner, tenant, store, warehouse_a, register,
):
    # 1. Abrir caja con $10.000
    r = auth_client.post(
        reverse("caja-session-open", kwargs={"pk": register.id}),
        data={"initial_amount": "10000"}, format="json",
    )
    assert r.status_code in (200, 201), r.data
    sess_id = r.data["id"]
    sess = CashSession.objects.get(id=sess_id)

    # 2. Venta LEGACY con descuento >= propina (creada directo para simular
    #    datos pre-Fase-A: SalePayment.amount incluye la propina embebida).
    sale = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse_a, created_by=owner,
        subtotal=Decimal("5000.00"), total=Decimal("4500.00"),
        status=Sale.STATUS_COMPLETED, sale_type=Sale.SALE_TYPE_VENTA,
        total_cost=Decimal("0.000"), gross_profit=Decimal("4500.000"),
        tip=Decimal("300.00"), sale_number=1, cash_session=sess,
    )
    SalePayment.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("4800.00"))
    SaleTip.objects.create(sale=sale, tenant=tenant, method="cash", amount=Decimal("300.00"))

    # 3. Live summary
    detail = auth_client.get(reverse("caja-session-detail", kwargs={"pk": sess_id}))
    assert detail.status_code == 200, detail.data
    live = detail.data["live"]

    # La venta legacy se clasifica bien → la propina cash NO se suma de más.
    assert Decimal(live["expected_cash"]) == Decimal("14800.00"), (
        f"descuadre: con el bug (subtotal) daría 15100. live={live}"
    )
    # Venta neta cash = payment(4800) − tip legacy(300) = 4500.
    assert Decimal(live["cash_sales"]) == Decimal("4500.00"), f"live={live}"
    # La propina igual se reporta (informativo).
    assert Decimal(live["cash_tips"]) == Decimal("300.00"), f"live={live}"
