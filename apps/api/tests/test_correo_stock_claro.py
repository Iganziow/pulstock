# -*- coding: utf-8 -*-
"""
tests/test_correo_stock_claro.py — el correo de stock bajo se entiende solo.

Hasta el 29/10/26 cada fila decia "Sin stock / sin stock" o "Predicción: se
acaba en ~1 día / 1 d": no decia cuanto quedaba, cuanto se usa ni cuanto pedir.
Y avisaba como "critico" al Te, que se vende todos los dias sin stock cargado
(21 en dos semanas, 0 dias con stock en 60): nada que reponer, todos los dias.
"""
import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.core.management import call_command

from billing.email_renderers import _cantidad, _explicar_alerta, render_low_stock_v2
from catalog.models import Product
from forecast.models import DailySales
from inventory.models import StockItem

D = Decimal


def _alerta(nombre, on_hand, uso, razon, dias=None, unidad="UN", umbral=None):
    return {"product_name": nombre, "sku": "S", "warehouse": "Bodega Principal", "unit": unidad,
            "on_hand": on_hand, "avg_daily": uso, "days_left": dias, "reason": razon,
            "threshold": umbral, "reason_text": "viejo"}


class TestCantidades:
    def test_mililitros_pasan_a_litros(self):
        assert _cantidad(2618, "ML") == "2,6 L"
        assert _cantidad(700, "ML") == "700 ml"

    def test_gramos_pasan_a_kilos(self):
        assert _cantidad(1500, "GR") == "1,5 kg"

    def test_unidades_y_miles_con_punto(self):
        assert _cantidad(3, "UN") == "3 unidades"
        assert _cantidad(1, "UN") == "1 unidad"
        assert _cantidad(1250, "UN") == "1.250 unidades"


class TestCadaFilaSeExplicaSola:
    def test_la_leche_dice_cuanto_queda_cuanto_se_usa_y_cuanto_pedir(self):
        estado, situacion, porque, pedir = _explicar_alerta(
            _alerta("Leche entera", 2618, 700, "forecast", dias=1, unidad="ML"))
        assert estado == "Se acaba mañana"
        assert situacion == "Quedan 2,6 L · se usan ~700 ml por día"
        assert "se acaba mañana" in porque
        assert pedir == "Para cubrir 7 días: pedir ~2,3 L"          # 7 x 700 - 2.618

    def test_una_sola_unidad_va_en_singular(self):
        _e, situacion, _p, _q = _explicar_alerta(_alerta("Super 8", 1, 0, "stockout", dias=None))
        assert situacion.startswith("Queda 1 unidad"), situacion

    def test_sin_stock_dice_cuanto_se_uso(self):
        estado, situacion, porque, pedir = _explicar_alerta(
            _alerta("Torta", 0, 0.5, "stockout", dias=0))
        assert estado == "Sin stock"
        assert situacion.startswith("No queda nada")
        assert "7 unidades" in porque                                     # 0,5 x 14
        assert pedir == "Para cubrir 7 días: pedir ~4 unidades"         # unidades enteras

    def test_con_pronostico_se_pide_lo_que_viene_no_el_promedio(self):
        """La leche: el promedio da 700/dia, pero el pronostico de los proximos
        7 dias son 6.000 (dias fuertes por delante)."""
        a = _alerta("Leche entera", 2618, 700, "forecast", dias=2, unidad="ML")
        a["proximos_dias"] = 6000
        estado, _s, porque, pedir = _explicar_alerta(a)
        assert estado == "Alcanza ~2 días"
        assert "se acaba en ~2 días" in porque
        assert pedir == "Para cubrir 7 días: pedir ~3,4 L"            # 6.000 - 2.618

    def test_un_pronostico_con_ceros_no_baja_el_pedido_del_promedio(self):
        """La leche del 29-oct: el pronostico de 7 dias traia dos dias en 0 y
        sumaba 3,8 L; con 3,4 L en stock sugeria pedir 432 ml."""
        a = _alerta("Leche entera", 3400, 643, "forecast", dias=2, unidad="ML")
        a["proximos_dias"] = 3832
        _e, _s, _p, pedir = _explicar_alerta(a)
        assert pedir == "Para cubrir 7 días: pedir ~1,1 L"            # 7 x 643 - 3.400

    def test_bajo_el_minimo_manual_se_pide_al_menos_hasta_el_minimo(self):
        _e, _s, _p, pedir = _explicar_alerta(_alerta("Queso", 6, 0.1, "manual", dias=60, umbral=10))
        assert pedir == "Para llegar a tu mínimo: pedir ~4 unidades"   # hasta el minimo de 10

    def test_bajo_el_minimo_manual_dice_cual_es(self):
        _e, _s, porque, _p = _explicar_alerta(_alerta("Queso", 6, 1, "manual", dias=6, umbral=10))
        assert "10 unidades" in porque


@pytest.mark.django_db
class TestElCorreo:
    def test_sin_emojis_y_asunto_con_resumen(self, tenant):
        asunto, plano, html = render_low_stock_v2(
            tenant, [_alerta("Leche entera", 2618, 700, "forecast", dias=1, unidad="ML"),
                     _alerta("Torta", 0, 0.5, "stockout", dias=0)], [])
        assert asunto.startswith("Stock: 1 sin stock, 1 se acaba pronto")
        for e in ("🚨", "⚠", "💡"):
            assert e not in asunto and e not in html and e not in plano
        assert "Quedan 2,6 L" in html and "pedir ~2,3 L" in html

    def test_los_indicadores_no_van_en_celdas_anidadas(self, tenant):
        """kpi_tile ya trae su <td>: envuelto en otro, el navegador deja columnas
        vacias y la fila sale desalineada (visto en el correo ABC, 8-nov)."""
        _a, _p, html = render_low_stock_v2(tenant, [_alerta("Torta", 0, 0.5, "stockout", dias=0)], [])
        inicio = html.index("<!-- KPIs")
        fila = html[inicio:html.index("</tr>", inicio)]
        assert fila.count("<td") == 3, "tres indicadores, tres celdas"

    def test_el_pie_es_corto_solo_en_los_reportes(self, tenant):
        _a, _p, html = render_low_stock_v2(tenant, [_alerta("Torta", 0, 0.5, "stockout", dias=0)], [])
        assert "Alguna duda" not in html and "Pulstock SpA" not in html
        # Un correo de cobro conserva soporte y razon social.
        from django.template.loader import render_to_string
        from billing.email_renderers import _base_ctx
        base = render_to_string("emails/base.html", _base_ctx(subject_line="x", eyebrow="x", hero_title="x", subtitle="x"))
        assert "Alguna duda" in base and "Pulstock SpA" in base

    def test_lo_que_se_vende_sin_stock_cargado_no_se_menciona(self, tenant):
        _a, plano, html = render_low_stock_v2(tenant, [_alerta("Torta", 0, 0.5, "stockout", dias=0)], [],
                                              sin_control=["Té", "Extra Bebida fría"])
        assert "Té" not in html and "Té" not in plano


def _dias_atras(n):
    return datetime.date.today() - datetime.timedelta(days=n)


@pytest.mark.django_db
class TestEnElComando:
    @pytest.fixture
    def con_correo(self, owner):
        owner.email = "mario@marbrava.cl"; owner.save(update_fields=["email"])
        return owner

    def test_el_te_sin_stock_cargado_no_es_critico(self, tenant, store, warehouse, con_correo, category):
        te = Product.objects.create(tenant=tenant, name="Té", sku="TE", category=category, price=D("1500"))
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=te, on_hand=D("0"), avg_cost=D("100"))
        torta = Product.objects.create(tenant=tenant, name="Torta", sku="TO", category=category, price=D("2500"))
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=torta, on_hand=D("0"), avg_cost=D("100"))
        for i in range(1, 11):    # el Te vende todos los dias y nunca cierra con stock
            DailySales.objects.create(tenant=tenant, product=te, warehouse=warehouse, date=_dias_atras(i),
                                      qty_sold=D("2"), closing_stock=D("0"))
            DailySales.objects.create(tenant=tenant, product=torta, warehouse=warehouse, date=_dias_atras(i),
                                      qty_sold=D("1"), closing_stock=D("3") if i > 1 else D("0"))
        call_command("send_low_stock_alerts", "--tenant", str(tenant.id), verbosity=0)
        assert mail.outbox
        plano = mail.outbox[0].body
        assert "Torta" in plano, "la torta se acabo de verdad: va en reponer"
        assert "Té" not in plano, "el Te se vende sin stock cargado: no hay nada que reponer"

    def test_el_insumo_usa_lo_que_se_consume_por_receta(self, tenant, store, warehouse, con_correo, category):
        """La leche no se vende directo: su uso sale de DailySales (recetas)."""
        leche = Product.objects.create(tenant=tenant, name="Leche entera", sku="LE", category=category,
                                       price=D("0"), unit="ML")
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=leche, on_hand=D("0"), avg_cost=D("1"))
        for i in range(1, 15):
            DailySales.objects.create(tenant=tenant, product=leche, warehouse=warehouse, date=_dias_atras(i),
                                      qty_sold=D("700"), closing_stock=D("500") if i > 2 else D("0"))
        call_command("send_low_stock_alerts", "--tenant", str(tenant.id), verbosity=0)
        assert mail.outbox, "la leche sin stock y con consumo tiene que avisar"
        html = str(mail.outbox[0].alternatives)
        assert "Leche entera" in html and "se usan ~700 ml por día" in html

    def test_el_registro_del_envio_no_marca_error(self, tenant, store, warehouse, con_correo, category, capsys):
        p = Product.objects.create(tenant=tenant, name="Galleton", sku="GA", category=category, price=D("900"))
        StockItem.objects.create(tenant=tenant, warehouse=warehouse, product=p, on_hand=D("0"), avg_cost=D("100"))
        for i in range(1, 6):
            DailySales.objects.create(tenant=tenant, product=p, warehouse=warehouse, date=_dias_atras(i),
                                      qty_sold=D("1"), closing_stock=D("1") if i > 1 else D("0"))
        call_command("send_low_stock_alerts", "--tenant", str(tenant.id))
        salida = capsys.readouterr()
        assert "[sent]" in salida.out
        assert "[error]" not in salida.err, salida.err
