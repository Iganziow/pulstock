"""
Base class for all forecast algorithms.
"""
from abc import ABC, abstractmethod


class ForecastAlgorithm(ABC):
    """
    Strategy interface for forecast algorithms.

    Subclasses must define:
        name: str             — algorithm key (e.g. "theta")
        min_data_points: int  — minimum days of data needed
        demand_patterns: list or None  — restrict to these patterns, None = all
        confidence_base: Decimal
    """
    name: str
    min_data_points: int
    demand_patterns: list | None = None  # None means eligible for all patterns

    @abstractmethod
    def forecast(self, daily_series, horizon_days=14, **kwargs) -> dict | None:
        """Run the algorithm and return forecast dict, or None if it fails."""
        ...

    @abstractmethod
    def backtest(self, daily_series, test_days=7, n_folds=3, **kwargs) -> dict:
        """Walk-forward cross-validation. Returns metrics dict."""
        ...

    def is_eligible(self, n_points: int, demand_pattern: str) -> bool:
        """Check if this algorithm should be considered given available data."""
        if n_points < self.min_data_points:
            return False
        if self.demand_patterns is not None and demand_pattern not in self.demand_patterns:
            return False
        return True
