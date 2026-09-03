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

# Cuando la propia Croston no vence al naive (MASE > 1.2), la ventana de backtest
# tuvo muy pocos eventos de demanda → la comparación es ruido estadístico.
# En ese caso exigimos mejora del 35% para no cambiar al algoritmo teóricamente
# incorrecto por un artefacto de la serie escasa.
MASE_OVERRIDE_MARGIN_SPARSE = 0.65
MASE_CROSTON_SPARSE_THRESHOLD = 1.2

# F21.2 (18/06/26): cantidad de folds del walk-forward backtest. Antes 3 (solo
# ~21 días testeados → el estimado oscilaba noche a noche por una sola semana
# rara). Subido a 8 (~56 días) para un estimado más estable. El loop de cada
# algoritmo auto-corta si no hay historia suficiente (productos cortos usan los
# folds que puedan), así que es seguro para todos. Pasado explícito a cada
# backtest desde acá = fuente única de verdad.
N_FOLDS = 8


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
        metrics = algo.backtest(daily_series, test_days=test_days, n_folds=N_FOLDS, **extra_kwargs)
        if metrics["mae"] >= 998:
            continue

        # Forecast — Sprint A (jul 2026): propagar el alpha tuneado por el
        # grid del backtest de Croston (antes se descartaba y el forecast
        # final usaba siempre el default). Los demás algoritmos lo ignoran.
        result = algo.forecast(
            daily_series, horizon_days=horizon,
            best_alpha=metrics.get("best_alpha"),
            # TSB tunea tambien beta (02/09/26): sin esto el grid elegia una
            # beta y el forecast final usaba siempre la de fabrica (0.10).
            best_beta=metrics.get("best_beta"),
            **extra_kwargs,
        )
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


def _wape_total(c):
    """WAPE de TOTALES del candidato (|Σpred−Σreal|/Σreal promedio por fold).
    Sprint A (jul 2026): es la métrica primaria en intermitente/lumpy — mide
    la TASA del período (lo que le importa a compras), no el acierto diario
    que premia sub-predecir. Sentinel → fondo del orden."""
    v = c["metrics"].get("wape_total")
    return v if (v is not None and v < 998) else 999.0


def _fc_total(c):
    """Suma del forecast del candidato sobre el horizonte. ~0 = colapsado."""
    return sum(float(f.get("qty_predicted", 0) or 0) for f in c.get("forecasts", []))


# Un forecast que suma <= esto sobre TODO el horizonte está colapsado a ~0.
COLLAPSE_FC_TOTAL = 0.5


def choose_best(candidates, demand_pattern):
    """Elige el mejor candidato según el patrón de demanda.

    Intermitente/lumpy → por MASE (métrica honesta: <1 vence al naive), con
    un FILTRO anti-colapso (descarta forecasts ~0, operativamente inútiles) y
    un GUARD operativo que conserva Croston salvo que un no-Croston le gane el
    MASE por >= MASE_OVERRIDE_MARGIN. Smooth → por _err (WAPE+sesgo).
    """
    if demand_pattern in ("intermittent", "lumpy"):
        # F (01/06/26) FILTRO ANTI-COLAPSO (capa 2): un candidato cuyo forecast
        # suma ~0 sobre el horizonte es operativamente inútil (no dice cuándo
        # reponer) — caso theta-en-0 sobre demanda esporádica, que MASE premia
        # falsamente (predecir 0 se "parece" al naive). Lo excluimos del pool,
        # SALVO que todos colapsen (producto realmente sin demanda). Esto es
        # quirúrgico: descarta solo el theta-colapso, conserva el theta que SÍ
        # produce un forecast real (donde legítimamente le gana a Croston).
        alive = [c for c in candidates if _fc_total(c) > COLLAPSE_FC_TOTAL]
        pool = alive if alive else candidates

        # F (01/06/26): seleccionar por MASE, no por MAE crudo. MAE crudo premia
        # modelos que "promedian a 0"; MASE escala por el naive → mide aporte real.
        # Sprint A (jul 2026): wape_total PRIMERO — el acierto día-a-día (MASE
        # incluido) hereda el sesgo a sub-predecir en lumpy; la tasa del período
        # es lo que decide compras. MASE queda de segundo criterio/desempate.
        # GUARD operativo: Croston (diseñado para intermitente) gana salvo que un
        # no-Croston le saque ventaja CLARA.
        def _key(c):
            return (_wape_total(c), _mase(c), _err(c), c["metrics"]["mae"])

        best_overall = min(pool, key=_key)
        # TSB va DENTRO de la familia protegida (02/09/26).
        #
        # El guard existe para conservar "el algoritmo disenado para demanda
        # intermitente" salvo que otro le gane por margen claro. TSB es
        # exactamente eso -- es el sucesor de Croston para intermitente con
        # obsolescencia (Teunter-Syntetos-Babai 2011) -- pero al agregarlo
        # quedo FUERA de esta lista por omision.
        #
        # El efecto era que TSB tenia que superar a Croston por 15%
        # (MASE_OVERRIDE_MARGIN) para ganarle, aunque fuese el mejor candidato
        # absoluto. Medido sobre las 79 series intermitentes reales de
        # produccion: TSB ganaba 5; con esta linea gana 25, y adaptive_ma
        # --el peor sesgo real del sistema, +198%-- baja de 6 a 2.
        # De los 20 cambios: 15 mejoran el wape_total y 5 lo empeoran.
        familia = [
            c for c in pool
            if c["algorithm"] in ("croston", "croston_sba", "tsb")
            and c["metrics"]["mae"] < 998
        ]
        if familia:
            best_croston = min(familia, key=_key)
            # Cuando Croston mismo no vence al naive (MASE > umbral), la ventana
            # de backtest tenía demasiado pocos eventos → ruido. Exigir margen
            # más estricto para no abandonar el algoritmo teóricamente correcto.
            effective_margin = (
                MASE_OVERRIDE_MARGIN
                if _mase(best_croston) <= MASE_CROSTON_SPARSE_THRESHOLD
                else MASE_OVERRIDE_MARGIN_SPARSE
            )
            # Sprint A: la comparación del override también por wape_total
            # (con fallback a MASE cuando ninguno tiene folds evaluables).
            ov, cr = _wape_total(best_overall), _wape_total(best_croston)
            if ov >= 998 and cr >= 998:
                ov, cr = _mase(best_overall), _mase(best_croston)
            if ov < cr * effective_margin:
                return best_overall
            return best_croston
        return best_overall
    return min(candidates, key=lambda c: (_err(c), c["metrics"]["mae"]))
