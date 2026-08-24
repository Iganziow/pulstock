"""
tests/test_minimo_automatico.py — el mínimo que se ajusta solo.

Mario: "que se autoajuste solo". Y tiene razón: nadie configura 252 mínimos a
mano. Se nota — hoy solo 8 de 252 lo tienen puesto, y ninguno de los insumos.

Ya existía un mínimo automático, pero era `avg_daily × 2`: dos días de venta,
plano para todo. Falla por dos lados y los dos se prueban acá:

  · Ignora la variabilidad. Un producto que vende 10±1 y otro que vende 10±8
    recibían el mismo mínimo, cuando el segundo necesita mucho más colchón
    para la misma tranquilidad.
  · Ignora el lead time. Si el proveedor tarda 30 días (ferretería), avisar
    cuando quedan 2 días de stock es avisar tarde.

La fórmula nueva es el punto de reposición clásico, el mismo que la sugerencia
de compra ya usaba del otro lado:

    mínimo = consumo_diario × lead_time + z × σ × √(lead_time)
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from forecast.models import DailySales
from inventory.min_stock import calcular_minimo, explicar, minimo_para
from inventory.models import StockItem

D = Decimal


def _consumo(tenant, warehouse, product, serie, hasta=None):
    """Carga una serie diaria de consumo, del día más viejo al más nuevo."""
    hasta = hasta or timezone.localdate()
    for i, qty in enumerate(reversed(serie)):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=hasta - datetime.timedelta(days=i + 1),
            qty_sold=D(str(qty)),
        )


# ══════════════════════════════════════════════════════════════════════
# LA FÓRMULA
# ══════════════════════════════════════════════════════════════════════

class TestLaFormula:
    def test_cubre_el_consumo_durante_la_espera(self):
        """Lo mínimo que tiene que hacer: aguantar hasta que llegue el pedido."""
        r = calcular_minimo(demanda_diaria=10, desviacion=0,
                            lead_time=5, nivel_servicio=0.95)
        assert r["consumo_esperado"] == 50
        assert r["minimo"] == 50, "sin variabilidad no hace falta colchón"

    def test_mas_variabilidad_pide_mas_colchon(self):
        """EL PUNTO DE TODO ESTO. Dos productos que venden 10 al día pero uno
        parejo y otro errático NO pueden tener el mismo mínimo."""
        parejo = calcular_minimo(10, desviacion=1, lead_time=5)
        erratico = calcular_minimo(10, desviacion=8, lead_time=5)

        # El consumo esperado es igual en los dos (10/día × 5 días): lo que la
        # variabilidad mueve es el colchón, y lo mueve en proporción directa.
        assert erratico["colchon"] == pytest.approx(parejo["colchon"] * 8, rel=0.01)

        # Traducido a negocio: el errático se pide con ~3 días más de respaldo.
        extra_dias = (erratico["minimo"] - parejo["minimo"]) / 10
        assert extra_dias > 2, (
            f"el errático solo lleva {extra_dias:.1f} días más de respaldo que "
            f"el parejo: no lo está protegiendo de nada"
        )

    def test_mas_lead_time_pide_mas_stock(self):
        """Una ferretería con proveedor a 30 días no puede tener el mismo
        mínimo que una cafetería con reposición en 2."""
        cerca = calcular_minimo(10, desviacion=2, lead_time=2)
        lejos = calcular_minimo(10, desviacion=2, lead_time=30)
        assert lejos["minimo"] > cerca["minimo"] * 5

    def test_subir_el_nivel_de_servicio_engorda_el_colchon(self):
        """Es la perilla del dueño: cuánto está dispuesto a quebrar."""
        normal = calcular_minimo(10, desviacion=5, lead_time=5, nivel_servicio=0.95)
        exigente = calcular_minimo(10, desviacion=5, lead_time=5, nivel_servicio=0.99)
        assert exigente["minimo"] > normal["minimo"]

    def test_nunca_devuelve_menos_de_dos_dias(self):
        """Con lead time 0 el mínimo daría casi cero y la alerta llegaría
        cuando ya no queda nada."""
        r = calcular_minimo(10, desviacion=0, lead_time=0)
        assert r["dias_cobertura"] >= 2
        assert r["minimo"] >= 20

    def test_nunca_devuelve_negativo(self):
        r = calcular_minimo(0, desviacion=0, lead_time=5)
        assert r["minimo"] >= 0


# ══════════════════════════════════════════════════════════════════════
# CON DATOS REALES
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSobreElConsumoReal:
    def test_calcula_desde_el_historial(self, tenant, warehouse, product):
        _consumo(tenant, warehouse, product, [10] * 28)
        r = minimo_para(tenant, product, warehouse)
        assert r is not None
        assert r["demanda_diaria"] == pytest.approx(10, abs=0.5)

    def test_los_dias_sin_venta_cuentan(self, tenant, warehouse, product):
        """Promediar solo los días con movimiento infla el mínimo de todo lo
        que rota poco — que es justo el caso de los insumos que Mario quiere
        cubrir (papel higiénico: 5 unidades en 80 días)."""
        # Vende 14 unidades pero solo 2 días de los 28.
        _consumo(tenant, warehouse, product, [7, 7] + [0] * 26)
        r = minimo_para(tenant, product, warehouse)
        assert r["demanda_diaria"] == pytest.approx(0.5, abs=0.1), (
            "promedió solo los días con venta: el mínimo va a quedar inflado"
        )

    def test_sin_consumo_no_devuelve_minimo(self, tenant, warehouse, product):
        """Un producto muerto no necesita mínimo. Ponerle uno hace que la
        alerta ladre por cosas que ya nadie compra."""
        _consumo(tenant, warehouse, product, [0] * 28)
        assert minimo_para(tenant, product, warehouse) is None

    def test_sin_historial_tampoco(self, tenant, warehouse, product):
        assert minimo_para(tenant, product, warehouse) is None

    def test_se_ajusta_solo_cuando_cambia_el_ritmo(
        self, tenant, warehouse, product,
    ):
        """LO QUE PIDIÓ MARIO. Si un producto se pone de moda, su mínimo tiene
        que subir sin que nadie toque nada."""
        _consumo(tenant, warehouse, product, [2] * 28)
        antes = minimo_para(tenant, product, warehouse)["minimo"]

        DailySales.objects.all().delete()
        _consumo(tenant, warehouse, product, [20] * 28)
        despues = minimo_para(tenant, product, warehouse)["minimo"]

        assert despues > antes * 3, (
            f"el ritmo se multiplicó por 10 y el mínimo pasó de {antes:.1f} a "
            f"{despues:.1f}: no está siguiendo al negocio"
        )


# ══════════════════════════════════════════════════════════════════════
# EL COMANDO NOCTURNO
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestComandoNocturno:
    def test_guarda_el_minimo_en_el_stock(self, tenant, warehouse, product):
        from django.core.management import call_command
        si = StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("50"), avg_cost=D("100"),
        )
        _consumo(tenant, warehouse, product, [10] * 28)

        call_command("recalcular_minimos", tenant=tenant.id, verbosity=0)

        si.refresh_from_db()
        assert si.min_stock_auto is not None and si.min_stock_auto > 0
        assert si.min_stock_auto_at is not None

    def test_dry_run_no_guarda(self, tenant, warehouse, product):
        from django.core.management import call_command
        si = StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("50"), avg_cost=D("100"),
        )
        _consumo(tenant, warehouse, product, [10] * 28)

        call_command("recalcular_minimos", "--dry-run", tenant=tenant.id, verbosity=0)
        si.refresh_from_db()
        assert si.min_stock_auto is None

    def test_deja_heartbeat(self, tenant, warehouse, product):
        """Si deja de recalcularse, los mínimos se congelan y la alerta empieza
        a mentir en silencio."""
        from django.core.management import call_command
        from core.models import CronHeartbeat

        call_command("recalcular_minimos", tenant=tenant.id, verbosity=0)
        hb = CronHeartbeat.objects.filter(
            task_name="inventory.recalcular_minimos",
        ).first()
        assert hb is not None and hb.last_result == "ok"


# ══════════════════════════════════════════════════════════════════════
# LA EXPLICACIÓN
# ══════════════════════════════════════════════════════════════════════

class TestSeExplica:
    def test_dice_de_donde_sale_el_numero(self):
        r = calcular_minimo(10, desviacion=4, lead_time=5)
        txt = explicar(r, unidad="unidades")
        assert "10.0 unidades al dia" in txt
        assert "5 dias" in txt
        assert "colchon" in txt

    def test_sin_variabilidad_no_habla_de_colchon(self):
        """Mencionar un colchón de 0 confunde más de lo que aclara."""
        r = calcular_minimo(10, desviacion=0, lead_time=5)
        assert "colchon" not in explicar(r)

    def test_sin_minimo_lo_dice_sin_inventar(self):
        assert "Sin consumo reciente" in explicar(None)


# ══════════════════════════════════════════════════════════════════════
# LA ALERTA LO USA
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestLaAlertaUsaElMinimo:
    """Calcular bien el mínimo no sirve de nada si la alerta sigue avisando
    con la regla vieja. Este es el punto donde el cálculo se vuelve útil."""

    def _alerta(self, tenant, warehouse, product, on_hand, avg_daily, auto=None):
        from inventory.management.commands.send_low_stock_alerts import Command
        si = StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D(str(on_hand)), avg_cost=D("100"),
            min_stock_auto=D(str(auto)) if auto is not None else None,
        )
        return Command()._build_alert(
            si, float(on_hand), product, warehouse.name, avg_daily, None,
        )

    def test_avisa_con_tiempo_para_que_alcance_a_llegar(
        self, tenant, warehouse, product,
    ):
        """Vende 10/día, quedan 35, el proveedor tarda 5 días.

        Con la regla vieja (avg × 2 = 20) no se avisa: 35 > 20. Y cuando se
        avise, quedarán 2 días de stock para una reposición de 5 → quiebre
        seguro. Con el mínimo calculado (~62) se avisa ahora, a tiempo.
        """
        a = self._alerta(tenant, warehouse, product, 35, 10.0, auto=62)
        assert a is not None, (
            "no avisó: el pedido va a llegar después del quiebre"
        )
        assert a["threshold"] == 62

    def test_sin_minimo_calculado_todavia_no_deja_de_avisar(
        self, tenant, warehouse, product,
    ):
        """Producto nuevo, el comando nocturno aún no corrió. Peor es quedarse
        callado: cae a la regla vieja hasta la próxima madrugada."""
        a = self._alerta(tenant, warehouse, product, 15, 10.0, auto=None)
        assert a is not None
        assert a["threshold"] == 20

    def test_el_minimo_manual_le_gana_al_calculado(
        self, tenant, warehouse, product,
    ):
        """Si el dueño puso un número a mano sabe algo que el historial no
        dice. El sistema no lo pisa."""
        product.min_stock = D("100")
        product.save(update_fields=["min_stock"])
        a = self._alerta(tenant, warehouse, product, 80, 10.0, auto=62)
        assert a["reason"] == "manual"
        assert a["threshold"] == 100.0


# ══════════════════════════════════════════════════════════════════════
# EL CASO QUE ORIGINÓ EL PEDIDO
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestProductosLentos:
    """El papel higiénico de Marbrava: 5 unidades en 80 días.

    Es el ejemplo textual de Mario, y era el que peor quedaba. Con ventana de
    28 días muchas veces no hay ni un movimiento, así que el cálculo devolvía
    "sin consumo" — ninguna alerta, nunca. Y aun encontrando el consumo, la
    fórmula da 0,7 unidades: avisar "cuando queden 0,7 rollos" es avisar
    cuando ya no queda ninguno.
    """

    def _papel(self, tenant, warehouse, product, hasta):
        """5 unidades repartidas en 80 días: nada en el último mes."""
        for dias_atras in (34, 48, 55, 68, 79):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=hasta - datetime.timedelta(days=dias_atras), qty_sold=D("1"),
            )

    def test_un_producto_de_rotacion_lenta_igual_recibe_minimo(
        self, tenant, warehouse, product,
    ):
        """Sin esto, el producto que Mario nombró queda fuera del sistema."""
        hasta = timezone.localdate()
        self._papel(tenant, warehouse, product, hasta)

        r = minimo_para(tenant, product, warehouse, hasta=hasta)
        assert r is not None, (
            "quedó sin mínimo: es justo el producto del que se quejó Mario"
        )
        assert r["ventana_dias"] > 28, "debió mirar más atrás para encontrarlo"

    def test_el_minimo_es_accionable_no_una_fraccion(
        self, tenant, warehouse, product,
    ):
        """Medio rollo de papel no es un umbral."""
        hasta = timezone.localdate()
        self._papel(tenant, warehouse, product, hasta)

        r = minimo_para(tenant, product, warehouse, hasta=hasta)
        assert r["minimo"] >= 1, f"avisaría recién con {r['minimo']:.2f} rollos"
        assert r["piso_aplicado"] is True

    def test_da_aviso_con_semanas_de_anticipacion(
        self, tenant, warehouse, product,
    ):
        """La prueba de que sirve: cuánto tiempo tiene Mario para comprar."""
        hasta = timezone.localdate()
        self._papel(tenant, warehouse, product, hasta)

        r = minimo_para(tenant, product, warehouse, hasta=hasta)
        dias_de_aviso = r["minimo"] / r["demanda_diaria"]
        assert dias_de_aviso > 10, (
            f"solo {dias_de_aviso:.0f} días de aviso: no alcanza para comprar"
        )

    def test_la_ventana_corta_se_prefiere_cuando_hay_datos(
        self, tenant, warehouse, product,
    ):
        """Ensanchar siempre haría que el mínimo reaccione tarde a los cambios
        de ritmo. Solo se ensancha cuando la ventana corta viene vacía."""
        _consumo(tenant, warehouse, product, [10] * 28)
        r = minimo_para(tenant, product, warehouse)
        assert r["ventana_dias"] == 28

    def test_en_litros_no_se_fuerza_a_una_unidad(
        self, tenant, warehouse, product, db,
    ):
        """El piso vale para lo que se cuenta entero. En volumen, 0,4 litros
        es una cantidad real y redondearla a 1 sería inventar stock."""
        from catalog.models import Unit
        litro = Unit.objects.create(
            tenant=tenant, code="LT", name="Litro", family="VOLUME", is_base=True,
        )
        product.unit_obj = litro
        product.save(update_fields=["unit_obj"])

        hasta = timezone.localdate()
        self._papel(tenant, warehouse, product, hasta)
        r = minimo_para(tenant, product, warehouse, hasta=hasta)
        assert r["piso_aplicado"] is False
        assert r["minimo"] < 1

    def test_sin_consumo_ni_en_seis_meses_sigue_sin_minimo(
        self, tenant, warehouse, product,
    ):
        """Ensanchar la ventana no puede resucitar productos muertos: sería
        volver a llenar el correo de avisos por cosas que nadie compra."""
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=timezone.localdate() - datetime.timedelta(days=300),
            qty_sold=D("5"),
        )
        assert minimo_para(tenant, product, warehouse) is None

    def test_explica_que_miro_mas_atras(self, tenant, warehouse, product):
        hasta = timezone.localdate()
        self._papel(tenant, warehouse, product, hasta)
        txt = explicar(minimo_para(tenant, product, warehouse, hasta=hasta),
                       unidad="unidades")
        assert "muy de a poco" in txt
        assert "no cuando ya se acabo" in txt

    def test_la_alerta_llega_aunque_no_haya_vendido_en_dos_semanas(
        self, tenant, warehouse, product,
    ):
        """El cierre del caso de Mario.

        La regla 2 estaba condicionada a `avg_daily > 0`, y ese promedio son
        los últimos 14 días. Para el papel higiénico vale CERO. Calcular su
        mínimo no servía de nada: la regla nunca llegaba a evaluarse.
        """
        from inventory.management.commands.send_low_stock_alerts import Command
        si = StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("1"), avg_cost=D("100"), min_stock_auto=D("2"),
        )
        a = Command()._build_alert(si, 1.0, product, warehouse.name, 0.0, None)

        assert a is not None, (
            "silencio: el mínimo se calcula pero la alerta nunca lo mira"
        )
        assert a["reason"] == "auto"
        assert "0 día" not in a["reason_text"], (
            "decir 'te alcanza para 0 días' con un mes de stock es falso"
        )

    def test_un_producto_muerto_en_cero_se_sigue_callando(
        self, tenant, warehouse, product,
    ):
        """La contracara: abrir la reja no puede revivir los 16 descontinuados
        que saqué del correo el mes pasado."""
        from inventory.management.commands.send_low_stock_alerts import Command
        si = StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("0"), avg_cost=D("100"), min_stock_auto=D("2"),
        )
        assert Command()._build_alert(
            si, 0.0, product, warehouse.name, 0.0, None,
        ) is None


# ══════════════════════════════════════════════════════════════════════
# QUE SE PUEDA VER
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSeVeEnLaApi:
    """Si el mínimo solo vive en el correo, Mario no puede contrastarlo con lo
    que ve en pantalla — y un número que no se puede contrastar no se cree."""

    def test_el_listado_de_stock_trae_el_minimo_sugerido(
        self, api_client, tenant, warehouse, product,
    ):
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("10"), avg_cost=D("100"), min_stock_auto=D("2.5"),
        )
        r = api_client.get(f"/api/inventory/stock/?warehouse_id={warehouse.id}")
        assert r.status_code == 200, r.content

        fila = next(f for f in r.json()["results"] if f["product_id"] == product.id)
        assert fila["min_stock_auto"] == "2.500"
        assert fila["min_stock"] == "0.000"

    def test_sin_minimo_calculado_viaja_nulo_no_cero(
        self, api_client, tenant, warehouse, product,
    ):
        """Un cero se lee como 'el mínimo es cero'. Null dice 'todavía no se
        calculó', que es distinto y es la verdad."""
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=product,
            on_hand=D("10"), avg_cost=D("100"),
        )
        r = api_client.get(f"/api/inventory/stock/?warehouse_id={warehouse.id}")
        fila = next(f for f in r.json()["results"] if f["product_id"] == product.id)
        assert fila["min_stock_auto"] is None
