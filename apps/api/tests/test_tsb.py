"""
tests/test_tsb.py — el algoritmo que sí se entera de que dejaste de vender.

Medido en producción el 31-ago-2026, sobre 30 días de comparaciones reales:

    croston       n=335   WAPE 251%   sesgo +95%
    croston_sba   n=637   WAPE 220%   sesgo +93%

39 productos sugiriendo casi el doble de lo que se vende, todos los días.
La causa es estructural: Croston solo actualiza sus estimaciones los días CON
venta, así que una racha de ceros no le dice nada y se queda congelado en el
último nivel alto que vio.

Lo que estos tests fijan es exactamente esa diferencia — no que TSB "sea
mejor" en abstracto, sino que decae donde Croston se queda pegado.
"""
import datetime
from decimal import Decimal

import pytest

from forecast.engine import ALGORITHM_REGISTRY
from forecast.engine.algorithms.croston import _croston_forecast
from forecast.engine.algorithms.tsb import TSBForecast, _tsb_forecast

D = Decimal
INICIO = datetime.date(2026, 6, 1)


def _serie(valores, desde=INICIO):
    return [(desde + datetime.timedelta(days=i), D(str(v))) for i, v in enumerate(valores)]


def _predicho(resultado):
    return float(resultado["forecasts"][0]["qty_predicted"])


class TestLoQueMotivaTodo:
    def test_decae_cuando_el_producto_deja_de_venderse(self):
        """EL CASO DEL HELADO EN INVIERNO.

        Vendió fuerte 40 días y lleva 30 sin vender ni una unidad. Croston no
        se entera —solo mira los días con venta— y sigue pronosticando el
        verano. TSB baja la probabilidad en cada cero.
        """
        vendia = [10, 0, 12, 0, 8, 0, 11] * 6   # 42 días activos
        seco = [0] * 30                          # y después, nada
        serie = _serie(vendia + seco)

        tsb = _predicho(_tsb_forecast(serie, horizon_days=7))
        cro = _predicho(_croston_forecast(serie, horizon_days=7))

        assert tsb < cro, (
            f"TSB ({tsb:.2f}) debería predecir MENOS que Croston ({cro:.2f}) "
            "tras 30 días secos — ese es el motivo de que exista"
        )
        assert tsb < 1.0, (
            f"tras 30 días sin vender, TSB sigue pidiendo {tsb:.2f}/día"
        )

    def test_croston_efectivamente_se_queda_pegado(self):
        """La otra mitad de la afirmación, para que no sea palabra mía.

        Si Croston reaccionara a los ceros, TSB no haría falta. Este test
        documenta que NO reacciona: su predicción es casi la misma con y sin
        un mes de sequía encima.
        """
        activa = _serie([10, 0, 12, 0, 8, 0, 11] * 6)
        con_sequia = _serie([10, 0, 12, 0, 8, 0, 11] * 6 + [0] * 30)

        antes = _predicho(_croston_forecast(activa, horizon_days=7))
        despues = _predicho(_croston_forecast(con_sequia, horizon_days=7))

        assert abs(antes - despues) / antes < 0.10, (
            f"Croston sí reaccionó ({antes:.2f} -> {despues:.2f}); "
            "revisar la premisa de este módulo"
        )

    def test_vuelve_a_subir_si_el_producto_revive(self):
        """El helado en primavera. Si solo bajara, sería un apagador, no un
        estimador: tiene que recuperarse sin reentrenar nada."""
        muerto = _serie([10, 0, 12, 0, 8, 0, 11] * 4 + [0] * 30)
        revivido = _serie([10, 0, 12, 0, 8, 0, 11] * 4 + [0] * 30
                          + [9, 0, 10, 0, 11, 0, 12] * 3)

        bajo = _predicho(_tsb_forecast(muerto, horizon_days=7))
        alto = _predicho(_tsb_forecast(revivido, horizon_days=7))

        assert alto > bajo, f"no se recuperó: {bajo:.2f} -> {alto:.2f}"


class TestSeComportaBien:
    def test_no_predice_negativo_nunca(self):
        for serie in (_serie([0] * 20 + [5]), _serie([100] + [0] * 40),
                      _serie([0, 0, 3, 0, 0, 1] * 5)):
            r = _tsb_forecast(serie, horizon_days=14)
            if r is None:
                continue
            assert all(f["qty_predicted"] >= 0 for f in r["forecasts"])
            assert all(f["lower_bound"] >= 0 for f in r["forecasts"])

    def test_series_imposibles_devuelven_None_en_vez_de_reventar(self):
        assert _tsb_forecast(_serie([]), horizon_days=7) is None
        assert _tsb_forecast(_serie([0] * 30), horizon_days=7) is None   # nunca vendió
        assert _tsb_forecast(_serie([5, 0, 0]), horizon_days=7) is None  # muy corta

    def test_una_venta_excepcional_no_fija_el_nivel(self):
        """Init por mediana, no por promedio: un día raro no debe mandar."""
        normal = _serie([2, 0, 3, 0, 2, 0, 3] * 5)
        con_pico = _serie([2, 0, 3, 0, 2, 0, 500] + [2, 0, 3, 0, 2, 0, 3] * 4)

        a = _predicho(_tsb_forecast(normal, horizon_days=7))
        b = _predicho(_tsb_forecast(con_pico, horizon_days=7))
        assert b < a * 4, f"el pico de 500 arrastró el nivel: {a:.2f} -> {b:.2f}"

    def test_el_backtest_tunea_alpha_y_beta(self):
        serie = _serie([8, 0, 0, 9, 0, 0, 7] * 8)
        m = TSBForecast().backtest(serie, test_days=7, n_folds=5)
        assert m["mae"] < 998, "el backtest no llegó a correr"
        assert 0 < m["best_alpha"] <= 0.3
        assert 0 < m["best_beta"] <= 0.2


class TestCompiteDeVerdad:
    def test_esta_en_el_registro_y_en_los_patrones_de_croston(self):
        assert "tsb" in ALGORITHM_REGISTRY
        algo = ALGORITHM_REGISTRY["tsb"]()
        # Tiene que competir exactamente donde Croston manda hoy, o no
        # sirve de nada.
        assert algo.demand_patterns == ["intermittent", "lumpy"]

    def test_cabe_en_la_columna_y_esta_en_las_opciones(self):
        from forecast.models import ForecastModel
        campo = ForecastModel._meta.get_field("algorithm")
        assert len("tsb") <= campo.max_length
        assert "tsb" in dict(campo.choices)


@pytest.mark.django_db
class TestNoRompeElEntrenamiento:
    def test_el_comando_completo_sigue_corriendo(self, tenant, store, warehouse, product):
        """Un algoritmo nuevo no puede tumbar la corrida nocturna."""
        from django.core.management import call_command
        from forecast.models import DailySales, ForecastTrainingLog

        hoy = datetime.date.today()
        patron = [7, 0, 0, 9, 0, 0, 8]
        for i in range(1, 61):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=hoy - datetime.timedelta(days=i),
                qty_sold=D(str(patron[i % 7])),
            )

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        log = ForecastTrainingLog.objects.order_by("-id").first()
        assert log.models_failed == 0, (log.error_message or "")[:200]


class TestTSBEstaEnLaFamiliaProtegida:
    """El guard de `choose_best` conserva "el algoritmo disenado para demanda
    intermitente" salvo que otro le gane por 15% (MASE_OVERRIDE_MARGIN).

    Al agregar TSB quedo FUERA de esa lista: tenia que superar a Croston por
    ese margen aunque fuese el mejor candidato absoluto. Medido sobre las 79
    series intermitentes reales de produccion, TSB ganaba 5 de 79; con el
    arreglo gana 25, y adaptive_ma --el peor sesgo real, +198%-- baja de 6 a 2.
    """

    def _cand(self, alg, wape_total, mase=0.8, n=14):
        return {
            "algorithm": alg,
            "forecasts": [{"qty_predicted": Decimal("1.0")} for _ in range(n)],
            "metrics": {"mae": 1.0, "mape": 50, "rmse": 1.0, "bias": 0,
                        "wape": wape_total, "wape_total": wape_total, "mase": mase},
        }

    def test_tsb_le_gana_a_croston_sin_necesitar_margen(self):
        """Antes: TSB mejor que Croston pero por <15% -> ganaba Croston."""
        from forecast.engine.selection import choose_best

        cands = [
            self._cand("croston_sba", 60.0),
            self._cand("tsb", 55.0),          # mejor, pero solo 8% mejor
        ]
        ganador = choose_best(cands, "intermittent")
        assert ganador["algorithm"] == "tsb", (
            "TSB era el mejor de la familia intermitente y perdio contra "
            "Croston: sigue fuera del guard"
        )

    def test_croston_sigue_ganando_cuando_es_mejor(self):
        """El arreglo no puede volverse un favoritismo hacia TSB."""
        from forecast.engine.selection import choose_best

        cands = [
            self._cand("croston_sba", 40.0),
            self._cand("tsb", 70.0),
        ]
        assert choose_best(cands, "intermittent")["algorithm"] == "croston_sba"

    def test_un_forastero_claramente_mejor_sigue_ganando(self):
        """El guard nunca fue un veto: con ventaja clara (>15%) el de afuera
        gana igual. Si esto se rompe, adaptive_ma/theta quedan bloqueados."""
        from forecast.engine.selection import choose_best

        cands = [
            self._cand("croston_sba", 80.0),
            self._cand("tsb", 75.0),
            self._cand("adaptive_ma", 20.0),   # muy por debajo del margen
        ]
        assert choose_best(cands, "adaptive_ma" and "intermittent")["algorithm"] == "adaptive_ma"

    def test_en_smooth_el_guard_no_aplica(self):
        """La familia protegida es solo para intermittent/lumpy."""
        from forecast.engine.selection import choose_best

        cands = [self._cand("tsb", 60.0), self._cand("theta", 30.0)]
        assert choose_best(cands, "smooth")["algorithm"] == "theta"
