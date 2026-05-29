from decimal import Decimal

from ..base import ForecastAlgorithm
from ..registry import register
from ..utils import (
    _q3, _compute_metrics, _average_metrics, D0,
    generate_daily_forecasts, compute_prediction_intervals,
    apply_empirical_intervals, predict_dow_base,
)


# F8: patrones de demanda donde conviene la estacionalidad ADITIVA (la
# multiplicativa aplana el finde cuando el promedio diario es bajo).
_ADDITIVE_PATTERNS = ("intermittent", "lumpy")


def _weighted_moving_average(daily_series, window=21):
    """
    Weighted moving average with exponential decay + day-of-week factors.
    Accepts (date, qty) or (date, qty, weight) tuples.
    """
    if not daily_series:
        return {"avg_daily": D0, "weights": [], "day_of_week_factors": {}}

    recent = daily_series[-window:]
    n = len(recent)
    decay = 0.9
    raw_weights = [decay ** (n - 1 - i) for i in range(n)]
    weight_sum = sum(raw_weights)

    weighted_sum = Decimal("0")
    weight_details = []
    for i, item in enumerate(recent):
        d, qty = item[0], item[1]
        data_weight = item[2] if len(item) >= 3 else 1.0
        w = Decimal(str(raw_weights[i] / weight_sum * data_weight))
        weighted_sum += Decimal(str(qty)) * w
        weight_details.append((d, float(w), float(qty)))

    # Re-normalize
    total_w = sum(wt for _, wt, _ in weight_details)
    if total_w > 0 and abs(total_w - 1.0) > 0.01:
        weighted_sum = Decimal("0")
        for i, (d, w, q) in enumerate(weight_details):
            norm_w = w / total_w
            weighted_sum += Decimal(str(q)) * Decimal(str(norm_w))
            weight_details[i] = (d, norm_w, q)

    avg_daily = _q3(weighted_sum)

    # Day-of-week factors
    dow_totals = {}
    for item in daily_series:
        d, qty = item[0], float(item[1])
        dow_totals.setdefault(d.weekday(), []).append(qty)

    # Detectar "días cerrados": si el dataset cubre un rango de fechas
    # con al menos 4 ocurrencias de un DOW (~1 mes) pero NO hay ningún
    # registro de venta de ese DOW, asumimos que el local no abre ese
    # día y forzamos factor=0. Mario reportó: "no se trabajan los
    # domingos" pero el modelo predecía 3.0 unidades para domingos.
    import datetime as _dt
    dates = [item[0] for item in daily_series]
    if dates:
        min_d, max_d = min(dates), max(dates)
        total_days_in_range = (max_d - min_d).days + 1
        dow_occurrences_in_range = {dow: 0 for dow in range(7)}
        for i in range(total_days_in_range):
            d = min_d + _dt.timedelta(days=i)
            dow_occurrences_in_range[d.weekday()] += 1
    else:
        dow_occurrences_in_range = {dow: 0 for dow in range(7)}

    overall_avg = float(avg_daily) if avg_daily > 0 else 1.0
    # Promedio global REAL (no el ponderado) para el offset aditivo: es la
    # referencia natural de "cuánto más/menos que un día típico" se vende
    # cada DOW. Usamos la media simple de los días con venta.
    all_day_vals = [v for vals in dow_totals.values() for v in vals]
    plain_avg = (sum(all_day_vals) / len(all_day_vals)) if all_day_vals else overall_avg

    dow_factors = {}
    dow_additive = {}   # F8: offset aditivo por DOW (qty extra/menos vs día típico)
    closed_dows = set()
    for dow in range(7):
        values = dow_totals.get(dow, [])
        if values:
            dow_avg = sum(values) / len(values)
            dow_factors[dow] = round(dow_avg / overall_avg, 3) if overall_avg > 0 else 1.0
            dow_additive[dow] = round(dow_avg - plain_avg, 3)
        elif dow_occurrences_in_range.get(dow, 0) >= 4:
            # Cerrado los días con al menos 4 oportunidades sin ventas
            dow_factors[dow] = 0.0
            closed_dows.add(dow)
        else:
            # Poca data del DOW (1-3 ocurrencias) — neutral
            dow_factors[dow] = 1.0
            dow_additive[dow] = 0.0

    return {
        "avg_daily": avg_daily,
        "weights": weight_details,
        "day_of_week_factors": dow_factors,
        # F8: para demanda intermitente, estos offsets preservan la señal
        # absoluta del finde que el multiplicativo aplana cuando avg≈0.
        "day_of_week_additive": dow_additive,
        "closed_dows": closed_dows,
        "plain_avg": plain_avg,
    }


def _predict_ma(result, dow, use_additive):
    """Predicción de un día con el resultado de _weighted_moving_average,
    en el MISMO modo (aditivo/multiplicativo) que usa el forecast — así el
    WAPE del backtest refleja lo que realmente se va a predecir."""
    return predict_dow_base(
        float(result["avg_daily"]), dow,
        result["day_of_week_factors"],
        dow_additive=result.get("day_of_week_additive") if use_additive else None,
        closed_dows=result.get("closed_dows"),
    )


def _backtest_moving_average(daily_series, test_days=7, window=21, n_folds=3, use_additive=False):
    """Walk-forward cross-validation with n_folds folds."""
    min_train = max(test_days + 7, window + 7)
    if len(daily_series) < min_train + test_days:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}

    fold_metrics = []
    total = len(daily_series)
    for fold in range(n_folds):
        test_end = total - fold * test_days
        test_start = test_end - test_days
        if test_start < min_train:
            break
        train = daily_series[:test_start]
        test = daily_series[test_start:test_end]
        result = _weighted_moving_average(train, window=window)
        actuals = [float(item[1]) for item in test]
        predictions = [_predict_ma(result, item[0].weekday(), use_additive) for item in test]
        fold_metrics.append(_compute_metrics(actuals, predictions))

    if not fold_metrics:
        return {"mae": 999, "mape": 999, "rmse": 999, "bias": 0}
    return _average_metrics(fold_metrics)


@register
class WeightedMovingAverage(ForecastAlgorithm):
    name = "moving_avg"
    min_data_points = 14
    demand_patterns = None  # all

    def forecast(self, daily_series, horizon_days=14, window=21,
                 month_factors=None, test_days=7, **kwargs):
        # F8: estacionalidad aditiva para demanda intermitente/lumpy.
        use_additive = kwargs.get("demand_pattern") in _ADDITIVE_PATTERNS
        ma_result = _weighted_moving_average(daily_series, window=window)
        today = daily_series[-1][0]
        forecasts = generate_daily_forecasts(
            ma_result["avg_daily"], ma_result["day_of_week_factors"],
            today, horizon_days, month_factors=month_factors,
            dow_additive=ma_result.get("day_of_week_additive") if use_additive else None,
            closed_dows=ma_result.get("closed_dows"),
        )

        # Apply empirical intervals if we have enough backtest data
        if len(daily_series) > test_days + 7:
            train = daily_series[:-test_days]
            test = daily_series[-test_days:]
            ma_train = _weighted_moving_average(train, window=window)
            actuals = [float(item[1]) for item in test]
            predictions = [_predict_ma(ma_train, item[0].weekday(), use_additive) for item in test]
            intervals = compute_prediction_intervals(actuals, predictions)
            if intervals:
                apply_empirical_intervals(forecasts, intervals)

        n = len(daily_series)
        return {
            "algorithm": "moving_avg",
            "forecasts": forecasts,
            "params": {
                "avg_daily": str(ma_result["avg_daily"]),
                "dow_factors": {str(k): v for k, v in ma_result["day_of_week_factors"].items()},
                "dow_additive": {str(k): v for k, v in ma_result.get("day_of_week_additive", {}).items()},
                "dow_mode": "additive" if use_additive else "multiplicative",
                "window": window,
                "month_factors": month_factors,
            },
            "metrics": {"mae": 0, "mape": 0, "rmse": 0, "bias": 0},
            "data_points": n,
            "confidence_base": Decimal("70.00"),
        }

    def backtest(self, daily_series, test_days=7, n_folds=3, window=21, **kwargs):
        use_additive = kwargs.get("demand_pattern") in _ADDITIVE_PATTERNS
        return _backtest_moving_average(daily_series, test_days=test_days,
                                        window=window, n_folds=n_folds,
                                        use_additive=use_additive)
