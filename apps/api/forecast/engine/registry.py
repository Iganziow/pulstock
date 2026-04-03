"""
Algorithm registry — maps names to ForecastAlgorithm subclasses.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ForecastAlgorithm

ALGORITHM_REGISTRY: dict[str, type[ForecastAlgorithm]] = {}


def register(cls):
    """Class decorator: register an algorithm by its `name` attribute."""
    ALGORITHM_REGISTRY[cls.name] = cls
    return cls
