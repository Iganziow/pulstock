# -*- coding: utf-8 -*-
"""
tests/test_regen_pasa_best_beta.py — lo que escribe la tabla es el regen.

Confirmado en produccion el 03/09/26 mirando las filas de Forecast de un
Croston: son la salida CRUDA del algoritmo re-ejecutado por
_regen_from_existing, que corre despues de save_forecasts y lo pisa. Nada de
lo que select_best_model deja en best["forecasts"] sobrevive.

Consecuencia: el regen pasaba best_alpha pero no best_beta, asi que el
arreglo de selection.py (1be7dd9) no cambiaba ni una fila en produccion: TSB
volvia a correr con beta=0.10 justo antes de guardar.
"""
import datetime
import types
from decimal import Decimal

import pytest

from forecast import services
from forecast.engine.algorithms.tsb import TSBForecast
from forecast.engine.registry import ALGORITHM_REGISTRY

D = Decimal


class EspiaTSB(TSBForecast):
    recibido = {}

    def forecast(self, daily_series, horizon_days=14, **kwargs):
        EspiaTSB.recibido = dict(kwargs)
        return super().forecast(daily_series, horizon_days=horizon_days, **kwargs)


@pytest.mark.django_db
def test_el_regen_le_pasa_la_beta_tuneada_al_algoritmo(
    tenant, product, warehouse, monkeypatch,
):
    monkeypatch.setitem(ALGORITHM_REGISTRY, "tsb", EspiaTSB)
    # save_forecasts necesita un ForecastModel real; aca solo importa QUE
    # recibe el algoritmo, no que se guarde.
    monkeypatch.setattr(services, "save_forecasts", lambda *a, **k: None)

    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=77)
    vals = [6, 0, 0, 8, 0, 0, 7] * 8 + [0] * 21
    serie = [(inicio + datetime.timedelta(days=i), D(str(v)), 1.0)
             for i, v in enumerate(vals)]

    fm = types.SimpleNamespace(
        algorithm="tsb",
        metrics={"best_alpha": 0.1, "best_beta": 0.02},
        model_params={},
    )
    services._regen_from_existing(
        tenant, product, warehouse.id, fm, hoy, 14, 21, serie, {},
        stockout_dates=None, raw_series=None,
    )

    assert EspiaTSB.recibido.get("best_alpha") == 0.1, "alpha dejo de llegar"
    assert EspiaTSB.recibido.get("best_beta") == 0.02, (
        "el regen re-ejecuta TSB sin la beta tuneada: la tabla queda con 0.10 "
        "aunque selection.py la pase"
    )
