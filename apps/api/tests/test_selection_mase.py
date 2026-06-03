"""
F (01/06/26) — selección por MASE en demanda intermitente/lumpy, con guard
operativo de Croston. Tests de la función pura choose_best.
"""
from forecast.engine.selection import choose_best, MASE_OVERRIDE_MARGIN


def cand(algo, mase, wape, mae, ts=0.0):
    return {
        "algorithm": algo,
        "metrics": {"mase": mase, "wape": wape, "mae": mae, "tracking_signal": ts},
    }


class TestChooseBestIntermittent:
    def test_non_croston_wins_when_mase_clearly_better(self):
        """Un no-Croston con MASE claramente mejor (>15%) destrona a Croston."""
        cands = [
            cand("croston_sba", mase=1.00, wape=120, mae=5),
            cand("adaptive_ma", mase=0.60, wape=90, mae=4),  # 40% mejor MASE
        ]
        best = choose_best(cands, "intermittent")
        assert best["algorithm"] == "adaptive_ma"

    def test_croston_kept_when_mase_competitive(self):
        """Croston se conserva si el no-Croston solo mejora marginalmente (<15%)."""
        cands = [
            cand("croston_sba", mase=1.00, wape=120, mae=5),
            cand("theta", mase=0.90, wape=80, mae=3),  # solo 10% mejor → no alcanza
        ]
        best = choose_best(cands, "intermittent")
        assert best["algorithm"] == "croston_sba"

    def test_croston_wins_when_it_has_best_mase(self):
        cands = [
            cand("croston_sba", mase=0.50, wape=70, mae=2),
            cand("adaptive_ma", mase=0.80, wape=60, mae=1),
        ]
        best = choose_best(cands, "lumpy")
        assert best["algorithm"] == "croston_sba"

    def test_sentinel_mase_croston_loses_to_real_mase(self):
        """Croston con MASE sentinel (serie plana) cede ante un MASE real."""
        cands = [
            cand("croston_sba", mase=999, wape=50, mae=2),
            cand("adaptive_ma", mase=0.85, wape=95, mae=3),
        ]
        best = choose_best(cands, "intermittent")
        assert best["algorithm"] == "adaptive_ma"

    def test_no_croston_picks_lowest_mase(self):
        cands = [
            cand("theta", mase=1.20, wape=100, mae=4),
            cand("adaptive_ma", mase=0.70, wape=110, mae=5),
            cand("ets", mase=0.95, wape=90, mae=3),
        ]
        best = choose_best(cands, "intermittent")
        assert best["algorithm"] == "adaptive_ma"

    def test_margin_boundary(self):
        """Exactamente en el borde del margen: no destrona (necesita < margen)."""
        # best_overall.mase debe ser < croston.mase * 0.85 para ganar.
        # croston=1.0 → umbral 0.85. Un no-croston con 0.85 NO gana (no es <).
        cands = [
            cand("croston_sba", mase=1.00, wape=120, mae=5),
            cand("moving_avg", mase=0.85, wape=70, mae=2),
        ]
        best = choose_best(cands, "intermittent")
        assert best["algorithm"] == "croston_sba", "en el borde, Croston se conserva"


class TestChooseBestSmooth:
    def test_smooth_picks_by_err_wape(self):
        """En smooth se ordena por _err (WAPE + sesgo), no por MASE."""
        cands = [
            cand("theta", mase=0.50, wape=40, mae=3),   # mejor MASE pero peor WAPE
            cand("holt_winters", mase=0.90, wape=20, mae=2),  # mejor WAPE
        ]
        best = choose_best(cands, "smooth")
        assert best["algorithm"] == "holt_winters"

    def test_smooth_bias_penalty_applies(self):
        """Un modelo con WAPE bajo pero TS alto pierde por la penalización."""
        cands = [
            cand("theta", mase=0.9, wape=30, mae=2, ts=10),   # +30pp penalización → 60
            cand("holt_winters", mase=0.9, wape=45, mae=2, ts=0),  # 45
        ]
        best = choose_best(cands, "smooth")
        assert best["algorithm"] == "holt_winters"
