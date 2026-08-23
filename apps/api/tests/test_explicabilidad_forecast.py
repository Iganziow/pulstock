"""
tests/test_explicabilidad_forecast.py — "ver de dónde sale cada cosa".

Pedido textual de Mario. La sugerencia de compra ya se explicaba sola; la
predicción no. Toda la información estaba guardada —algoritmo, avg_daily,
correcciones por día, productos padre, confianza medida— pero en JSON que solo
sirve para depurar.

Lo que se prueba acá no es que el texto exista: es que **diga la verdad** sobre
el modelo que lo generó. Una explicación que no corresponde con lo que el
sistema realmente hizo es peor que ninguna — enseña algo falso y se descubre
tarde.
"""
import datetime
from decimal import Decimal

import pytest

from catalog.models import Product
from forecast.explain import explicar_ingredientes, explicar_modelo
from forecast.models import ForecastModel

D = Decimal


def _modelo(tenant, warehouse, product, algorithm, params=None, **extra):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm=algorithm, version=1, is_active=True,
        trained_at=datetime.datetime.now(datetime.timezone.utc),
        model_params=params or {}, demand_pattern="smooth",
        **extra,
    )


@pytest.mark.django_db
class TestCadaAlgoritmoSeExplicaDistinto:
    def test_derivado_de_receta_habla_de_los_productos_que_lo_usan(
        self, tenant, warehouse, product,
    ):
        """Un ingrediente no se predice por sus ventas: se predice por lo que
        consumen los platos. Decir 'promedio de ventas' ahí sería mentira."""
        fm = _modelo(tenant, warehouse, product, "ingredient_derived", {
            "avg_daily": "1009.713",
            "parent_products": [1, 2, 3, 4],
        })
        r = explicar_modelo(fm, unidad="ml")
        assert "4 productos" in r["resumen"]
        assert "ingrediente" in r["resumen"]
        assert "1.010 ml" in r["resumen"], r["resumen"]

    def test_intermitente_explica_por_que_no_usa_promedio(
        self, tenant, warehouse, product,
    ):
        """Es la pregunta natural del dueño: '¿por qué no promedias y ya?'"""
        fm = _modelo(tenant, warehouse, product, "croston_sba",
                     {"avg_daily": "3.2"})
        r = explicar_modelo(fm, unidad="unidades")
        assert "no se vende todos los días" in r["resumen"]
        assert "cero" in r["resumen"]

    def test_sin_historial_propio_lo_dice(self, tenant, warehouse, product):
        fm = _modelo(tenant, warehouse, product, "category_prior",
                     {"avg_daily": "0.9"})
        r = explicar_modelo(fm, unidad="unidades")
        assert "categoría" in r["resumen"]
        assert "historial propio" in r["resumen"]

    def test_sin_modelo_no_inventa_una_explicacion(self, tenant):
        r = explicar_modelo(None)
        assert "Todavía no hay una predicción" in r["resumen"]
        assert r["detalles"] == []


@pytest.mark.django_db
class TestLoQueElModeloAprendio:
    def test_cuenta_el_dia_de_semana_con_su_direccion(
        self, tenant, warehouse, product,
    ):
        """Suele ser lo que más sorprende al dueño porque le confirma algo que
        intuía. Si dice 'más' cuando el modelo resta, destruye la confianza."""
        fm = _modelo(tenant, warehouse, product, "simple_avg", {
            "avg_daily": "100",
            "bias_correction": {"dow": {"0": 123.4, "3": -139.9}, "global": 0},
        })
        texto = " ".join(explicar_modelo(fm, unidad="ml")["detalles"])
        assert "los jueves se vende menos" in texto, texto
        assert "los lunes se vende más" in texto, texto

    def test_ignora_correcciones_insignificantes(
        self, tenant, warehouse, product,
    ):
        """Decir 'los martes se vende 0 más' es ruido que resta credibilidad."""
        fm = _modelo(tenant, warehouse, product, "simple_avg", {
            "avg_daily": "100",
            "bias_correction": {"dow": {"1": 0.2, "2": -0.4}, "global": 0},
        })
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "martes" not in texto and "miércoles" not in texto

    def test_la_confianza_viene_con_su_motivo_medido(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(
            tenant, warehouse, product, "simple_avg", {"avg_daily": "50"},
            confidence_label="high",
            confidence_reason="WAPE real 26% en últimos 14 días (10 comparaciones)",
        )
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "confianza es alta" in texto
        assert "26%" in texto
        # Las siglas no se minusculizan: "wAPE" se lee como error de tipeo.
        assert "WAPE" in texto and "wAPE" not in texto

    def test_una_razon_normal_si_encadena_en_minuscula(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(
            tenant, warehouse, product, "simple_avg", {"avg_daily": "50"},
            confidence_label="medium", confidence_reason="Pocos dias de datos",
        )
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "es media: pocos dias" in texto

    def test_con_confianza_baja_sugiere_revisar_antes_de_aprobar(
        self, tenant, warehouse, product,
    ):
        """Una predicción floja que se presenta igual que una sólida es una
        trampa: el dueño aprueba a ciegas y después culpa al sistema."""
        fm = _modelo(
            tenant, warehouse, product, "simple_avg", {"avg_daily": "50"},
            confidence_label="very_low", confidence_reason="pocos datos",
        )
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "revisar la cantidad sugerida" in texto

    def test_avisa_cuando_el_freno_automatico_actuo(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(tenant, warehouse, product, "simple_avg", {
            "avg_daily": "50",
            "circuit_breaker": {"reason": "collapsed_vs_recent_demand"},
        })
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "se había desalineado" in texto

    def test_avisa_cuando_hay_poco_historial(self, tenant, warehouse, product):
        fm = _modelo(tenant, warehouse, product, "simple_avg",
                     {"avg_daily": "50"}, data_points=6)
        texto = " ".join(explicar_modelo(fm, unidad="unidades")["detalles"])
        assert "6 días de historial" in texto


@pytest.mark.django_db
class TestDesgloseDeReceta:
    def test_muestra_que_platos_lo_consumen_y_cuanto(
        self, tenant, warehouse, product, category,
    ):
        """La parte más fácil de verificar para un dueño —'¿de verdad un latte
        lleva 170 ml?'— y por eso la que más confianza genera cuando cuadra."""
        latte = Product.objects.create(
            tenant=tenant, name="Latte", sku="LAT", category=category,
        )
        capu = Product.objects.create(
            tenant=tenant, name="Capuccino", sku="CAP", category=category,
        )
        fm = _modelo(tenant, warehouse, product, "ingredient_derived", {
            "avg_daily": "1000",
            "recipe_multipliers": {str(latte.id): "170.0", str(capu.id): "150.0"},
        })

        filas = explicar_ingredientes(fm)
        assert [f["nombre"] for f in filas] == ["Latte", "Capuccino"], (
            "debe ordenar por cuánto consume cada uno, no por id"
        )
        assert filas[0]["cantidad"] == "170.0"

    def test_un_modelo_que_no_es_de_receta_no_devuelve_desglose(
        self, tenant, warehouse, product,
    ):
        fm = _modelo(tenant, warehouse, product, "simple_avg", {"avg_daily": "10"})
        assert explicar_ingredientes(fm) == []

    def test_ignora_productos_borrados(self, tenant, warehouse, product):
        """Un id que ya no existe no puede romper la pantalla."""
        fm = _modelo(tenant, warehouse, product, "ingredient_derived", {
            "avg_daily": "10",
            "recipe_multipliers": {"999999": "50.0", "abc": "1"},
        })
        assert explicar_ingredientes(fm) == []
