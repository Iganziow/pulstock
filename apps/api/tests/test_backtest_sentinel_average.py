"""
F21.1 (16/06/26): _average_metrics excluía mal los folds centinela.

Un fold con ventana de test degenerada (plana/sin ventas) devuelve 999 en las
métricas de ratio (mape/wape/mase/smape). Promediarlo con folds buenos producía
valores falsos: 1 centinela de 3 → 333, 2 de 3 → 666. Eso es justo lo que se
veía en prod como "outliers" de MASE (Syrup avellana MASE 666, etc.) e inflaba
la media a 94. Peor: arruinaba la selección de algoritmo (Croston perdía por un
centinela, no por su error real).

Fix: las métricas de ratio promedian SOLO folds informativos (< 900). Las
absolutas (mae/rmse/bias) siguen promediando todos los folds.
"""
import pytest
from forecast.engine.utils import _average_metrics


def _fold(mae=1.0, mape=50.0, wape=50.0, rmse=1.0, bias=0.0, mase=0.5, smape=50.0, ts=0.0):
    return {"mae": mae, "mape": mape, "wape": wape, "rmse": rmse, "bias": bias,
            "mase": mase, "smape": smape, "tracking_signal": ts}


class TestSentinelExcludedFromAverage:

    def test_one_sentinel_of_three_does_not_become_333(self):
        folds = [
            _fold(mase=999, wape=999, mape=999, smape=999),  # ventana plana
            _fold(mase=0.5, wape=40, mape=45, smape=48),
            _fold(mase=0.5, wape=40, mape=45, smape=48),
        ]
        avg = _average_metrics(folds)
        # ANTES: (999+0.5+0.5)/3 = 333.3. AHORA: (0.5+0.5)/2 = 0.5
        assert avg["mase"] == 0.5, f"esperaba 0.5, got {avg['mase']}"
        assert avg["wape"] == 40.0
        assert avg["mase"] < 5  # ya no es un falso outlier

    def test_two_sentinels_of_three_does_not_become_666(self):
        folds = [
            _fold(mase=999, wape=999),
            _fold(mase=999, wape=999),
            _fold(mase=0.6, wape=42),
        ]
        avg = _average_metrics(folds)
        # ANTES: (999+999+0.6)/3 = 666.2. AHORA: 0.6
        assert avg["mase"] == 0.6
        assert avg["wape"] == 42.0

    def test_all_sentinels_stays_999(self):
        """Si NINGÚN fold es evaluable, la métrica queda 999 (honesto: no se
        puede medir)."""
        folds = [_fold(mase=999, wape=999, mape=999, smape=999) for _ in range(3)]
        avg = _average_metrics(folds)
        assert avg["mase"] == 999
        assert avg["wape"] == 999

    def test_no_sentinels_normal_average(self):
        folds = [_fold(mase=0.4, wape=30), _fold(mase=0.6, wape=50)]
        avg = _average_metrics(folds)
        assert avg["mase"] == 0.5
        assert avg["wape"] == 40.0

    def test_absolute_metrics_average_all_folds(self):
        """mae/rmse/bias NO usan centinela → promedian todos los folds,
        incluido el de ventana plana (su mae es real)."""
        folds = [
            _fold(mae=2.0, rmse=3.0, bias=1.0, mase=999),  # plana pero mae real
            _fold(mae=0.0, rmse=0.0, bias=0.0, mase=0.5),
        ]
        avg = _average_metrics(folds)
        assert avg["mae"] == 1.0   # (2.0 + 0.0) / 2
        assert avg["rmse"] == 1.5
        assert avg["bias"] == 0.5
        # pero mase excluye el centinela
        assert avg["mase"] == 0.5

    def test_empty_returns_sentinels(self):
        avg = _average_metrics([])
        assert avg["mae"] == 999
        assert avg["mase"] == 999

    def test_realistic_croston_no_longer_loses_to_sentinel(self):
        """Escenario real: Croston tiene 1 fold plano (centinela) + 2 buenos.
        Antes su MASE promediado era 333 y perdía contra adaptive_ma (0.9).
        Ahora su MASE real (0.45) le gana."""
        croston = _average_metrics([
            _fold(mase=999), _fold(mase=0.4), _fold(mase=0.5),
        ])
        adaptive = _average_metrics([
            _fold(mase=0.9), _fold(mase=0.9), _fold(mase=0.9),
        ])
        assert croston["mase"] == 0.45
        assert croston["mase"] < adaptive["mase"], "Croston ahora gana con su MASE real"
