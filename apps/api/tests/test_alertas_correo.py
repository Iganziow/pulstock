"""
tests/test_alertas_correo.py — las dos alertas que la página de ventas
promete y el sistema no estaba mandando.

Contexto (auditoría de agosto 2026):

  · El ABC semanal existía como tarea de Celery y estaba declarado en
    CELERY_BEAT_SCHEDULE, pero Celery NO corre en producción — todo lo
    periódico se dispara por cron. El correo nunca se envió, ni una vez.

  · La alerta de quiebre estaba pausada desde may-2026. La nota decía
    "hasta que el modelo madure", pero la razón real era otra: avisaba de
    80 productos de 219. Dos fuentes de ruido, medidas sobre datos reales:

        64 preparados por receta (Capuccino, Latte, Cortado…) cuyo on_hand
           es 0 SIEMPRE por diseño — se hacen al momento, no se almacenan.
        16 productos descontinuados: sin stock y sin una sola venta en 30
           días. Cafés de especialidad y golosinas fuera de carta.

    Quedan 8 alertas reales. Eso es un correo que se abre; 80 es uno que se
    archiva sin leer.
"""
import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine
from inventory.models import StockItem
from sales.models import Sale, SaleLine

D = Decimal


@pytest.fixture
def dueño_con_correo(db, owner):
    owner.email = "mario@marbrava.cl"
    owner.first_name = "Mario"
    owner.save(update_fields=["email", "first_name"])
    return owner


@pytest.fixture
def leche(db, tenant, category):
    """Insumo real: se compra, se almacena y se puede quebrar de verdad."""
    return Product.objects.create(
        tenant=tenant, name="Leche entera", sku="LE-1",
        category=category, price=D("1200"),
    )


@pytest.fixture
def capuccino(db, tenant, category, leche):
    """Preparado: se hace al momento, su on_hand es 0 por diseño."""
    p = Product.objects.create(
        tenant=tenant, name="Capuccino", sku="CAP-1",
        category=category, price=D("3500"),
    )
    receta = Recipe.objects.create(tenant=tenant, product=p)
    RecipeLine.objects.create(
        tenant=tenant, recipe=receta, ingredient=leche, qty=D("180"),
    )
    return p


def _sin_stock(tenant, warehouse, producto):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=producto,
        on_hand=D("0"), avg_cost=D("100"),
    )


def _vender(tenant, store, warehouse, user, producto, qty="20"):
    """Le da rotación real al producto: sin esto el sistema no puede
    distinguir un quiebre de un producto que ya nadie compra."""
    venta = Sale.objects.create(
        tenant=tenant, store=store, warehouse=warehouse, created_by=user,
        subtotal=D("10000"), total=D("10000"),
        status="COMPLETED", sale_type="VENTA",
    )
    SaleLine.objects.create(
        tenant=tenant, sale=venta, product=producto,
        qty=D(qty), unit_price=D("500"), unit_cost_snapshot=D("100"),
    )
    return venta


def _cuerpo(msg):
    return msg.body + str(msg.alternatives or "")


# ══════════════════════════════════════════════════════════════════════
# ALERTA DE QUIEBRE
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAlertaDeQuiebre:
    def test_avisa_por_el_insumo_que_de_verdad_falta(
        self, tenant, store, warehouse, dueño_con_correo, leche,
    ):
        """El caso que la alerta existe para cubrir."""
        _sin_stock(tenant, warehouse, leche)
        _vender(tenant, store, warehouse, dueño_con_correo, leche)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        assert len(mail.outbox) == 1, "debe mandar un correo al dueño"
        assert "Leche entera" in _cuerpo(mail.outbox[0])

    def test_no_avisa_por_productos_que_se_preparan_al_momento(
        self, tenant, store, warehouse, dueño_con_correo, capuccino, leche,
    ):
        """RUIDO 1 — 64 de 80 alertas en Marbrava.

        Un capuccino con on_hand=0 no está quebrado: se prepara al momento.
        Lo que hay que vigilar de un capuccino es su leche, y esa entra por
        su cuenta.
        """
        _sin_stock(tenant, warehouse, capuccino)
        _sin_stock(tenant, warehouse, leche)
        _vender(tenant, store, warehouse, dueño_con_correo, capuccino)
        _vender(tenant, store, warehouse, dueño_con_correo, leche)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        cuerpo = _cuerpo(mail.outbox[0])
        assert "Capuccino" not in cuerpo, (
            "avisó por un preparado: su on_hand es 0 por diseño, no es quiebre"
        )
        assert "Leche entera" in cuerpo, "pero sí debe avisar por el insumo"

    def test_no_avisa_por_productos_descontinuados(
        self, tenant, store, warehouse, dueño_con_correo, leche, category,
    ):
        """RUIDO 2 — 16 de 80 alertas en Marbrava.

        Stock 0 y cero ventas no es un quiebre: es un producto que salió de
        carta hace meses.
        """
        muerto = Product.objects.create(
            tenant=tenant, name="Cafe Esp Descontinuado", sku="DESC-1",
            category=category, price=D("9990"),
        )
        _sin_stock(tenant, warehouse, muerto)
        _sin_stock(tenant, warehouse, leche)
        _vender(tenant, store, warehouse, dueño_con_correo, leche)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        cuerpo = _cuerpo(mail.outbox[0])
        assert "Cafe Esp Descontinuado" not in cuerpo, (
            "avisó por un producto sin stock que además no se vende hace meses"
        )
        assert "Leche entera" in cuerpo

    def test_un_minimo_manual_manda_aunque_no_rote(
        self, tenant, warehouse, dueño_con_correo, category,
    ):
        """El mínimo configurado a mano es una decisión explícita del dueño y
        le gana a nuestra heurística de rotación — un estacional que él
        quiere vigilar se sigue avisando."""
        estacional = Product.objects.create(
            tenant=tenant, name="Panettone", sku="PAN-1",
            category=category, price=D("12990"), min_stock=D("10"),
        )
        _sin_stock(tenant, warehouse, estacional)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        assert len(mail.outbox) == 1, "el mínimo manual debe disparar el correo"
        assert "Panettone" in _cuerpo(mail.outbox[0])

    def test_sin_nada_que_avisar_no_molesta(
        self, tenant, store, warehouse, dueño_con_correo, leche,
    ):
        """Si no hay quiebres reales, no se manda correo. Una alerta que
        llega todos los días aunque no pase nada deja de leerse."""
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=leche,
            on_hand=D("500"), avg_cost=D("100"),
        )
        _vender(tenant, store, warehouse, dueño_con_correo, leche, qty="1")

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)
        assert len(mail.outbox) == 0

    def test_dry_run_no_manda_nada(
        self, tenant, store, warehouse, dueño_con_correo, leche,
    ):
        _sin_stock(tenant, warehouse, leche)
        _vender(tenant, store, warehouse, dueño_con_correo, leche)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", "--dry-run", verbosity=0)
        assert len(mail.outbox) == 0


# ══════════════════════════════════════════════════════════════════════
# REPORTE ABC SEMANAL
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestReporteABCSemanal:
    def test_existe_el_comando_que_lo_dispara(self, tenant, store, dueño_con_correo):
        """La tarea existía hace meses; lo que faltaba era quién la llama.
        Celery no corre en producción, así que sin este comando el correo
        que la página promete cada lunes no salía nunca."""
        from django.core.management import get_commands
        assert "send_weekly_abc" in get_commands()

    def test_dry_run_no_manda_nada(self, tenant, store, dueño_con_correo):
        mail.outbox.clear()
        call_command("send_weekly_abc", "--dry-run", verbosity=0)
        assert len(mail.outbox) == 0

    def test_registra_heartbeat_para_que_el_monitoreo_lo_vea(
        self, tenant, store, dueño_con_correo,
    ):
        """Si el envío se rompe tiene que verse en /health/deep/, no
        descubrirse porque un cliente avisa que dejó de recibirlo."""
        from core.models import CronHeartbeat
        call_command("send_weekly_abc", "--dry-run", verbosity=0)
        hb = CronHeartbeat.objects.filter(task_name="reports.weekly_abc").first()
        assert hb is not None, "el comando debe dejar heartbeat"
        assert hb.last_result == "ok"
