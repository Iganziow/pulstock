import random

from ..utils import _q3


def croston_bootstrap_intervals(daily_series, base_forecast, n_boot=200, confidence=0.80):
    """
    Generate bootstrapped prediction intervals for Croston forecasts.
    Resamples non-zero demand sizes and intervals to build empirical distribution.

    Returns adjusted forecasts with bootstrapped lower/upper bounds.
    """
    non_zero = [(d, float(q)) for d, q, *_ in daily_series if float(q) > 0]
    if len(non_zero) < 5 or not base_forecast:
        return base_forecast

    sizes = [q for _, q in non_zero]
    intervals_days = []
    for i in range(1, len(non_zero)):
        intervals_days.append((non_zero[i][0] - non_zero[i - 1][0]).days)
    if not intervals_days:
        return base_forecast

    horizon = len(base_forecast["forecasts"])
    boot_rates = []

    random.seed(42)  # deterministic for reproducibility
    for _ in range(n_boot):
        # Resample sizes and intervals
        boot_sizes = [random.choice(sizes) for _ in range(len(sizes))]
        boot_intervals = [random.choice(intervals_days) for _ in range(len(intervals_days))]
        mean_size = sum(boot_sizes) / len(boot_sizes)
        mean_interval = sum(boot_intervals) / len(boot_intervals)
        if mean_interval > 0:
            boot_rates.append(mean_size / mean_interval)
        else:
            boot_rates.append(mean_size)

    boot_rates.sort()
    lo_idx = int(len(boot_rates) * (1 - confidence) / 2)
    hi_idx = int(len(boot_rates) * (1 + confidence) / 2)
    lo_idx = max(0, min(lo_idx, len(boot_rates) - 1))
    hi_idx = max(0, min(hi_idx, len(boot_rates) - 1))

    lower_rate = boot_rates[lo_idx]
    upper_rate = boot_rates[hi_idx]

    for fc in base_forecast["forecasts"]:
        fc["lower_bound"] = _q3(max(0, lower_rate))
        fc["upper_bound"] = _q3(upper_rate)

    base_forecast["params"]["bootstrap_samples"] = n_boot
    return base_forecast
