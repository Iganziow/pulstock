# -*- coding: utf-8 -*-
"""
tests/test_feriados_aprendidos.py — un feriado se pronostica con lo que el
negocio VIVIO la ultima vez; sin historia, con un estandar que no invente
efectos (feriados legales configurados, fechas comerciales neutras, sin rampas).

Medido en Marbrava el 19/10/26 con lo que publicaria el codigo, sobre la copia
de produccion (|multiplicador - real| x venta normal, solo los dias que alguna
regla toca):

    feriados 2026, aprende de 2025     hoy 1.455k  ->  B + grupo   979k  (-33%)
    25-oct-2025 a 3-ene-2026           hoy 2.578k  ->  B         2.060k  (-20%)
    (sin año previo: solo saca las rampas)

Lo de antes: el multiplicador aprendido se guardaba por fila FECHADA
(HolidayLearning), asi que un feriado futuro se pronosticaba siempre con la
configuracion global: los nacionales x0,75-0,8 (Marbrava cierra), Halloween
x1,4 (real 0,41), Navidad con 14 dias de rampa hasta x1,75 (real 0,9).
"""
import datetime
from decimal import Decimal

import pytest

from catalog.models import Product
from forecast import services
from forecast.engine import apply_holiday_adjustments
from forecast.models import DailySales, Holiday

D = Decimal
HOY = datetime.date.today()
DOMINGO = 6


def _habil(d):
    while d.weekday() == DOMINGO:
        d -= datetime.timedelta(days=1)
    return d


def _feriado(fecha, nombre="Feriado X", mult="0.80", pre_days=0, pre_mult="1.00",
             post_days=0, post_mult="0.85"):
    return Holiday.objects.create(
        tenant=None, name=nombre, date=fecha, demand_multiplier=D(mult),
        pre_days=pre_days, pre_multiplier=D(pre_mult),
        post_days=post_days, post_multiplier=D(post_mult),
    )


def _vender(tenant, warehouse, product, desde, hasta, qty=10, salvo=None):
    """Vende `qty` por dia de `desde` a `hasta`, domingos cerrados. `salvo` =
    {fecha: cantidad} (0 = cerrado)."""
    salvo = salvo or {}
    d = desde
    while d <= hasta:
        if d.weekday() != DOMINGO:
            q = salvo.get(d, qty)
            if q:
                DailySales.objects.create(tenant=tenant, product=product, warehouse=warehouse,
                                          date=d, qty_sold=D(str(q)))
        d += datetime.timedelta(days=1)


def _unos(fechas):
    return [{"date": d, "qty_predicted": D("10"), "lower_bound": D("7"),
             "upper_bound": D("13")} for d in fechas]


@pytest.mark.django_db
class TestPorNombre:
    def test_cerro_el_año_pasado_se_pronostica_cerrado(self, tenant, warehouse, product):
        pasado = _habil(HOY - datetime.timedelta(days=364))
        _feriado(pasado)
        _vender(tenant, warehouse, product, pasado - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo={pasado: 0})
        assert services.multiplicador_aprendido(tenant, "Feriado X", HOY) == D("0")

    def test_manda_la_ultima_vez(self, tenant, warehouse, product):
        """Dos años: el más reciente gana (el negocio cambia)."""
        viejo = _habil(HOY - datetime.timedelta(days=500))
        nuevo = _habil(HOY - datetime.timedelta(days=150))
        _feriado(viejo); _feriado(nuevo)
        _vender(tenant, warehouse, product, viejo - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo={viejo: 30, nuevo: 5})
        assert services.multiplicador_aprendido(tenant, "Feriado X", HOY) == D("0.5")

    def test_un_feriado_en_el_dia_que_el_local_no_abre_no_enseña_nada(
            self, tenant, warehouse, product):
        """El 12-oct-2025 cayó en domingo: que no haya vendido no dice nada."""
        pasado = HOY - datetime.timedelta(days=364)
        while pasado.weekday() != DOMINGO:
            pasado -= datetime.timedelta(days=1)
        _feriado(pasado)
        _vender(tenant, warehouse, product, pasado - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1))
        assert services.multiplicador_aprendido(tenant, "Feriado X", HOY) is None

    def test_unas_vacaciones_no_enseñan_que_el_feriado_cierra(self, tenant, warehouse, product):
        pasado = _habil(HOY - datetime.timedelta(days=364))
        _feriado(pasado)
        cerrado = {pasado + datetime.timedelta(days=k): 0 for k in range(-6, 7)}
        _vender(tenant, warehouse, product, pasado - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo=cerrado)
        assert services.multiplicador_aprendido(tenant, "Feriado X", HOY) is None

    def test_los_ingredientes_no_cuentan(self, tenant, warehouse, product):
        """La vara es venta x precio: un insumo a precio 0 que se consume en
        cantidades enormes no mueve el multiplicador."""
        pasado = _habil(HOY - datetime.timedelta(days=364))
        _feriado(pasado)
        leche = Product.objects.create(tenant=tenant, name="Leche", price=D("0"), is_active=True)
        desde, hasta = pasado - datetime.timedelta(days=40), HOY - datetime.timedelta(days=1)
        _vender(tenant, warehouse, product, desde, hasta, salvo={pasado: 15})
        _vender(tenant, warehouse, leche, desde, hasta, qty=5000, salvo={pasado: 90000})
        assert services.multiplicador_aprendido(tenant, "Feriado X", HOY) == D("1.5")


@pytest.mark.django_db
class TestGrupo:
    def test_un_feriado_legal_sin_historia_usa_lo_que_vivio_en_los_otros(
            self, tenant, warehouse, product):
        """San Pedro 2025 cayó en domingo: en 2026 no tenia historia propia. El
        local cerro sus otros feriados legales; se pronostica cerrado."""
        a = _habil(HOY - datetime.timedelta(days=200))
        b = _habil(HOY - datetime.timedelta(days=120))
        _feriado(a, nombre="Legal A"); _feriado(b, nombre="Legal B")
        futuro = _feriado(HOY + datetime.timedelta(days=3), nombre="Sin historia")
        _vender(tenant, warehouse, product, a - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo={a: 0, b: 0})
        elegidos = services._load_holidays_for_horizon(tenant, _unos([futuro.date]))
        assert [h.learned_multiplier for h in elegidos] == [D("0")]

    def test_una_fecha_comercial_no_tiene_grupo(self, tenant, warehouse, product):
        """Halloween o Black Friday (configurados arriba de 1) no heredan el
        cierre de los feriados legales."""
        a = _habil(HOY - datetime.timedelta(days=200))
        b = _habil(HOY - datetime.timedelta(days=120))
        _feriado(a, nombre="Legal A"); _feriado(b, nombre="Legal B")
        futuro = _feriado(HOY + datetime.timedelta(days=3), nombre="Comercial", mult="1.40")
        _vender(tenant, warehouse, product, a - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo={a: 0, b: 0})
        elegidos = services._load_holidays_for_horizon(tenant, _unos([futuro.date]))
        assert [h.learned_multiplier for h in elegidos] == [D("1")], "neutra, no el cierre de los legales"


@pytest.mark.django_db
class TestEstandarParaUnLocalNuevo:
    """Solo lo que sabemos (20/10/26): sin historia propia, los feriados
    legales usan lo configurado y las fechas comerciales quedan neutras."""

    def test_una_fecha_comercial_queda_neutra(self, tenant, warehouse, product):
        futuro = _feriado(HOY + datetime.timedelta(days=3), nombre="Halloween", mult="1.40")
        elegidos = services._load_holidays_for_horizon(tenant, _unos([futuro.date]))
        assert [h.learned_multiplier for h in elegidos] == [D("1")]

    def test_un_feriado_legal_conserva_lo_configurado(self, tenant, warehouse, product):
        futuro = _feriado(HOY + datetime.timedelta(days=3), nombre="Legal", mult="0.80")
        elegidos = services._load_holidays_for_horizon(tenant, _unos([futuro.date]))
        assert [h.learned_multiplier for h in elegidos] == [None]

    def test_una_vez_vivida_manda_lo_del_local(self, tenant, warehouse, product):
        pasado = _habil(HOY - datetime.timedelta(days=364))
        _feriado(pasado, nombre="Halloween", mult="1.40")
        futuro = _feriado(HOY + datetime.timedelta(days=3), nombre="Halloween", mult="1.40")
        _vender(tenant, warehouse, product, pasado - datetime.timedelta(days=40),
                HOY - datetime.timedelta(days=1), salvo={pasado: 4})
        elegidos = services._load_holidays_for_horizon(tenant, _unos([futuro.date]))
        assert [h.learned_multiplier for h in elegidos] == [D("0.4")]


@pytest.mark.django_db
class TestAplicacion:
    def test_un_cero_aprendido_baja_el_pronostico_a_cero(self):
        """Antes `if mult` trataba el 0 como 'sin ajuste'."""
        d = HOY + datetime.timedelta(days=2)
        fcs = _unos([d])
        apply_holiday_adjustments(fcs, [{"date": d, "demand_multiplier": 0.8,
                                         "learned_multiplier": 0, "pre_days": 0,
                                         "pre_multiplier": 1}])
        assert fcs[0]["qty_predicted"] == D("0")

    def test_produccion_no_lleva_rampas(self):
        """save_forecasts llama con rampas=False, para todo tipo de negocio."""
        d = HOY + datetime.timedelta(days=5)
        dias = [d + datetime.timedelta(days=k) for k in range(-3, 4)]
        h = {"date": d, "demand_multiplier": 1.5, "pre_days": 3, "pre_multiplier": 1.5,
             "post_days": 2, "post_multiplier": 0.8}
        fcs = _unos(dias)
        apply_holiday_adjustments(fcs, [h], business_type="retail", rampas=False)
        por = {f["date"]: f["qty_predicted"] for f in fcs}
        assert por[d] == D("15.000")
        assert all(por[x] == D("10") for x in dias if x != d), por

    def test_la_funcion_generica_conserva_las_rampas_si_se_piden(self):
        d = HOY + datetime.timedelta(days=5)
        h = {"date": d, "demand_multiplier": 1.5, "pre_days": 1, "pre_multiplier": 1.2}
        fcs = _unos([d - datetime.timedelta(days=1), d])
        apply_holiday_adjustments(fcs, [h])
        assert fcs[0]["qty_predicted"] == D("12.000")

    def test_un_feriado_en_dia_cerrado_no_se_come_su_masa(self):
        """El 1-nov-2026 cae domingo. El domingo lo pone en 0 _apply_closed_
        weekdays, que reparte su masa entre los dias abiertos; si el feriado
        (0 aprendido) lo multiplica antes, esa masa se pierde y cada dia
        abierto del horizonte baja 1-2%."""
        d = HOY + datetime.timedelta(days=1)
        while d.weekday() != DOMINGO:
            d += datetime.timedelta(days=1)
        fcs = _unos([d])
        apply_holiday_adjustments(fcs, [{"date": d, "demand_multiplier": 0.8,
                                         "learned_multiplier": 0, "pre_days": 0,
                                         "pre_multiplier": 1}],
                                  business_type="restaurant", closed_dows={DOMINGO})
        assert fcs[0]["qty_predicted"] == D("10")
