# -*- coding: utf-8 -*-
"""
tests/test_backtest_forecast.py — el backtest fiel como comando del sistema.

La fidelidad se apoya en que el comando arma la serie con la MISMA funcion
que el entrenamiento nocturno (armar_serie_entrenamiento). Aca se fija:

  1. que esa funcion, corrida "como si fuera" un dia pasado D, solo mira
     ventas anteriores a D y termina en (D, 0): el cero de hoy que ve el
     entrenamiento real (pinneado en test_serie_termina_ayer.py);
  2. que el comando corre de punta a punta sobre un tenant chico, imprime
     el resumen por segmento y guarda el detalle por producto;
  3. que --comparar lee ese detalle y cuenta cuantos productos mejoran o
     empeoran (la disciplina: correr antes y despues de tocar el motor).
"""
import datetime
import io
import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast.models import DailySales
from forecast.services import armar_serie_entrenamiento

D = Decimal
HOY = datetime.date.today()


def _dia(i):
    return HOY - datetime.timedelta(days=i)


def _cargar_historia(tenant, warehouse, product, patron, dias=84):
    """Un patron semanal con el domingo cerrado (0): como Marbrava."""
    for i in range(1, dias + 1):
        d = _dia(i)
        q = 0 if d.weekday() == 6 else patron[d.weekday()]
        if q:
            DailySales.objects.create(tenant=tenant, product=product, warehouse=warehouse, date=d, qty_sold=D(str(q)))


@pytest.mark.django_db
class TestSerieDeUnDiaPasado:
    def test_solo_mira_antes_de_la_corrida_y_termina_en_el_cero_de_ese_dia(self, tenant, warehouse, product):
        _cargar_historia(tenant, warehouse, product, [8, 7, 9, 8, 10, 6, 0])
        corrida = _dia(14)
        serie = armar_serie_entrenamiento(tenant, product, warehouse.id, corrida, min_days=7)
        assert serie is not None
        fechas = [d for d, _ in serie["raw_series"]]
        assert max(fechas) == corrida, "la serie termina en el dia de la corrida"
        assert serie["raw_series"][-1][1] == 0, "el ultimo punto es el cero de 'hoy', como en produccion"
        # ninguna venta posterior a la corrida se filtra
        assert all(d <= corrida for d in fechas)
        assert len(fechas) == (corrida - min(fechas)).days + 1, "sin huecos: relleno de ceros"
        assert 6 in serie["closed_dows"], "detecta el domingo cerrado"

    def test_devuelve_none_si_no_alcanza_min_days(self, tenant, warehouse, product):
        _cargar_historia(tenant, warehouse, product, [8, 7, 9, 8, 10, 6, 0], dias=5)
        assert armar_serie_entrenamiento(tenant, product, warehouse.id, HOY, min_days=14) is None


@pytest.mark.django_db
class TestComandoBacktest:
    def test_corre_resume_y_guarda_el_detalle(self, tenant, store, warehouse, product, product_b, tmp_path):
        _cargar_historia(tenant, warehouse, product, [8, 7, 9, 8, 10, 6, 0])
        _cargar_historia(tenant, warehouse, product_b, [2, 0, 0, 3, 0, 0, 0])
        salida = tmp_path / "base.json"
        out = io.StringIO()
        call_command("backtest_forecast", tenant=tenant.id, semanas=2, salida=str(salida),
                     etiqueta="antes", stdout=out)
        texto = out.getvalue()
        assert "Backtest fiel [antes]" in texto
        assert "TOTAL" in texto and "nucleo" in texto
        assert "algoritmos elegidos" in texto
        detalle = json.loads(salida.read_text(encoding="utf-8"))
        assert detalle["meta"]["semanas"] == 2 and detalle["meta"]["horizonte"] == 7
        assert {p["nombre"] for p in detalle["productos"]} == {product.name, product_b.name}
        for p in detalle["productos"]:
            assert p["semanas"] == 2
            assert p["real"] > 0
            assert p["alg"] not in ("none", "")
            assert p["seg"] in ("nucleo", "cola")
        # el que vende 90% es nucleo; el intermitente chico, cola
        seg = {p["nombre"]: p["seg"] for p in detalle["productos"]}
        assert seg[product.name] == "nucleo" and seg[product_b.name] == "cola"

    def test_comparar_cuenta_los_que_mejoran_y_empeoran(self, tenant, store, warehouse, product, tmp_path):
        _cargar_historia(tenant, warehouse, product, [8, 7, 9, 8, 10, 6, 0])
        base = tmp_path / "base.json"
        call_command("backtest_forecast", tenant=tenant.id, semanas=1, salida=str(base), stdout=io.StringIO())
        # simulamos una corrida "anterior" peor: el doble de error absoluto
        d = json.loads(base.read_text(encoding="utf-8"))
        for p in d["productos"]:
            p["abs"] = p["abs"] * 2 + 1
        base.write_text(json.dumps(d), encoding="utf-8")
        out = io.StringIO()
        call_command("backtest_forecast", tenant=tenant.id, semanas=1, comparar=str(base), stdout=out)
        texto = out.getvalue()
        assert "base" in texto and "ahora" in texto and "delta" in texto
        assert "productos que mejoran: 1 | empeoran: 0" in texto

    def test_tenant_inexistente(self):
        from django.core.management.base import CommandError
        with pytest.raises(CommandError):
            call_command("backtest_forecast", tenant=999999, stdout=io.StringIO())
