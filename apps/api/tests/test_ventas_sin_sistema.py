"""
tests/test_ventas_sin_sistema.py — cuadrar el stock tras un corte de luz.

Pedido de Mario, textual:

    "Se necesita poder ajustar inventario tras periodos de venta sin sistema de
    larga duración (corte de luz, caída de sistema), de manera que NO AFECTE
    LAS VENTAS DEL TURNO en que se realice la actualización."

El ajuste normal no servía por dos razones, y las dos se prueban acá:

  1. Creaba un movimiento fechado HOY. Si el corte fue el jueves y Mario
     cuadra el sábado, el sábado aparecía consumiendo lo que se vendió dos
     días antes.
  2. Creaba un `ADJ`, que el agregador del forecast NO lee. Esas ventas nunca
     existían para el modelo: la demanda de ese día quedaba en cero, el modelo
     aprendía que se vende menos de lo real, y la sugerencia pedía de menos.
     El error se acumula en cada corte.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import StockItem, StockMove
from inventory.offline_sales import ErrorVentaOffline, registrar_ventas_offline

D = Decimal


@pytest.fixture
def con_stock(db, tenant, warehouse, product):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=D("100"), avg_cost=D("500"),
    )


def _registrar(tenant, warehouse, owner, product, qty, dias_atras=2, nota=""):
    fecha = timezone.localdate() - datetime.timedelta(days=dias_atras)
    return registrar_ventas_offline(
        tenant=tenant, warehouse=warehouse, usuario=owner, fecha=fecha,
        lineas=[{"product_id": product.id, "qty": qty}], nota=nota,
    )


@pytest.mark.django_db
class TestNoContaminaElTurnoActual:
    def test_el_movimiento_queda_fechado_el_dia_del_corte(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """LA MITAD QUE MÁS LE IMPORTA A MARIO. Si cuadra el sábado un corte
        del jueves, el sábado no puede aparecer consumiendo esas unidades."""
        _registrar(tenant, warehouse, owner, product, "40", dias_atras=2)

        mv = StockMove.objects.get(product=product, ref_type="OFFLINE")
        esperada = timezone.localdate() - datetime.timedelta(days=2)
        assert timezone.localtime(mv.created_at).date() == esperada, (
            "quedó fechado hoy: contamina el turno en que se hizo la corrección"
        )

    def test_hoy_no_registra_ningun_movimiento(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        _registrar(tenant, warehouse, owner, product, "40", dias_atras=3)
        hoy = timezone.localdate()
        assert not StockMove.objects.filter(
            product=product, created_at__date=hoy,
        ).exists()

    def test_el_stock_si_se_corrige_ahora(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """La fecha del movimiento es histórica, pero el stock es el de hoy:
        es lo que hay que salir a comprar."""
        _registrar(tenant, warehouse, owner, product, "40")
        con_stock.refresh_from_db()
        assert con_stock.on_hand == D("60.000")


@pytest.mark.django_db
class TestElModeloAprendeDeEseDia:
    def test_se_marca_como_venta_no_como_ajuste(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """Un `ADJ` es invisible para el agregador del forecast. Tiene que ser
        un OUT con ref_type OFFLINE para contarse como demanda."""
        _registrar(tenant, warehouse, owner, product, "40")

        mv = StockMove.objects.get(product=product)
        assert mv.move_type == StockMove.OUT
        assert mv.ref_type == "OFFLINE"
        assert mv.reason == "VENTA_SIN_SISTEMA"

    def test_el_agregador_lo_cuenta_como_demanda(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """La prueba de fondo: sin esto el modelo aprende que ese día no se
        vendió nada y la sugerencia pide de menos, en cada corte."""
        from django.core.management import call_command
        from forecast.models import DailySales

        fecha = timezone.localdate() - datetime.timedelta(days=2)
        _registrar(tenant, warehouse, owner, product, "40", dias_atras=2)

        call_command("aggregate_daily_sales", date=str(fecha),
                     tenant=tenant.id, verbosity=0)

        ds = DailySales.objects.filter(product=product, date=fecha).first()
        assert ds is not None, "el día del corte no generó fila de demanda"
        assert ds.qty_sold == D("40.000"), (
            f"la demanda quedó en {ds.qty_sold}: el modelo va a creer que ese "
            f"día se vendió menos de lo real"
        )


@pytest.mark.django_db
class TestGuardas:
    def test_no_acepta_fechas_futuras(self, tenant, warehouse, owner, product, con_stock):
        with pytest.raises(ErrorVentaOffline, match="futuro"):
            registrar_ventas_offline(
                tenant=tenant, warehouse=warehouse, usuario=owner,
                fecha=timezone.localdate() + datetime.timedelta(days=1),
                lineas=[{"product_id": product.id, "qty": "5"}],
            )

    def test_no_reescribe_historia_muy_vieja(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """Más de dos meses atrás el modelo ya se entrenó con esos datos y las
        cajas están cerradas: corregir ahí hace más daño que bien."""
        with pytest.raises(ErrorVentaOffline, match="60 d"):
            _registrar(tenant, warehouse, owner, product, "5", dias_atras=90)

    def test_rechaza_cantidades_no_positivas(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        with pytest.raises(ErrorVentaOffline, match="mayor que cero"):
            _registrar(tenant, warehouse, owner, product, "0")

    def test_rechaza_productos_de_otro_negocio(
        self, tenant, warehouse, owner, product, con_stock, db,
    ):
        from core.models import Tenant
        from catalog.models import Product
        otro = Tenant(name="Rival", slug="rival-off")
        otro._skip_subscription = True
        otro.save()
        ajeno = Product.objects.create(
            tenant=otro, name="Producto Ajeno", sku="AJE-1",
        )
        with pytest.raises(ErrorVentaOffline, match="otro negocio"):
            registrar_ventas_offline(
                tenant=tenant, warehouse=warehouse, usuario=owner,
                fecha=timezone.localdate() - datetime.timedelta(days=1),
                lineas=[{"product_id": ajeno.id, "qty": "1"}],
            )

    def test_vender_mas_de_lo_que_el_sistema_creia_no_rompe_ni_se_recorta(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        """Mario declara 150 y el sistema creía tener 100.

        El stock NO puede quedar negativo —hay un constraint en la base, y con
        razón: corrompe costeo y valorización—. Pero tampoco se recorta lo
        declarado: si vendió 150, la demanda del día fue 150 y el modelo tiene
        que aprender eso.

        La diferencia significa que el inventario ya venía mal ANTES del corte,
        y este flujo es justo lo que lo revela. Hay que avisarlo, no taparlo.
        """
        r = _registrar(tenant, warehouse, owner, product, "150")

        con_stock.refresh_from_db()
        assert con_stock.on_hand == D("0.000"), "el stock se apoya en cero"

        mv = StockMove.objects.get(product=product, ref_type="OFFLINE")
        assert mv.qty == D("150.000"), (
            "el movimiento se recortó: el modelo va a aprender una demanda "
            "menor a la real"
        )
        assert r["descuadres"], "hay que avisar que el inventario venía mal"
        assert r["descuadres"][0]["faltante"] == "50.000"

    def test_sin_descuadre_no_inventa_alarma(
        self, tenant, warehouse, owner, product, con_stock,
    ):
        r = _registrar(tenant, warehouse, owner, product, "40")
        assert r["descuadres"] == []


@pytest.mark.django_db
class TestEndpoint:
    def test_registra_y_deja_rastro(
        self, api_client, tenant, warehouse, owner, product, con_stock,
    ):
        from core.models import AuditEntry
        fecha = (timezone.localdate() - datetime.timedelta(days=2)).isoformat()

        r = api_client.post("/api/inventory/offline-sales/", {
            "date": fecha,
            "warehouse_id": warehouse.id,
            "note": "corte de luz jueves",
            "lines": [{"product_id": product.id, "qty": "40"}],
        }, format="json")

        assert r.status_code == 201, r.content
        con_stock.refresh_from_db()
        assert con_stock.on_hand == D("60.000")
        assert AuditEntry.objects.filter(action="inventory_offline_sales").exists(), (
            "corregir stock a mano sin dejar rastro es una puerta abierta"
        )

    def test_fecha_invalida_da_error_util(
        self, api_client, tenant, warehouse, product, con_stock,
    ):
        r = api_client.post("/api/inventory/offline-sales/", {
            "date": "ayer",
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": product.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 400
        assert "AAAA-MM-DD" in r.json()["detail"]
