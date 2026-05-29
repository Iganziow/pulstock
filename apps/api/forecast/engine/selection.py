"""
Auto model selection — trains eligible algorithms, backtests, picks best.
"""
from datetime import date
from decimal import Decimal
import logging

from .registry import ALGORITHM_REGISTRY
from .patterns import classify_demand_pattern
from .utils import D0
from .algorithms.croston_bootstrap import croston_bootstrap_intervals

logger = logging.getLogger(__name__)


def select_best_model(daily_series, window=21, horizon=14, test_days=7,
                      month_factors=None, demand_pattern=None, stockout_dates=None):
    """
    Train all eligible models, backtest each, return the best one.

    Returns dict:
        algorithm, forecasts, params, metrics, data_points, confidence_base,
        demand_pattern
    """
    n = len(daily_series)
    today = daily_series[-1][0] if daily_series else date.today()

    if demand_pattern is None:
        demand_pattern, adi, cv2 = classify_demand_pattern(daily_series)
    else:
        adi, cv2 = 0, 0

    candidates = []
    ensemble_algo = None

    # Common kwargs for algorithms that need them
    extra_kwargs = {
        "window": window,
        "month_factors": month_factors,
        "stockout_dates": stockout_dates,
        # F8: los algoritmos MA usan el pattern para elegir estacionalidad
        # aditiva (intermittent/lumpy) vs multiplicativa (smooth).
        "demand_pattern": demand_pattern,
    }

    for algo_cls in ALGORITHM_REGISTRY.values():
        algo = algo_cls()

        # Ensemble is handled specially after other candidates
        if algo.name == "ensemble":
            ensemble_algo = algo
            continue

        # Category prior is handled by services.py directly, not auto-selection
        if algo.name == "category_prior":
            continue

        if not algo.is_eligible(n, demand_pattern):
            continue

        # Backtest
        metrics = algo.backtest(daily_series, test_days=test_days, **extra_kwargs)
        if metrics["mae"] >= 998:
            continue

        # Forecast
        result = algo.forecast(daily_series, horizon_days=horizon, **extra_kwargs)
        if result is None:
            continue

        result["metrics"] = metrics
        result.setdefault("data_points", n)

        # Apply bootstrapped intervals for Croston variants
        if algo.name in ("croston", "croston_sba"):
            result = croston_bootstrap_intervals(daily_series, result)

        candidates.append(result)

    # When adaptive_ma is available, remove redundant moving_avg (same family)
    has_adaptive = any(c["algorithm"] == "adaptive_ma" for c in candidates)
    if has_adaptive:
        candidates = [c for c in candidates if c["algorithm"] != "moving_avg"]

    if not candidates:
        return {
            "algorithm": "none",
            "forecasts": [],
            "params": {},
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": n,
            "confidence_base": D0,
            "demand_pattern": demand_pattern,
        }

    # Ensemble (>= 2 viable candidates, >= 28 days)
    if ensemble_algo and len(candidates) >= 2 and n >= 28:
        ens = ensemble_algo.forecast(
            daily_series, horizon_days=horizon,
            candidates=candidates, demand_pattern=demand_pattern,
        )
        if ens:
            candidates.append(ens)

    # Bug 1/2 (22/05/26): seleccionar por WAPE, no por MAPE.
    # El MAPE clasico explota con demanda intermitente (|err|/actual: si un
    # dia se vende 1 y se predice 8 -> 700%) y llegaba a 15.000%. Con MAPE
    # roto el selector elegia algoritmos que predicen mal (theta colapsando
    # a 0, HW con sabados en 0) porque su MAPE "se veia" comparable. WAPE
    # (Σ|err|/Σactual) es robusto: refleja el error real. Asi el backtest
    # honesto descarta los algoritmos que no manejan dias cerrados y elige
    # moving_avg/adaptive_ma que SI los manejan via dow_factors.
    def _err(c):
        m = c["metrics"]
        w = m.get("wape")
        base = w if w is not None else m.get("mape", 999)
        # F3.2 (Mario 29/05/26): penalizar SESGO persistente. Un modelo con
        # tracking_signal alto se equivoca siempre para el mismo lado (sub o
        # sobre-predice sistemáticamente) — eso vacía o llena la bodega aunque
        # su WAPE "se vea" bien. +5pp de WAPE por cada unidad de TS sobre 4.
        ts = abs(m.get("tracking_signal", 0) or 0)
        bias_penalty = max(0.0, ts - 4) * 5
        return base + bias_penalty

    # Pick best: for intermittent use MAE (WAPE/MAPE unreliable with zeros).
    if demand_pattern in ("intermittent", "lumpy"):
        # PREFERENCIA por Croston cuando demanda es intermitente
        # ──────────────────────────────────────────────────────
        # (13/05/26) Croston/Croston_SBA están diseñados específicamente
        # para demanda intermitente. Otros algoritmos (simple_avg,
        # moving_avg, theta) pueden dar MAE puntualmente menor en el
        # backtest porque "promedian a 0" en los días sin demanda — pero
        # operativamente son inútiles: predicen consumo todos los días
        # cuando la realidad es esporádica.
        #
        # Estrategia: si Croston o Croston-SBA son candidatos viables
        # (pasaron backtest, no devolvieron MAE sentinel de error),
        # preferirlos. Entre los dos Croston, el de menor MAE.
        croston_candidates = [
            c for c in candidates
            if c["algorithm"] in ("croston", "croston_sba")
            and c["metrics"]["mae"] < 998
        ]
        if croston_candidates:
            best = min(
                croston_candidates,
                key=lambda c: (c["metrics"]["mae"], _err(c)),
            )
        else:
            best = min(candidates, key=lambda c: (c["metrics"]["mae"], _err(c)))
    else:
        best = min(candidates, key=lambda c: (_err(c), c["metrics"]["mae"]))
    best["demand_pattern"] = demand_pattern

    logger.info(
        "Model selection: %d candidates. Winner: %s (WAPE=%.1f%%, MAE=%.3f, pattern=%s)",
        len(candidates), best["algorithm"],
        _err(best), best["metrics"]["mae"], demand_pattern,
    )

    return best
