"""
Algorithm registry — maps names to ForecastAlgorithm subclasses.
"""
from __future__ import annotations
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ForecastAlgorithm

ALGORITHM_REGISTRY: dict[str, type[ForecastAlgorithm]] = {}


def _desactivados() -> set[str]:
    """Algoritmos apagados por variable de entorno.

    `FORECAST_ALGOS_OFF=croston,ets` y esos algoritmos dejan de competir en
    la seleccion. El resto sigue igual y los productos que los usaban eligen
    su mejor alternativa en el siguiente entrenamiento nocturno.

    Existe por el traspaso: despues de la entrega no hay desarrollador. Si un
    algoritmo empieza a sugerir disparates un martes cualquiera, esto se
    apaga editando el `.env` y reiniciando el servicio -- sin tocar codigo,
    sin desplegar, sin esperar a nadie. Y se revierte igual de facil.

    Documentado en docs/ops/. Vacio por defecto: no apaga nada.
    """
    crudo = os.environ.get("FORECAST_ALGOS_OFF", "")
    return {x.strip() for x in crudo.split(",") if x.strip()}


def register(cls):
    """Class decorator: register an algorithm by its `name` attribute."""
    if cls.name in _desactivados():
        return cls  # queda definido, pero fuera de la competencia
    ALGORITHM_REGISTRY[cls.name] = cls
    return cls
