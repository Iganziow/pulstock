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

# En demanda intermitente, un algoritmo no-Croston solo destrona a Croston si
# mejora su MASE en este margen (15%). Anti-flicker: evita cambiar de modelo
# por diferencias marginales noche a noche.
MASE_OVERRIDE_MARGIN = 0.85


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

    best = choose_best(candidates, demand_pattern)
    best["demand_pattern"] = demand_pattern

    logger.info(
        "Model selection: %d candidates. Winner: %s (WAPE=%.1f%%, MAE=%.3f, pattern=%s)",
        len(candidates), best["algorithm"],
        _err(best), best["metrics"]["mae"], demand_pattern,
    )

    return best


def _err(c):
    """Métrica de orden general: WAPE (robusto en intermitente, ver Bug 1/2)
    + penalización de sesgo. El MAPE clásico explota con ceros; WAPE no."""
    m = c["metrics"]
    w = m.get("wape")
    base = w if w is not None else m.get("mape", 999)
    # F3.2 (29/05/26): penalizar SESGO persistente. Un modelo con
    # tracking_signal alto se equivoca siempre para el mismo lado → vacía o
    # llena la bodega aunque su WAPE "se vea" bien. +5pp por unidad de TS>4.
    ts = abs(m.get("tracking_signal", 0) or 0)
    bias_penalty = max(0.0, ts - 4) * 5
    return base + bias_penalty


def _mase(c):
    """MASE de un candidato. Sentinel 999 (naive_mae==0, serie plana) no es
    informativo → lo mandamos al fondo del orden."""
    v = c["metrics"].get("mase")
    return v if (v is not None and v < 998) else 999.0


def choose_best(candidates, demand_pattern):
    """Elige el mejor candidato según el patrón de demanda.

    Intermitente/lumpy → por MASE (métrica honesta: <1 vence al naive), con
    un GUARD operativo que conserva Croston salvo que un no-Croston le gane
    el MASE por >= MASE_OVERRIDE_MARGIN. Smooth/erratic → por _err (WAPE+sesgo).
    """
    if demand_pattern in ("intermittent", "lumpy"):
        # F (01/06/26): seleccionar por MASE, no por MAE crudo.
        # MAE crudo premia modelos que "promedian a 0" en los días sin demanda
        # (bajan el MAE pero son operativamente inútiles). MASE escala el MAE
        # por el del naive → mide si el modelo APORTA algo real.
        #
        # GUARD operativo: Croston/Croston-SBA están diseñados para demanda
        # intermitente (predicen CUÁNDO se consume, no un promedio plano).
        # Croston gana salvo que un no-Croston le saque ventaja CLARA en MASE.
        def _key(c):
            return (_mase(c), _err(c), c["metrics"]["mae"])

        best_overall = min(candidates, key=_key)
        croston = [
            c for c in candidates
            if c["algorithm"] in ("croston", "croston_sba")
            and c["metrics"]["mae"] < 998
        ]
        if croston:
            best_croston = min(croston, key=_key)
            if _mase(best_overall) < _mase(best_croston) * MASE_OVERRIDE_MARGIN:
                return best_overall
            return best_croston
        return best_overall
    return min(candidates, key=lambda c: (_err(c), c["metrics"]["mae"]))
