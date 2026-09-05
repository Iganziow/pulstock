# -*- coding: utf-8 -*-
"""
tests/test_texto_sugerencia.py — el texto de la sugerencia dice la verdad en
la unidad del producto.

Lo que Mario leia el 04/09/26 en la sugerencia #178:

    Chocolate Premium: "Te quedan 560 unidades y vendes unas 64 al dia"
        -> eran gramos, y se consumen 43 al dia (64 era la demanda de
           planificacion inflada para confianza baja).
    Muffin: "vendes alrededor de 1 unidades al dia"
        -> 0,14 al dia, redondeado a 1 por `max(1, round(x))`.
    Té: "Estas 30 unidades te alcanzan para aproximadamente 7 dias"
        -> a 2 por dia, 30 alcanzan 15. El "7" era el ciclo de compra.
"""
from decimal import Decimal

from forecast.services import _cantidad, _cobertura, _natural_reasoning, _ritmo_de_venta

D = Decimal


class TestCantidadEnSuUnidad:
    def test_gramos_y_kilos(self):
        assert _cantidad(453, "GR") == "453 g"
        assert _cantidad(1200, "GR") == "1,2 kg"
        assert _cantidad(2000, "G") == "2 kg"

    def test_mililitros_y_litros(self):
        assert _cantidad(450, "ML") == "450 ml"
        assert _cantidad(1800, "ML") == "1,8 L"

    def test_unidades_con_singular_y_miles(self):
        assert _cantidad(1, "UN") == "1 unidad"
        assert _cantidad(30, "UN") == "30 unidades"
        assert _cantidad(1234, "UN") == "1.234 unidades"
        assert _cantidad(2, "") == "2 unidades"

    def test_unidad_desconocida_se_muestra_tal_cual(self):
        assert _cantidad(3, "CAJA") == "3 caja"


class TestRitmoDeVenta:
    def test_alto_volumen_por_dia_en_su_unidad(self):
        assert _ritmo_de_venta(43.0, "GR") == "vendes cerca de 43 g al día"

    def test_baja_rotacion_por_semana_o_por_mes(self):
        assert _ritmo_de_venta(0.5, "UN") == "vendes cerca de 4 unidades a la semana"
        assert _ritmo_de_venta(0.14, "UN") == "vendes cerca de 4 unidades al mes"

    def test_sin_venta(self):
        assert _ritmo_de_venta(0.0, "UN") == "no se vendió en el último mes"


class TestCobertura:
    def test_dias_semanas_y_meses(self):
        assert _cobertura(D("6"), 2.0) == "unos 3 días"
        assert _cobertura(D("30"), 2.0) == "unas 2 semanas"
        assert _cobertura(D("200"), 2.0) == "más de dos meses"
        assert _cobertura(D("2"), 2.0) == "un día"

    def test_sin_venta_no_promete_nada(self):
        assert _cobertura(D("10"), 0.0) == ""


class TestElTextoCompleto:
    def test_chocolate_premium_habla_en_gramos_y_con_la_venta_real(self):
        t = _natural_reasoning(
            current_stock=D("560"), avg_daily=D("64"), days_out=8,
            suggested_qty=D("453"), target_days=7, buffer_pct=D("0"),
            unit="GR", venta_diaria=43.0,
        )
        assert "560 g" in t and "453 g" in t
        assert "43 g al día" in t
        assert "64" not in t, "mostro la demanda inflada en vez de la venta"
        assert "unidades" not in t

    def test_muffin_no_dice_que_vende_1_al_dia(self):
        t = _natural_reasoning(
            current_stock=D("0"), avg_daily=D("0.142"), days_out=0,
            suggested_qty=D("2"), target_days=7, buffer_pct=D("0"),
            unit="UN", venta_diaria=0.142,
        )
        assert "vendes cerca de 4 unidades al mes" in t
        assert "1 unidades" not in t
        assert "2 unidades te alcanza para unas 2 semanas" in t

    def test_te_dice_cuanto_alcanza_de_verdad(self):
        t = _natural_reasoning(
            current_stock=D("0"), avg_daily=D("3"), days_out=0,
            suggested_qty=D("30"), target_days=7, buffer_pct=D("0"),
            unit="UN", venta_diaria=2.0,
        )
        assert "30 unidades te alcanza para unas 2 semanas" in t
        assert "alcanzan para aproximadamente 7" not in t

    def test_sin_venta_diaria_usa_la_demanda_como_ultimo_recurso(self):
        t = _natural_reasoning(
            current_stock=D("0"), avg_daily=D("2"), days_out=0,
            suggested_qty=D("14"), target_days=7, buffer_pct=D("0"),
        )
        assert "vendes cerca de 2 unidades al día" in t

    def test_el_colchon_se_explica_solo_si_es_grande(self):
        base = dict(current_stock=D("5"), avg_daily=D("1"), days_out=5,
                    suggested_qty=D("10"), target_days=7, unit="UN", venta_diaria=1.0)
        assert "colchón" not in _natural_reasoning(buffer_pct=D("0.05"), **base)
        assert "colchón de seguridad de aproximadamente 25%" in _natural_reasoning(buffer_pct=D("0.25"), **base)

    def test_ningun_numero_con_punto_decimal(self):
        """El front redondeaba cualquier '\\d+.\\d+' a entero: '1.234' -> '1'.
        El texto usa coma decimal y punto de miles; no puede traer 1.5."""
        import re
        t = _natural_reasoning(
            current_stock=D("1234.5"), avg_daily=D("1.5"), days_out=10,
            suggested_qty=D("1500"), target_days=7, buffer_pct=D("0"),
            unit="ML", venta_diaria=1.5,
        )
        assert re.search(r"\d+\.\d+", t) is None or "1.234" in t
