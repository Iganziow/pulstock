"""
tests/test_pipeline_secuencial.py — que los pasos esperen, y que sepan cuándo parar.

Los cinco pasos de la noche estaban encadenados por RELOJ: cada uno arrancaba a
su hora pase lo que pase. Medido en producción el 24-ago-2026, el pipeline
entero tarda 28,7 s por negocio y la ventana entre entrenamiento y sugerencias
es de 30 minutos:

    30 min / 28,7 s = ~62 negocios

Pasado ese número, las sugerencias arrancaban con el entrenamiento a medias y
se calculaban sobre modelos parcialmente actualizados. Sin fallar y sin avisar.

Encadenando por terminación el tiempo total deja de importar. Pero eso obliga a
decidir algo que el reloj resolvía por omisión: **qué hacer cuando un paso
falla**. Los pasos dependen unos de otros, así que la respuesta no es la misma
en todos los casos, y es lo que se prueba acá.
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.multi_tenant import FallaParcial


@pytest.fixture
def espia_pasos(monkeypatch):
    """Reemplaza los pasos reales por un registro de quién fue llamado."""
    import forecast.management.commands.run_nightly_pipeline as mod

    llamados = []

    def falso(nombre, **kw):
        llamados.append(nombre)

    monkeypatch.setattr(mod, "call_command", falso)
    return llamados


@pytest.mark.django_db
class TestElOrdenSeRespeta:
    def test_corre_los_cinco_pasos_en_orden(self, espia_pasos):
        """El orden no es arbitrario: sin demanda agregada no hay nada que
        entrenar, y sin modelos no hay sugerencia que generar."""
        call_command("run_nightly_pipeline", verbosity=0)
        assert espia_pasos == [
            "aggregate_daily_sales",
            "track_forecast_accuracy",
            "compute_category_profiles",
            "train_forecast_models",
            "generate_purchase_suggestions",
        ]

    def test_dry_run_no_ejecuta_nada(self, espia_pasos):
        call_command("run_nightly_pipeline", "--dry-run", verbosity=0)
        assert espia_pasos == []


@pytest.mark.django_db
class TestCuandoUnPasoFallaDelTodo:
    """Falla total = ningún negocio se procesó. Se rompió algo común y seguir
    solo produciría resultados basura sobre datos incompletos."""

    def _falla_en(self, monkeypatch, paso, excepcion):
        import forecast.management.commands.run_nightly_pipeline as mod
        llamados = []

        def falso(nombre, **kw):
            llamados.append(nombre)
            if nombre == paso:
                raise excepcion

        monkeypatch.setattr(mod, "call_command", falso)
        return llamados

    def test_corta_la_cadena(self, monkeypatch):
        llamados = self._falla_en(
            monkeypatch, "compute_category_profiles", CommandError("base caída"),
        )
        with pytest.raises(CommandError):
            call_command("run_nightly_pipeline", verbosity=0)

        assert "train_forecast_models" not in llamados, (
            "entrenó sobre datos incompletos en vez de detenerse"
        )
        assert "generate_purchase_suggestions" not in llamados

    def test_dice_en_que_paso_se_detuvo(self, monkeypatch):
        """Si solo dijera 'falló', habría que leer el log entero para saber
        cuánto del pipeline alcanzó a correr."""
        self._falla_en(monkeypatch, "train_forecast_models", CommandError("x"))
        with pytest.raises(CommandError, match="paso 4/5"):
            call_command("run_nightly_pipeline", verbosity=0)

    def test_tambien_corta_ante_un_error_inesperado(self, monkeypatch):
        """No solo CommandError: cualquier excepción del paso detiene todo."""
        self._falla_en(monkeypatch, "aggregate_daily_sales", ValueError("boom"))
        with pytest.raises(CommandError, match="paso 1/5"):
            call_command("run_nightly_pipeline", verbosity=0)


@pytest.mark.django_db
class TestCuandoFallaSoloUnNegocio:
    """LA DISTINCIÓN QUE IMPORTA. Si el paso funcionó para los demás negocios,
    los sanos tienen derecho a su entrenamiento y a su sugerencia."""

    def _parcial_en(self, monkeypatch, paso):
        import forecast.management.commands.run_nightly_pipeline as mod
        llamados = []

        def falso(nombre, **kw):
            llamados.append(nombre)
            if nombre == paso:
                raise FallaParcial("1 de 3 negocios falló", ok=2, fallidos=1)

        monkeypatch.setattr(mod, "call_command", falso)
        return llamados

    def test_la_cadena_sigue(self, monkeypatch):
        llamados = self._parcial_en(monkeypatch, "compute_category_profiles")
        with pytest.raises(FallaParcial):
            call_command("run_nightly_pipeline", verbosity=0)

        assert "train_forecast_models" in llamados, (
            "un local con una receta rota dejó sin entrenar a todos los demás"
        )
        assert "generate_purchase_suggestions" in llamados

    def test_pero_el_pipeline_igual_reporta_el_problema(self, monkeypatch):
        """Seguir no es tapar: el heartbeat tiene que enterarse."""
        self._parcial_en(monkeypatch, "train_forecast_models")
        with pytest.raises(FallaParcial, match="train_forecast_models"):
            call_command("run_nightly_pipeline", verbosity=0)

    def test_una_falla_parcial_no_es_una_caida_de_plataforma(self, monkeypatch):
        """Se refleja en el heartbeat como 'partial', que la salud lee como
        aviso y no como caída — ver test_salud_severidad.py."""
        from core.models import CronHeartbeat

        self._parcial_en(monkeypatch, "train_forecast_models")
        with pytest.raises(FallaParcial):
            call_command("run_nightly_pipeline", verbosity=0)

        hb = CronHeartbeat.objects.get(task_name="forecast.pipeline_nocturno")
        assert hb.last_result == "partial"


@pytest.mark.django_db
class TestDejaRastro:
    def test_registra_heartbeat_al_terminar_bien(self, espia_pasos):
        from core.models import CronHeartbeat

        call_command("run_nightly_pipeline", verbosity=0)
        hb = CronHeartbeat.objects.get(task_name="forecast.pipeline_nocturno")
        assert hb.last_result == "ok"

    def test_los_pasos_conservan_su_propio_heartbeat(self):
        """Sin esto habría que leer el log para saber cuál falló."""
        from core.models import CronHeartbeat

        call_command("run_nightly_pipeline", verbosity=0)
        registrados = set(CronHeartbeat.objects.values_list("task_name", flat=True))
        assert "forecast.pipeline_nocturno" in registrados
        assert "train_forecast_models" in registrados
        assert "aggregate_daily_sales" in registrados

    def test_el_flag_tenant_llega_a_todos_los_pasos(self, monkeypatch):
        """Se usa para reprocesar un negocio puntual a mano."""
        import forecast.management.commands.run_nightly_pipeline as mod
        recibidos = []

        def falso(nombre, **kw):
            recibidos.append(kw.get("tenant"))

        monkeypatch.setattr(mod, "call_command", falso)
        call_command("run_nightly_pipeline", tenant=7, verbosity=0)
        assert recibidos == [7] * 5
