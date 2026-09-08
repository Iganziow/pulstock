# -*- coding: utf-8 -*-
"""
tests/test_centinela_metricas.py — un error real gigante no puede confundirse
con "no evaluable".

Auditoria del 08/09/26, reproducida tal cual: dos periodos, uno perfecto (0%)
y uno catastrofico (1.000%), y el promedio devolvia 0%. La causa: los folds
con ventana degenerada (sin ventas, o serie plana) devuelven 999 como
centinela, y el promedio descartaba TODO fold con la metrica >= 900. Un error
REAL del 900% o mas caia en la misma bolsa y desaparecia.

Por que importa aunque el sintoma no se vea hoy: esa metrica es la que elige
el algoritmo cada noche. Un modelo que la mitad de las semanas se equivoca por
diez veces se veia perfecto y podia ganar. Medido el 08/09/26 sobre 1.860
folds de todos los candidatos de Marbrava, ninguno caia en el caso (todos los
descartes eran centinelas legitimos), asi que en este cliente no estaba
distorsionando nada. Se arregla porque es silencioso.

Ahora cada fold declara en `no_evaluables` que metricas no significan nada, y
el promedio se decide por esa marca y no por la magnitud.
"""
from forecast.engine.utils import _average_metrics, _compute_metrics


def _fold(reales, preds):
    return _compute_metrics([float(x) for x in reales], [float(x) for x in preds])


class TestElFoldSeMarcaSolo:
    def test_fold_normal_no_marca_nada(self):
        f = _fold([10, 12, 9, 11, 13, 8, 10], [11] * 7)
        assert f["no_evaluables"] == []
        assert 0 < f["wape"] < 50

    def test_serie_plana_solo_deja_sin_evaluar_el_mase(self):
        """Si la realidad no varia, el naive no comete error y el MASE no
        significa nada; el WAPE si (F21.1)."""
        f = _fold([10] * 7, [12] * 7)
        assert f["no_evaluables"] == ["mase"]
        assert f["wape"] == 20.0

    def test_fold_catastrofico_es_evaluable(self):
        """1.000% de error es un error, no un centinela."""
        f = _fold([1] * 7, [11] * 7)
        assert f["wape"] == 1000.0
        assert "wape" not in f["no_evaluables"]
        assert "wape_total" not in f["no_evaluables"]

    def test_semana_sin_ventas_si_es_centinela(self):
        f = _fold([0] * 7, [3] * 7)
        assert f["wape"] == 999
        assert set(f["no_evaluables"]) >= {"wape", "wape_total", "mape"}

    def test_semana_sin_ventas_y_sin_prediccion_es_acierto(self):
        """Cerrado o demanda detenida: predijo 0 y se vendio 0. No es centinela."""
        f = _fold([0] * 7, [0] * 7)
        assert f["wape"] == 0 and f["wape_total"] == 0
        assert "wape" not in f["no_evaluables"]


class TestElPromedio:
    def test_el_caso_de_la_auditoria(self):
        """Dos periodos, 0% y 1.000%: el promedio es 500%, no 0%."""
        prom = _average_metrics([_fold([10] * 7, [10] * 7), _fold([1] * 7, [11] * 7)])
        assert prom["wape"] == 500.0, (
            "el fold de 1.000%% se esta descartando como si no fuera evaluable: %s" % prom["wape"])
        assert prom["wape_total"] == 500.0

    def test_el_centinela_legitimo_se_sigue_ignorando(self):
        """Lo que el filtro por magnitud hacia bien: una semana sin ventas no
        puede inflar la metrica (F21.1, 16/06/26)."""
        prom = _average_metrics([_fold([10] * 7, [10] * 7), _fold([0] * 7, [3] * 7)])
        assert prom["wape"] == 0.0

    def test_todos_centinela_queda_en_999(self):
        prom = _average_metrics([_fold([0] * 7, [3] * 7)] * 3)
        assert prom["wape"] == 999 and prom["wape_total"] == 999

    def test_tope_para_que_no_se_confunda_con_el_centinela(self):
        """Un error de 50.000% se acota a 995: sigue siendo el peor de todos,
        pero no entra en la banda >= 998 que el resto del motor lee como
        'no evaluable'."""
        prom = _average_metrics([_fold([1] * 7, [500] * 7)])
        assert prom["wape"] == 995.0
        assert prom["wape"] < 998

    def test_metricas_viejas_sin_marca_siguen_funcionando(self):
        """Modelos entrenados antes del 08/09/26: sus folds no traen la lista,
        y para ellos se conserva la regla de magnitud."""
        viejo_bueno = {"mae": 1, "rmse": 1, "bias": 0, "wape": 10.0}
        viejo_centinela = {"mae": 1, "rmse": 1, "bias": 0, "wape": 999}
        assert _average_metrics([viejo_bueno, viejo_centinela])["wape"] == 10.0

    def test_sin_folds(self):
        assert _average_metrics([])["wape"] == 999


class TestElEfectoEnLaSeleccion:
    def test_un_modelo_que_falla_la_mitad_del_tiempo_ya_no_le_gana_a_uno_estable(self):
        """El riesgo concreto de la auditoria: favorecer un modelo malo."""
        from forecast.engine.selection import choose_best

        inestable = {
            "algorithm": "inestable", "forecasts": [{"qty_predicted": 5} for _ in range(7)],
            "metrics": _average_metrics([_fold([10] * 7, [10] * 7), _fold([1] * 7, [11] * 7)]),
            "data_points": 60,
        }
        estable = {
            "algorithm": "estable", "forecasts": [{"qty_predicted": 5} for _ in range(7)],
            "metrics": _average_metrics([_fold([10] * 7, [12] * 7), _fold([10] * 7, [12] * 7)]),
            "data_points": 60,
        }
        assert choose_best([inestable, estable], "smooth")["algorithm"] == "estable"
        assert choose_best([inestable, estable], "intermittent")["algorithm"] == "estable"
