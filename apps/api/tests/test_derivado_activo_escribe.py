"""
tests/test_derivado_activo_escribe.py — el bug que dejó a un producto sin
medirse durante 2,5 meses, en silencio.

Cómo funcionaba
---------------
Un producto que es ingrediente de receta y tiene datos propios suficientes se
entrena dos veces cada noche: el modelo `organic` sobre sus ventas directas, y
un `ingredient_derived` en paralelo como CANDIDATO. El candidato solo escribe
filas de Forecast `if make_active or swapped` — o sea, únicamente la noche en
que le gana al organic.

El problema
-----------
Ganado el swap, el derivado queda activo… pero se lo sigue entrenando como
candidato todas las noches. Y como ya no hay nada contra qué ganar, no vuelve a
swapear nunca. Resultado: deja de escribir sus predicciones.

Sin fila de Forecast para ese día, `track_forecast_accuracy` no tiene con qué
comparar y el producto **deja de medirse para siempre**. No falla nada, no
aparece ningún error: simplemente desaparece de la métrica.

Medido en Marbrava (23-ago-2026): `Leche deslactosada` llevaba desde el 6 de
junio sin una sola fila de accuracy, con pronóstico vigente y vendiendo 4.170
unidades cada 14 días.
"""
import datetime
from decimal import Decimal

import pytest

from catalog.models import Product, Recipe, RecipeLine
from forecast.models import DailySales, Forecast, ForecastModel

D = Decimal


@pytest.fixture
def leche(db, tenant, category):
    """El ingrediente: se consume dentro de recetas."""
    return Product.objects.create(
        tenant=tenant, name="Leche entera", sku="LE-1",
        category=category, price=D("1200"),
    )


@pytest.fixture
def latte(db, tenant, category, leche):
    """El producto padre que la consume."""
    p = Product.objects.create(
        tenant=tenant, name="Latte", sku="LAT-1",
        category=category, price=D("3500"),
    )
    receta = Recipe.objects.create(tenant=tenant, product=p)
    RecipeLine.objects.create(
        tenant=tenant, recipe=receta, ingredient=leche, qty=D("180"),
    )
    return p


def _historial(tenant, warehouse, producto, dias=40, qty="200"):
    """Ventas parejas: suficientes para que entre al camino de datos completos."""
    hoy = datetime.date.today()
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=producto, warehouse=warehouse,
            date=hoy - datetime.timedelta(days=i), qty_sold=D(qty),
        )


def _modelo_derivado_activo(tenant, warehouse, producto):
    """Simula el estado tras un swap ganado: el derivado ya es el activo."""
    return ForecastModel.objects.create(
        tenant=tenant, product=producto, warehouse=warehouse,
        algorithm="ingredient_derived", version=1, is_active=True,
        trained_at=datetime.datetime.now(datetime.timezone.utc),
        data_points=30, demand_pattern="smooth",
        model_params={"avg_daily": "200.000", "parent_products": []},
        metrics={"wape": 20},
    )


@pytest.mark.django_db
class TestDerivadoActivoEscribeSusForecasts:
    def test_un_derivado_ya_activo_deja_filas_para_puntuar(
        self, tenant, store, warehouse, leche, latte,
    ):
        """EL BUG. Con el derivado ya activo, la corrida nocturna tiene que
        seguir escribiendo predicciones — si no, el producto se vuelve
        invisible para la métrica sin que nada falle."""
        from django.core.management import call_command

        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        _modelo_derivado_activo(tenant, warehouse, leche)

        Forecast.objects.all().delete()
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        filas = Forecast.objects.filter(product=leche)
        assert filas.exists(), (
            "el derivado activo no escribió ninguna predicción: el producto "
            "queda sin nada que puntuar y desaparece de la métrica"
        )

    def test_el_entrenamiento_no_aborta_a_mitad_de_camino(
        self, tenant, store, warehouse, leche, latte,
    ):
        """Lo que los otros tres tests de este archivo NO miraban.

        Verificaban el efecto sobre el producto, pero no que el comando hubiera
        llegado al final. Entre el 23 y el 24-ago-2026 un `NameError` en esta
        misma rama abortaba el entrenamiento del negocio a mitad de camino: el
        `except` de tenant se lo tragaba, `ForecastTrainingLog` quedaba en
        `partial` y el comando informaba éxito.

        Producción entrenó **5 modelos en vez de 39** esa noche y los tres
        tests de este archivo siguieron en verde.
        """
        from django.core.management import call_command
        from forecast.models import ForecastTrainingLog

        # Mismo montaje que el primer test de la clase: el error solo aparece
        # con el derivado YA activo, que es cuando se evalua `ya_activo`.
        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        _modelo_derivado_activo(tenant, warehouse, leche)

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        log = ForecastTrainingLog.objects.order_by("-id").first()
        assert log.models_failed == 0, (
            f"el entrenamiento abortó a mitad: {log.error_message[:200]}"
        )
        assert log.status != ForecastTrainingLog.STATUS_PARTIAL

    def test_las_filas_pertenecen_a_un_modelo_activo(
        self, tenant, store, warehouse, leche, latte,
    ):
        """Que existan filas no basta: si las escribió un modelo que quedó
        inactivo, las predicciones y el modelo vigente dicen cosas distintas."""
        from django.core.management import call_command

        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        _modelo_derivado_activo(tenant, warehouse, leche)

        Forecast.objects.all().delete()
        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        filas = list(Forecast.objects.filter(product=leche).select_related("model"))
        assert filas, "sin filas no hay nada que verificar"
        assert any(f.model.is_active for f in filas), (
            "todas las predicciones vigentes las escribió un modelo inactivo"
        )

    def test_el_producto_queda_cubierto_por_la_alarma(
        self, tenant, store, warehouse, leche, latte,
    ):
        """Cierre del círculo: la alarma de cobertura no debe marcarlo ciego."""
        from django.core.management import call_command
        from forecast.coverage import find_coverage_gaps

        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        _modelo_derivado_activo(tenant, warehouse, leche)

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        r = find_coverage_gaps(tenant.id)
        ciegos = {c["product_id"] for c in r["ciegos"]}
        assert leche.id not in ciegos

    def test_la_prediccion_del_dia_sobrevive_a_la_corrida_de_esta_noche(
        self, tenant, store, warehouse, leche, latte,
    ):
        """El agujero que quedó abierto después del arreglo anterior.

        `track_forecast_accuracy` corre a las 04:30 y puntúa el día ANTERIOR.
        O sea que la fila escrita anoche tiene que seguir viva a la mañana
        siguiente. No lo estaba: `train_product_model` desactiva todos los
        modelos activos del producto —el derivado incluido— y recién después
        se preguntaba `ya_activo`, que por eso daba False siempre. El producto
        caía en la rama de candidato, cuyo `.delete()` se lleva el modelo y,
        por `on_delete=CASCADE`, sus filas de Forecast.

        Medido en producción tres noches seguidas (25/26/27-ago-2026): los
        pronósticos arrancaban el 26, después el 27, después el 28 — la
        ventana se corría un día cada noche y la fila del día en curso
        desaparecía antes de que llegaran las ventas para compararla.
        """
        from django.core.management import call_command

        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        fm = _modelo_derivado_activo(tenant, warehouse, leche)

        # La predicción de anoche para hoy: es la que el track de mañana
        # necesita encontrar.
        ayer = datetime.date.today() - datetime.timedelta(days=1)
        Forecast.objects.create(
            tenant=tenant, product=leche, warehouse=warehouse, model=fm,
            forecast_date=ayer, qty_predicted=D("200"),
            lower_bound=D("150"), upper_bound=D("250"),
        )

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        assert Forecast.objects.filter(product=leche, forecast_date=ayer).exists(), (
            "la corrida nocturna borró la predicción de una fecha ya cumplida: "
            "nadie va a poder puntuarla y el producto desaparece de la métrica"
        )

    def test_el_derivado_ya_activo_no_se_borra_a_si_mismo(
        self, tenant, store, warehouse, leche, latte,
    ):
        """Fija el ORDEN, que es la causa raíz.

        Sin filas pasadas que lo protejan, un derivado que ya era el activo
        tiene que seguir existiendo después de la corrida — desactivado si
        perdió, pero no borrado. Si desaparece es que `ya_activo` se evaluó
        tarde y el producto volvió a la rama de candidato.
        """
        from django.core.management import call_command

        _historial(tenant, warehouse, leche)
        _historial(tenant, warehouse, latte, qty="20")
        fm = _modelo_derivado_activo(tenant, warehouse, leche)

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        assert ForecastModel.objects.filter(id=fm.id).exists(), (
            "el derivado que ya era el activo se borró a sí mismo: "
            "`ya_activo` se evaluó después de que train_product_model lo desactivara"
        )
