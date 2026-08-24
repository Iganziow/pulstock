"""
tests/test_pipeline_multi_tenant.py — que un cliente roto no apague a los demás.

El pipeline nocturno recorría los tenants con un `for` pelado:

    for tenant in tenants:
        self._process_tenant(tenant, ...)

Con UN cliente eso funciona. Con tres, la excepción del primero corta el bucle
y los otros dos no se procesan: no se agrega demanda, no se entrenan modelos,
no se generan sugerencias. Y no aparece ningún error por ellos — el comando
muere una sola vez, por el primero, y el resto simplemente no existe en el log.

Peor: **cuál sobrevive depende del orden del queryset**. El mismo fallo deja
distintos clientes sin pronóstico según por dónde empiece.

Cuatro de los cinco comandos del pipeline estaban así. El quinto
(`train_forecast_models`) sí aislaba, pero después se tragaba el error: el
heartbeat quedaba en "ok" y `/health/deep/` en verde con un cliente sin modelos.

Los dos comportamientos se prueban acá, porque hacen falta los dos:
  1. los negocios sanos terminan su trabajo aunque otro falle;
  2. el comando FALLA igual, para que el heartbeat lo registre.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Tenant
from core.multi_tenant import exigir_todos, por_tenant

D = Decimal


class _Falso:
    """Tenant mínimo — el helper solo usa id y name."""
    def __init__(self, id, name):
        self.id, self.name = id, name


# ══════════════════════════════════════════════════════════════════════
# EL HELPER
# ══════════════════════════════════════════════════════════════════════

class TestAislamiento:
    def test_un_negocio_roto_no_frena_a_los_siguientes(self):
        """EL PUNTO DE TODO ESTO."""
        vistos = []

        def procesar(t):
            vistos.append(t.id)
            if t.id == 2:
                raise ValueError("receta rota")

        ok, fallidos = por_tenant([_Falso(1, "A"), _Falso(2, "B"), _Falso(3, "C")], procesar)

        assert vistos == [1, 2, 3], (
            f"solo se procesaron {vistos}: el fallo del segundo dejó al "
            f"tercero sin pronóstico"
        )
        assert ok == 2
        assert len(fallidos) == 1

    def test_el_orden_deja_de_decidir_quien_sobrevive(self):
        """Antes, con el roto primero no se procesaba nadie; con el roto
        último se procesaban todos. Ahora da igual dónde caiga."""
        def corrida(posicion_del_roto):
            vistos = []

            def procesar(t):
                vistos.append(t.id)
                if t.id == posicion_del_roto:
                    raise ValueError("boom")

            por_tenant([_Falso(i, f"T{i}") for i in (1, 2, 3)], procesar)
            return vistos

        assert corrida(1) == corrida(3) == [1, 2, 3]

    def test_recuerda_cual_fallo_y_por_que(self):
        """Sin esto, aislar sería esconder: hay que poder diagnosticarlo."""
        def procesar(t):
            if t.id == 2:
                raise ValueError("receta con qty=0")

        _, fallidos = por_tenant([_Falso(1, "A"), _Falso(2, "Bar Central")], procesar)
        tenant, error = fallidos[0]
        assert tenant.name == "Bar Central"
        assert "qty=0" in str(error)

    def test_sin_fallas_no_levanta(self):
        exigir_todos(3, [])          # no debe lanzar

    def test_con_fallas_levanta_y_nombra_a_los_culpables(self):
        """El heartbeat solo marca "failed" si el comando levanta. Tragarse el
        error dejaría a los sanos andando y al roto invisible — cambiaríamos
        una falla ruidosa por una silenciosa."""
        with pytest.raises(CommandError) as e:
            exigir_todos(2, [(_Falso(7, "Bar Central"), ValueError("boom"))])
        assert "Bar Central" in str(e.value)
        assert "1 de 3" in str(e.value)

    def test_con_muchas_fallas_no_escupe_una_pared_de_texto(self):
        fallidos = [(_Falso(i, f"Local {i}"), ValueError("x")) for i in range(20)]
        with pytest.raises(CommandError) as e:
            exigir_todos(0, fallidos)
        assert "y 15 mas" in str(e.value)


# ══════════════════════════════════════════════════════════════════════
# LOS COMANDOS REALES
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def dos_negocios(db, tenant):
    """El tenant de siempre más otro, para que el bucle tenga dos vueltas."""
    otro = Tenant(name="Bar Central", slug="bar-central-pipeline")
    otro._skip_subscription = True
    otro.save()
    return tenant, otro


@pytest.mark.django_db
class TestElPipelineNoSalteaNegocios:
    """Sin `--tenant`, cada comando tiene que recorrer TODOS los negocios.

    En producción el crontab pasa `--tenant 1` a tres de estas tareas, así que
    un segundo cliente no recibe nada. Estos tests fijan que el código sí
    soporta a todos — el arreglo del crontab es sacar el flag.
    """

    @pytest.mark.parametrize("comando", [
        "aggregate_daily_sales",
        "track_forecast_accuracy",
        "compute_category_profiles",
        "generate_purchase_suggestions",
    ])
    def test_corre_sin_tenant_y_no_explota(self, dos_negocios, comando):
        call_command(comando, verbosity=0)

    @pytest.mark.parametrize("comando", [
        "aggregate_daily_sales",
        "track_forecast_accuracy",
        "compute_category_profiles",
        "generate_purchase_suggestions",
    ])
    def test_visita_a_los_dos_negocios(self, dos_negocios, comando, monkeypatch):
        """Que no falle no alcanza: hay que confirmar que llegó a los dos."""
        from core import multi_tenant

        visitados = []
        original = multi_tenant.por_tenant

        def espia(tenants, procesar, **kw):
            tenants = list(tenants)
            visitados.extend(t.id for t in tenants)
            return original(tenants, procesar, **kw)

        monkeypatch.setattr(multi_tenant, "por_tenant", espia)
        for mod in ("aggregate_daily_sales", "track_forecast_accuracy",
                    "compute_category_profiles", "generate_purchase_suggestions"):
            monkeypatch.setattr(
                f"forecast.management.commands.{mod}.por_tenant", espia, raising=False,
            )

        call_command(comando, verbosity=0)
        esperados = {t.id for t in dos_negocios}
        assert esperados.issubset(set(visitados)), (
            f"visitó {set(visitados)} y faltaban {esperados - set(visitados)}"
        )

    def test_el_flag_tenant_sigue_acotando(self, dos_negocios):
        """Se usa para depurar y para reprocesar un solo negocio: no puede
        romperse al arreglar el recorrido completo."""
        from core import multi_tenant

        _, otro = dos_negocios
        visitados = []
        original = multi_tenant.por_tenant

        def espia(tenants, procesar, **kw):
            tenants = list(tenants)
            visitados.extend(t.id for t in tenants)
            return original(tenants, procesar, **kw)

        import forecast.management.commands.compute_category_profiles as mod
        mod.por_tenant = espia
        try:
            call_command("compute_category_profiles", tenant=otro.id, verbosity=0)
        finally:
            mod.por_tenant = original

        assert visitados == [otro.id]


@pytest.mark.django_db
class TestTodoElPipelineDejaHuella:
    def test_los_cinco_pasos_registran_heartbeat(self, tenant):
        """`compute_category_profiles` era el único sin heartbeat: si dejaba de
        correr, los productos nuevos se quedaban sin prior de categoría y nadie
        se enteraba."""
        from core.models import CronHeartbeat

        for comando in ("aggregate_daily_sales", "track_forecast_accuracy",
                        "compute_category_profiles", "generate_purchase_suggestions"):
            call_command(comando, verbosity=0)

        registrados = set(CronHeartbeat.objects.values_list("task_name", flat=True))
        for esperado in ("aggregate_daily_sales", "track_forecast_accuracy",
                         "compute_category_profiles", "generate_purchase_suggestions"):
            assert esperado in registrados, f"{esperado} corre sin dejar rastro"


@pytest.mark.django_db
class TestConUnNegocioRotoDeVerdad:
    """La prueba que de verdad importa: inyectar una falla en un comando real
    y confirmar que el otro negocio igual recibe su trabajo.

    Los tests de arriba verifican que el comando *visita* a los dos, pero eso
    pasa también con el bucle viejo mientras nadie falle. Acá se rompe uno.
    """

    def test_el_negocio_sano_igual_recibe_su_sugerencia(
        self, dos_negocios, monkeypatch,
    ):
        sano, roto = dos_negocios
        atendidos = []

        import forecast.management.commands.generate_purchase_suggestions as mod

        def falla_para_uno(tenant, *a, **kw):
            if tenant.id == roto.id:
                raise ValueError("receta con qty=0")
            atendidos.append(tenant.id)
            return 0, 0

        monkeypatch.setattr(mod, "generate_suggestions", falla_para_uno)

        with pytest.raises(CommandError):
            call_command("generate_purchase_suggestions", verbosity=0)

        assert sano.id in atendidos, (
            "el negocio sano se quedó sin sugerencia de compra por culpa del "
            "fallo de otro cliente"
        )

    def test_y_el_comando_falla_para_que_quede_registrado(
        self, dos_negocios, monkeypatch,
    ):
        """Aislar sin fallar sería peor: los sanos andando y el roto invisible.
        El heartbeat solo marca "failed" si el comando levanta."""
        from core.models import CronHeartbeat
        _, roto = dos_negocios

        import forecast.management.commands.generate_purchase_suggestions as mod
        monkeypatch.setattr(mod, "generate_suggestions", lambda t, *a, **kw: (_ for _ in ()).throw(ValueError("boom")))

        with pytest.raises(CommandError, match="fallaron"):
            call_command("generate_purchase_suggestions", verbosity=0)

        hb = CronHeartbeat.objects.get(task_name="generate_purchase_suggestions")
        assert hb.last_result == "failed", (
            f"el heartbeat quedó en {hb.last_result!r}: /health/deep/ seguiría "
            f"en verde con un cliente sin sugerencias"
        )

    def test_el_entrenamiento_tambien_falla_si_un_negocio_no_se_entreno(
        self, dos_negocios, monkeypatch,
    ):
        """`train_forecast_models` ya aislaba, pero se tragaba el error: lo
        anotaba en ForecastTrainingLog y devolvía éxito."""
        from core.models import CronHeartbeat
        import forecast.management.commands.train_forecast_models as mod

        def revienta(self, tenant, *a, **kw):
            raise ValueError("sin datos")

        monkeypatch.setattr(mod.Command, "_process_tenant", revienta)

        with pytest.raises(CommandError, match="no se entrenaron"):
            call_command("train_forecast_models", verbosity=0)

        hb = CronHeartbeat.objects.get(task_name="train_forecast_models")
        assert hb.last_result == "failed"
