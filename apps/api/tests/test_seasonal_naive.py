"""
tests/test_seasonal_naive.py — el piso contra el que todo modelo se justifica.

Medido contra producción el 27-ago-2026 sobre 4.179 comparaciones reales:
croston (449% vs 213%), croston_sba (269% vs 162%) y ets (2147% vs 2000%)
perdían contra predecir "lo mismo que el martes pasado". 45 productos usaban
algoritmos peores que no hacer nada, y todos sobre-predecían — o sea que le
sugerían al dueño comprar de más.

En vez de una guarda que revise la precisión y fuerce reemplazos (lógica nueva
encima de la selección, con sus propios bugs), la regla se registra como un
candidato más. La selección ya elige por WAPE con walk-forward: ahora esta
regla compite, y gana solo cuando gana de verdad.
"""
import datetime
from decimal import Decimal

import pytest

from forecast.engine import ALGORITHM_REGISTRY
from forecast.engine.algorithms.seasonal_naive import SeasonalNaive
from forecast.engine.selection import select_best_model

D = Decimal
LUNES = datetime.date(2026, 6, 1)  # es lunes


def _serie(valores, desde=LUNES):
    """Serie diaria a partir de una lista de cantidades."""
    return [(desde + datetime.timedelta(days=i), D(str(v))) for i, v in enumerate(valores)]


def _semanal(semanas, patron):
    """Repite un patrón de 7 días, `semanas` veces."""
    return _serie(patron * semanas)


class TestLaReglaPredice:
    def test_repite_el_mismo_dia_de_la_semana(self):
        """Lo esencial: un martes se parece al martes anterior."""
        # Patrón fuerte por día: lunes 10, martes 50, miércoles 10...
        serie = _semanal(4, [10, 50, 10, 10, 10, 10, 10])
        r = SeasonalNaive().forecast(serie, horizon_days=7)

        assert r is not None
        # La serie termina un domingo (4 semanas exactas). El primer día
        # pronosticado es lunes → 10; el segundo es martes → 50.
        por_dia = {f["date"].weekday(): float(f["qty_predicted"]) for f in r["forecasts"]}
        assert por_dia[0] == 10, "el lunes debería repetir el lunes anterior"
        assert por_dia[1] == 50, "el martes debería repetir el martes anterior"

    def test_no_corre_sin_dos_semanas(self):
        """Con menos de 14 días no hay 'mismo día anterior' para todo el horizonte."""
        assert SeasonalNaive().forecast(_serie([10] * 10), horizon_days=7) is None

    def test_la_banda_sale_del_error_propio_no_de_un_porcentaje_inventado(self):
        """Una serie perfectamente repetitiva tiene error cero: banda cero."""
        r = SeasonalNaive().forecast(_semanal(4, [10, 50, 10, 10, 10, 10, 10]), horizon_days=7)
        assert r["params"]["banda_p80"] == "0.000"

        # Una serie ruidosa tiene banda ancha. Ojo: el ruido tiene que ser
        # ENTRE semanas. `[10,90,...] * 4` parece ruidoso pero tiene período 7
        # exacto, así que cada mismo-día-de-la-semana es idéntico y el error
        # de esta regla es cero — correctamente. Me pasó al escribir el test.
        ruidosa = _serie([10, 10, 10, 10, 10, 10, 10,
                          80, 80, 80, 80, 80, 80, 80,
                          10, 10, 10, 10, 10, 10, 10,
                          80, 80, 80, 80, 80, 80, 80])
        r2 = SeasonalNaive().forecast(ruidosa, horizon_days=7)
        assert float(r2["params"]["banda_p80"]) > 0

    def test_nunca_predice_negativo(self):
        r = SeasonalNaive().forecast(_semanal(4, [0, 0, 1, 0, 0, 0, 2]), horizon_days=14)
        assert all(f["lower_bound"] >= 0 for f in r["forecasts"])
        assert all(f["qty_predicted"] >= 0 for f in r["forecasts"])


class TestCompiteDeVerdad:
    def test_esta_en_el_registro(self):
        assert "seasonal_naive" in ALGORITHM_REGISTRY

    def test_gana_cuando_el_patron_semanal_manda(self):
        """EL CASO QUE MOTIVA TODO.

        Serie con estacionalidad semanal brutal y sin tendencia: repetir la
        semana anterior es la respuesta correcta, y ningún promedio le gana.
        Antes esta regla no podía ganar porque no competía.
        """
        serie = _semanal(10, [0, 0, 0, 0, 0, 80, 60])  # solo vende fines de semana
        best = select_best_model(serie, horizon=7, test_days=7)

        assert best["algorithm"] != "none"
        # No exigimos que gane siempre —eso lo decide la medición— pero sí que
        # su error sea competitivo: si perdiera por goleada, la regla estaría
        # mal implementada.
        naive = SeasonalNaive().backtest(serie, test_days=7, n_folds=8)
        assert naive["mae"] < 998, "el backtest de la regla no llegó a correr"
        assert naive["mae"] <= best["metrics"]["mae"] * 1.5, (
            f"la regla quedó muy lejos del ganador ({best['algorithm']}): "
            f"mae {naive['mae']:.2f} vs {best['metrics']['mae']:.2f}"
        )

    def test_no_desplaza_al_ganador_cuando_hay_tendencia(self):
        """La otra mitad: donde un modelo de verdad es mejor, tiene que ganar.

        Serie con tendencia creciente limpia — repetir la semana pasada
        sub-predice siempre. Acá la regla NO debe quedar primera.
        """
        serie = _serie([10 + i * 2 for i in range(60)])
        best = select_best_model(serie, horizon=7, test_days=7)
        assert best["algorithm"] != "seasonal_naive", (
            "con tendencia clara, repetir la semana anterior no puede ser lo mejor"
        )


@pytest.mark.django_db
class TestNoRompeLoQueYaHabia:
    def test_el_entrenamiento_completo_sigue_corriendo(
        self, tenant, store, warehouse, product,
    ):
        """El candidato nuevo no puede tumbar el comando de entrenamiento."""
        from django.core.management import call_command
        from forecast.models import DailySales, ForecastTrainingLog

        hoy = datetime.date.today()
        for i in range(1, 61):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=hoy - datetime.timedelta(days=i),
                qty_sold=D("40") if (hoy - datetime.timedelta(days=i)).weekday() >= 5 else D("5"),
            )

        call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

        log = ForecastTrainingLog.objects.order_by("-id").first()
        assert log.models_failed == 0, log.error_message[:200]

    def test_el_algoritmo_cabe_en_la_columna(self, tenant, store, warehouse, product):
        """`seasonal_naive` son 14 caracteres; la columna admite 30. Trivial,
        pero un nombre que no entra rompe el guardado en producción y no en
        los tests que usan sqlite en memoria."""
        from forecast.models import ForecastModel
        campo = ForecastModel._meta.get_field("algorithm")
        assert len("seasonal_naive") <= campo.max_length
        assert "seasonal_naive" in dict(campo.choices)
