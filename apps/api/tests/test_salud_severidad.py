"""
tests/test_salud_severidad.py — que la alarma suene solo cuando hay que ir.

`/api/core/health/deep/` devolvía 503 ante cualquier problema: base caída,
disco lleno, o un aviso de que 6 productos no se estaban midiendo. Los tres,
el mismo código.

El resultado medido: la salud de producción estuvo en rojo permanente durante
días por el aviso de cobertura del forecast. Información útil, urgencia
equivocada. Y una alarma que suena siempre no la lee nadie — el día que se
caiga la base de verdad va a parecer más de lo mismo.

Ahora el código HTTP responde UNA pregunta: **¿hay que actuar ahora?**
  · 200 — la plataforma responde (aunque haya avisos pendientes)
  · 503 — algo se detuvo y hay que ir

El estado detallado sigue completo en el cuerpo, para quien lo mire.
"""
import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import CronHeartbeat


def _latido(nombre, resultado="ok", edad_min=0):
    hb = CronHeartbeat.objects.create(
        task_name=nombre, last_result=resultado, expected_max_age_minutes=90,
    )
    if edad_min:
        # last_run_at es auto_now: hay que pisarlo con update().
        CronHeartbeat.objects.filter(pk=hb.pk).update(
            last_run_at=timezone.now() - datetime.timedelta(minutes=edad_min)
        )
    return hb


@pytest.fixture(autouse=True)
def disco_sano(monkeypatch):
    """Aísla del disco de la máquina que corre los tests.

    Sin esto el resultado depende de cuánto espacio libre tenga quien ejecuta
    la suite: en un equipo con el disco lleno TODOS estos tests darían 503 y
    parecería que la clasificación por severidad no funciona.
    """
    import collections
    import shutil
    Uso = collections.namedtuple("Uso", "total used free")
    monkeypatch.setattr(
        shutil, "disk_usage",
        lambda _: Uso(total=100 * 1024**3, used=20 * 1024**3, free=80 * 1024**3),
    )


def _salud(**params):
    return APIClient().get("/api/core/health/deep/", params)


@pytest.mark.django_db
class TestLoQueDespiertaAAlguien:
    def test_todo_sano_responde_200(self):
        _latido("billing.process_renewals")
        r = _salud()
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_una_tarea_de_cobro_caida_si_es_urgente(self):
        """Una renovación que no corre es plata que no entra o un cliente
        cortado sin motivo. Eso sí justifica una alarma."""
        _latido("billing.process_renewals", "failed")
        r = _salud()
        assert r.status_code == 503
        assert r.json()["status"] == "down"

    def test_una_tarea_de_cobro_detenida_tambien(self):
        """No corrió en absoluto es tan grave como que falle."""
        _latido("billing.retry_payments", "ok", edad_min=500)
        assert _salud().status_code == 503

    def test_un_aviso_de_calidad_no_es_una_caida(self):
        """EL CASO QUE ORIGINÓ ESTO. `forecast.check_coverage` tuvo la salud
        en rojo durante días por 6 productos sin medir."""
        _latido("forecast.check_coverage", "failed")
        r = _salud()
        assert r.status_code == 200, (
            "un aviso de calidad de pronóstico apagaba el monitor entero"
        )
        assert r.json()["status"] == "degraded", (
            "tampoco puede decir que está todo bien: el problema existe"
        )

    def test_el_aviso_igual_queda_registrado(self, settings):
        """Bajar la urgencia no es esconder: tiene que poder consultarse."""
        settings.DEEP_HEALTH_TOKEN = "secreto"
        _latido("forecast.check_coverage", "failed")
        cron = _salud(token="secreto").json()["checks"]["cron"]
        assert "forecast.check_coverage" in cron["avisos"]
        assert cron["criticas"] == []

    def test_quien_quiera_alertar_por_los_avisos_puede(self):
        """Para el que prefiere vigilar calidad además de disponibilidad."""
        _latido("forecast.check_coverage", "failed")
        assert _salud(strict="1").status_code == 503


@pytest.mark.django_db
class TestUnClienteRotoNoEsLaPlataformaCaida:
    """Lo que pediste: que un tenant con problemas no equivalga a todo caído."""

    def test_una_falla_parcial_no_dispara_la_alarma(self):
        """La tarea corrió y funcionó para los demás negocios. Hay que
        arreglar ese cliente, pero nadie tiene que levantarse."""
        _latido("billing.process_renewals", "partial")
        r = _salud()
        assert r.status_code == 200
        assert r.json()["status"] == "degraded"

    def test_aunque_sea_una_tarea_critica(self):
        """Explícito: ni siquiera en cobros. Con 20 clientes, uno con datos
        raros no puede apagar el monitor de los otros 19."""
        _latido("billing.suspend_overdue", "partial")
        assert _salud().status_code == 200

    def test_pero_si_fallo_para_todos_si_es_caida(self):
        """`failed` significa que ninguno se procesó: se rompió algo común."""
        _latido("billing.suspend_overdue", "failed")
        assert _salud().status_code == 503

    def test_el_detalle_separa_los_tres_estados(self, settings):
        settings.DEEP_HEALTH_TOKEN = "secreto"
        _latido("billing.process_renewals", "partial")
        _latido("forecast.check_coverage", "failed")
        _latido("printing.cleanup_jobs", "ok")

        cron = _salud(token="secreto").json()["checks"]["cron"]
        assert cron["partial"] == ["billing.process_renewals"]
        assert cron["failed"] == ["forecast.check_coverage"]
        assert cron["criticas"] == []
        assert set(cron["avisos"]) == {
            "billing.process_renewals", "forecast.check_coverage",
        }


@pytest.mark.django_db
class TestSiNoSePuedeSaberEsCritico:
    def test_no_poder_leer_el_estado_de_los_crons_es_caida(self, monkeypatch):
        """Sin datos no hay diagnóstico posible. Asumir que está todo bien
        sería la peor lectura: silencio idéntico al de un sistema sano."""
        from core import models

        def revienta(*a, **kw):
            raise RuntimeError("tabla ilegible")

        monkeypatch.setattr(models.CronHeartbeat.objects, "all", revienta)
        r = _salud()
        assert r.status_code == 503
        assert r.json()["status"] == "down"


@pytest.mark.django_db
class TestElRespaldoEsCritico:
    """Un respaldo que no corre no se nota hasta el día que hay que restaurar.

    Era la única tarea crítica sin heartbeat: `backup.sh` es un script de bash
    y escribía su resultado en un log que nadie abre. Ahora se anota como el
    resto y cuenta como crítico — si el respaldo falla, la alarma suena.
    """

    def test_un_respaldo_fallido_dispara_la_alarma(self):
        _latido("backup.diario", "failed")
        r = _salud()
        assert r.status_code == 503, (
            "el respaldo falló y el monitor se quedó callado"
        )
        assert r.json()["status"] == "down"

    def test_un_respaldo_que_dejo_de_correr_tambien(self):
        """Peor que fallar: no ejecutarse. No deja ni un error que mirar."""
        _latido("backup.diario", "ok", edad_min=3000)
        assert _salud().status_code == 503

    def test_con_el_respaldo_al_dia_no_molesta(self):
        _latido("backup.diario", "ok")
        assert _salud().status_code == 200
