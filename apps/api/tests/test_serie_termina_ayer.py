# -*- coding: utf-8 -*-
"""
tests/test_serie_termina_ayer.py — el cero de "hoy" SE QUEDA, y este test
explica por que.

El hecho: `aggregate_daily_sales` escribe las ventas de AYER y el pipeline
corre de madrugada, pero el relleno de ceros de train_product_model llega
"hasta hoy". Todos los productos, todas las noches, entran al modelo con un
ultimo dia en cero que todavia no ocurrio. Como dato, es falso.

Lo que paso al intentar arreglarlo (04/09/26): se cambio span_end a ayer
(una linea) y se midio con backtest FIEL a produccion -- 99 productos
reales, 4 semanas hacia adelante, replicando clean_series, el patron con
domingos filtrados, window=7 y la historia importada:

    quitar el cero:  WAPE total 132% -> 154%   sesgo +2% -> +25%
                     cola 158% -> 179%          intermitentes +37% -> +68%
                     32 productos mejoran, 56 empeoran

El cero actua hoy como FRENO sobre modelos que sobre-predicen la demanda
intermitente (Croston/TSB/adaptive_ma sobre 75 de 99 productos). Quitarlo
sin corregir antes esa sobreprediccion destapa el sesgo y empeora lo que
Mario ve. Este test fija la conducta actual para que nadie la "arregle" por
intuicion, como casi hago yo.

Cuando exista una correccion de sesgo real (la actual es letra muerta, ver
FORECAST_REVIEW.md 3.2 y 3.5), hay que volver a medir con el mismo backtest
y recien entonces mover span_end a ayer. El cambio es una linea; la
evidencia para hacerlo es lo que falta.
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast import services
from forecast.models import DailySales

D = Decimal


def _historia(tenant, product, warehouse, dias=60):
    hoy = datetime.date.today()
    patron = [7, 6, 8, 7, 9, 6, 7]
    for i in range(1, dias + 1):
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=hoy - datetime.timedelta(days=i),
            qty_sold=D(str(patron[i % 7])),
        )


@pytest.mark.django_db
def test_la_serie_termina_hoy_con_cero_y_es_a_proposito(
    tenant, store, warehouse, product, monkeypatch,
):
    _historia(tenant, product, warehouse)
    capturadas = []
    original = services.select_best_model

    def espia(*args, **kwargs):
        serie = args[0] if args else kwargs["daily_series"]
        capturadas.append(list(serie))
        return original(*args, **kwargs)

    monkeypatch.setattr(services, "select_best_model", espia)
    call_command("train_forecast_models", tenant=tenant.id, horizon=14, verbosity=0)

    assert capturadas, "select_best_model no se llamo: el setup no entreno"
    hoy = datetime.date.today()
    ultimo = capturadas[0][-1]
    assert ultimo[0] == hoy and float(ultimo[1]) == 0.0, (
        "la serie ya no termina en (hoy, 0). Si esto es intencional, tiene "
        "que venir con un backtest fiel que muestre que la cola NO empeora: "
        "el 04/09/26 quitar el cero subio el sesgo intermitente de +37%% a "
        "+68%%. Ultimo punto: %s" % (ultimo,)
    )
