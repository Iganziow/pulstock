"""
tests/test_ventas_offline.py — cuadrar el stock tras vender sin sistema.

El pedido de Mario, textual: "poder ajustar inventario tras periodos de venta
sin sistema de larga duración (corte de luz, caída), de manera que no afecte
las ventas del turno en que se realice la actualización".

El backend existía (inventory/offline_sales.py) pero SIN un solo test — y es
código que descuenta stock con fecha retroactiva. Estos tests fijan las tres
promesas del diseño:

  1. El consumo queda fechado el DÍA DEL CORTE, no hoy: el turno actual
     queda limpio (la mitad del pedido de Mario).
  2. El agregador del forecast cuenta ese movimiento como DEMANDA de ese
     día (la otra mitad, la invisible: sin esto el modelo aprende que el
     día del corte no se vendió nada y pide de menos para siempre).
  3. El stock jamás queda negativo, y el descuadre se reporta en vez de
     esconderse.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from inventory.models import StockItem, StockMove

User = get_user_model()
URL = "/api/inventory/offline-sales/"
D = Decimal


@pytest.fixture
def stock(db, tenant, warehouse, product):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=D("100.000"), avg_cost=D("500.000"),
        stock_value=D("50000.000"),
    )


def _post(cliente, warehouse, fecha, lineas, nota="corte de luz"):
    return cliente.post(URL, {
        "date": fecha.isoformat(), "warehouse_id": warehouse.id,
        "note": nota, "lines": lineas,
    }, format="json")


@pytest.mark.django_db
class TestLasTresPromesas:
    def test_descuenta_y_fecha_en_el_dia_del_corte(
        self, api_client, warehouse, product, stock,
    ):
        corte = timezone.localdate() - datetime.timedelta(days=5)
        r = _post(api_client, warehouse, corte,
                  [{"product_id": product.id, "qty": "40"}])
        assert r.status_code == 201, r.data

        stock.refresh_from_db()
        assert stock.on_hand == D("60.000")

        mv = StockMove.objects.get(product=product, ref_type="OFFLINE")
        assert mv.move_type == StockMove.OUT
        # La fecha es la del corte — no hoy. Es la mitad del pedido de Mario:
        # que el turno en que se hace la corrección quede limpio.
        assert timezone.localtime(mv.created_at).date() == corte
        assert mv.qty == D("40.000")

    def test_el_turno_de_hoy_queda_limpio(
        self, api_client, warehouse, product, stock,
    ):
        corte = timezone.localdate() - datetime.timedelta(days=3)
        _post(api_client, warehouse, corte, [{"product_id": product.id, "qty": "10"}])

        hoy = timezone.localdate()
        de_hoy = [m for m in StockMove.objects.filter(product=product)
                  if timezone.localtime(m.created_at).date() == hoy]
        assert de_hoy == [], (
            "la corrección dejó movimientos fechados HOY: el turno actual "
            "aparece consumiendo lo que se vendió el día del corte"
        )

    def test_el_modelo_aprende_la_demanda_del_dia_del_corte(
        self, api_client, tenant, warehouse, product, stock,
    ):
        """LA PROMESA INVISIBLE. Un ajuste normal (ADJ) es invisible para el
        agregador: el modelo aprende que ese día no se vendió y pide de menos
        para siempre. La venta offline entra como demanda del día real."""
        from forecast.models import DailySales

        corte = timezone.localdate() - datetime.timedelta(days=5)
        _post(api_client, warehouse, corte, [{"product_id": product.id, "qty": "40"}])

        call_command("aggregate_daily_sales", date=corte.isoformat(),
                     tenant=tenant.id, verbosity=0)

        ds = DailySales.objects.filter(
            tenant=tenant, product=product, warehouse=warehouse, date=corte,
        ).first()
        assert ds is not None, "el agregador no vio la venta offline"
        assert ds.qty_sold >= D("40"), (
            f"la demanda del día del corte quedó en {ds.qty_sold}, "
            "el modelo va a aprender menos de lo que realmente se vendió"
        )

    def test_no_deja_negativo_y_reporta_el_descuadre(
        self, api_client, warehouse, product, stock,
    ):
        """Vendió 150 pero el sistema creía tener 100: el stock queda en 0
        (no negativo), el movimiento va COMPLETO (la demanda fue 150) y la
        diferencia se avisa — significa que el inventario ya estaba malo
        ANTES del corte, y eso es justo lo que este flujo revela."""
        corte = timezone.localdate() - datetime.timedelta(days=2)
        r = _post(api_client, warehouse, corte,
                  [{"product_id": product.id, "qty": "150"}])
        assert r.status_code == 201, r.data

        stock.refresh_from_db()
        assert stock.on_hand == D("0.000")
        assert stock.stock_value == D("0.000")

        mv = StockMove.objects.get(product=product, ref_type="OFFLINE")
        assert mv.qty == D("150.000"), "recortó la demanda declarada"

        descuadres = r.data.get("descuadres") or []
        assert descuadres, "no avisó que lo declarado superaba el stock"
        assert D(str(descuadres[0]["faltante"])) == D("50")


@pytest.mark.django_db
class TestLosBordes:
    def test_rechaza_fecha_futura(self, api_client, warehouse, product, stock):
        futuro = timezone.localdate() + datetime.timedelta(days=1)
        r = _post(api_client, warehouse, futuro, [{"product_id": product.id, "qty": "1"}])
        assert r.status_code == 400

    def test_rechaza_mas_de_60_dias(self, api_client, warehouse, product, stock):
        viejo = timezone.localdate() - datetime.timedelta(days=61)
        r = _post(api_client, warehouse, viejo, [{"product_id": product.id, "qty": "1"}])
        assert r.status_code == 400

    def test_rechaza_cantidad_cero_sin_aplicar_nada(
        self, api_client, warehouse, product, product_b, stock,
    ):
        """Una línea inválida anula el lote completo (transacción): no puede
        quedar la mitad aplicada."""
        corte = timezone.localdate() - datetime.timedelta(days=1)
        r = _post(api_client, warehouse, corte, [
            {"product_id": product.id, "qty": "10"},
            {"product_id": product_b.id, "qty": "0"},
        ])
        assert r.status_code == 400
        stock.refresh_from_db()
        assert stock.on_hand == D("100.000"), "aplicó la mitad del lote inválido"

    def test_un_producto_de_otro_negocio_rechaza_el_lote(
        self, api_client, warehouse, product, stock,
    ):
        from core.models import Tenant
        from catalog.models import Product

        otro_tenant = Tenant.objects.create(name="Otro Negocio")
        ajeno = Product.objects.create(
            tenant=otro_tenant, name="Ajeno", price=D("1000"), is_active=True,
        )
        corte = timezone.localdate() - datetime.timedelta(days=1)
        r = _post(api_client, warehouse, corte, [{"product_id": ajeno.id, "qty": "5"}])
        assert r.status_code == 400
        assert StockMove.objects.filter(ref_type="OFFLINE").count() == 0

    def test_un_cajero_no_puede(self, db, tenant, store, warehouse, product, stock):
        """La corrección retroactiva de inventario es de inventario/manager —
        exactamente el reparto de roles que pidió Mario."""
        from rest_framework.test import APIClient

        cajero = User.objects.create_user(
            username="cajero_offline", password="testpass123",
            tenant=tenant, active_store=store, role="cashier",
        )
        cliente = APIClient()
        cliente.force_authenticate(user=cajero)
        corte = timezone.localdate() - datetime.timedelta(days=1)
        r = _post(cliente, warehouse, corte, [{"product_id": product.id, "qty": "1"}])
        assert r.status_code == 403
