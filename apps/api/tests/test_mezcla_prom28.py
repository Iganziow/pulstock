# -*- coding: utf-8 -*-
"""
tests/test_mezcla_prom28.py — lo publicado se mezcla con el nivel de los
ultimos 28 dias abiertos.

    prediccion(dia) = 0,25 x modelo(dia) + 0,75 x nivel

Medido en produccion (21-sep-2026): un promedio de 28 dias le gana al motor en
los seis productos del nucleo, 38% contra 48%, porque el modelo acierta el
nivel y erra la forma. Ver forecast/engine/mezcla.py.

Lo que se cuida aca:
  - la cuenta, y que la banda se corra con el punto sin achicarse;
  - que el nivel salga de los dias que el NEGOCIO opero (no de los del
    producto), de exactamente 28, y con la misma demanda con que se entrena;
  - que no se toque a los intermitentes, a los productos nuevos ni con el
    interruptor puesto;
  - que lo mezclado no reciba ademas la correccion de sesgo;
  - que llegue a la tabla por el camino real del entrenamiento, dos noches
    seguidas (la segunda es la del kept-path, que regenera).
"""
import datetime
from decimal import Decimal

import pytest
from django.core.management import call_command

from forecast import services
from forecast.engine.mezcla import mezclar_con_nivel, nivel
from forecast.models import DailySales, Forecast, ForecastAccuracy, ForecastModel

D = Decimal
DOMINGO = 6


def hoy():
    # Se pide en cada test y no al importar: la suite puede cruzar medianoche.
    return datetime.date.today()


def _dia(fecha, qty=10, lo=7, hi=13):
    return {"date": fecha, "qty_predicted": D(str(qty)),
            "lower_bound": D(str(lo)), "upper_bound": D(str(hi))}


def _proximo(weekday):
    d = hoy() + datetime.timedelta(days=1)
    while d.weekday() != weekday:
        d += datetime.timedelta(days=1)
    return d


# ---------------------------------------------------------------- la cuenta

class TestLaCuenta:
    def test_un_cuarto_de_modelo_y_tres_cuartos_de_nivel(self):
        fcs = [_dia(_proximo(0), qty=100, lo=80, hi=120)]
        mezclar_con_nivel(fcs, D("60"), {DOMINGO})
        assert fcs[0]["qty_predicted"] == D("70.000")      # 25 + 45

    def test_en_dia_cerrado_el_objetivo_es_cero(self):
        """La mascara de dias cerrados despues lo pone en 0 y reparte el resto."""
        fcs = [_dia(_proximo(DOMINGO), qty=20, lo=15, hi=25)]
        mezclar_con_nivel(fcs, D("60"), {DOMINGO})
        assert fcs[0]["qty_predicted"] == D("5.000")

    def test_la_banda_se_corre_con_el_punto_y_conserva_el_ancho(self):
        fcs = [_dia(_proximo(1), qty=10, lo=7, hi=13)]
        mezclar_con_nivel(fcs, D("30"), {DOMINGO})       # 2,5 + 22,5 = 25
        f = fcs[0]
        assert f["qty_predicted"] == D("25.000")
        assert (f["lower_bound"], f["upper_bound"]) == (D("22.000"), D("28.000"))

    def test_la_banda_no_baja_de_cero_ni_deja_afuera_al_punto(self):
        fcs = [_dia(_proximo(2), qty=10, lo=1, hi=11)]
        mezclar_con_nivel(fcs, D("2"), {DOMINGO})        # 2,5 + 1,5 = 4
        f = fcs[0]
        assert f["qty_predicted"] == D("4.000")
        assert f["lower_bound"] == D("0") and f["upper_bound"] == D("5.000")
        assert f["lower_bound"] <= f["qty_predicted"] <= f["upper_bound"]

    def test_sin_dias_no_hay_nivel(self):
        assert nivel([]) is None
        assert nivel([D("2"), D("4")]) == D("3")


# ---------------------------------------------------------------- el nivel y el embudo

def _historia(tenant, product, warehouse, qty_de, dias=60):
    """Una fila por dia abierto (todos menos el domingo, como Marbrava).
    `qty_de(i)` da la venta del dia i hacia atras, o None para no crear fila."""
    for i in range(1, dias + 1):
        d = hoy() - datetime.timedelta(days=i)
        if d.weekday() == DOMINGO:
            continue
        q = qty_de(i)
        if q is None:
            continue
        DailySales.objects.create(tenant=tenant, product=product, warehouse=warehouse,
                                  date=d, qty_sold=D(str(q)))


def _abiertos_recientes(n=28, dias=60):
    """Los ultimos n dias abiertos, del mas reciente al mas viejo."""
    out = []
    for i in range(1, dias + 1):
        d = hoy() - datetime.timedelta(days=i)
        if d.weekday() != DOMINGO:
            out.append((i, d))
    return out[:n]


def _ventana_de_28():
    """Indice i (dias hacia atras) del dia abierto mas viejo de la ventana."""
    return _abiertos_recientes()[-1][0]


def _modelo(tenant, product, warehouse, patron="smooth", params=None):
    return ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse, algorithm="theta",
        demand_pattern=patron, is_active=True, model_params=params or {}, metrics={},
    )


def _semana():
    return [_dia(hoy() + datetime.timedelta(days=i)) for i in range(1, 8)]


def _semana_suma(product):
    return sum(f.qty_predicted for f in _publicado(product))


def _cerca(a, b):
    """La mascara de dias cerrados reparte el domingo en los 6 dias abiertos y
    redondea cada uno a milesimas: la semana puede sumar 0,002 de mas."""
    return abs(D(a) - D(b)) <= D("0.01")


def _publicado(product):
    return list(Forecast.objects.filter(product=product, forecast_date__gt=hoy())
                .order_by("forecast_date"))


@pytest.fixture
def sin_feriados(monkeypatch):
    """El 12-oct cae en la semana pronosticada: sin esto las cuentas exactas
    dependerian del calendario."""
    monkeypatch.setattr(services, "_load_holidays_for_horizon", lambda *a, **k: {})


@pytest.mark.django_db
class TestElNivel:
    def test_sale_de_los_ultimos_28_dias_abiertos_y_nada_mas(
            self, tenant, store, warehouse, product, sin_feriados):
        """Los 28 dias abiertos mas recientes venden 40; los anteriores, 400.
        Si la ventana se pasara un solo dia, el nivel no daria 40."""
        borde = _ventana_de_28()
        _historia(tenant, product, warehouse, lambda i: 40 if i <= borde else 400)
        fm = _modelo(tenant, product, warehouse)

        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})

        fm.refresh_from_db()
        assert fm.model_params["mezcla_prom28"] == {"peso_modelo": 0.25, "nivel": 40.0}
        filas = _publicado(product)
        domingo = [f for f in filas if f.forecast_date.weekday() == DOMINGO]
        assert domingo and all(f.qty_predicted == 0 for f in domingo)
        # 6 dias abiertos a 0,25x10 + 0,75x40 = 32,5, mas el 2,5 del domingo que
        # la mascara reparte entre ellos: la masa de la semana se conserva.
        assert _cerca(sum(f.qty_predicted for f in filas), "197.5")

    def test_un_dia_abierto_sin_venta_del_producto_cuenta_como_cero(
            self, tenant, store, warehouse, product, product_b, sin_feriados):
        """El local opero (otro producto vendio) y este no se vendio: es demanda
        cero de verdad, no un hueco."""
        _historia(tenant, product_b, warehouse, lambda i: 1)            # el local abre
        _historia(tenant, product, warehouse, lambda i: 40 if i % 2 == 0 else None)
        fm = _modelo(tenant, product, warehouse)

        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})

        con_venta = sum(1 for i, _ in _abiertos_recientes() if i % 2 == 0)
        esperado = round(40.0 * con_venta / 28, 3)
        fm.refresh_from_db()
        assert fm.model_params["mezcla_prom28"]["nivel"] == esperado

    def test_un_quiebre_real_no_baja_el_nivel(
            self, tenant, store, warehouse, product, sin_feriados):
        """La venta de un dia de quiebre esta censurada: el entrenamiento la
        interpola en vez de creerle, y el nivel la salta."""
        _historia(tenant, product, warehouse, lambda i: 40)
        quiebres = [d for _, d in _abiertos_recientes()[:5]]
        DailySales.objects.filter(product=product, date__in=quiebres).update(
            qty_sold=D("0"), is_stockout=True)
        fm = _modelo(tenant, product, warehouse)

        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})

        fm.refresh_from_db()
        assert fm.model_params["mezcla_prom28"]["nivel"] == 40.0


@pytest.mark.django_db
def test_el_periodo_de_transicion_del_ingrediente_no_entra_al_nivel(
        tenant, store, warehouse, product, product_b, sin_feriados):
    """Antes de `ingredient_forecast_trusted_from` no habia recetas y el consumo
    de un ingrediente quedaba subregistrado. El entrenamiento esos dias los
    interpola; el nivel no puede creerles. Con los 28 dias de la ventana en
    transicion no queda nada medible, y no se mezcla."""
    from catalog.models import Recipe, RecipeLine
    tenant.ingredient_forecast_trusted_from = hoy() + datetime.timedelta(days=1)
    tenant.save(update_fields=["ingredient_forecast_trusted_from"])
    receta = Recipe.objects.create(tenant=tenant, product=product_b, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=product, qty=D("10"))
    _historia(tenant, product, warehouse, lambda i: 10)          # subregistrado
    fm = _modelo(tenant, product, warehouse)

    services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})

    fm.refresh_from_db()
    assert "mezcla_prom28" not in (fm.model_params or {})
    assert _cerca(_semana_suma(product), "70")


@pytest.mark.django_db
class TestAQuienNo:
    def _sin_mezcla(self, product, fm):
        assert _cerca(_semana_suma(product), "70"), "la semana del modelo, intacta"
        fm.refresh_from_db()
        assert "mezcla_prom28" not in (fm.model_params or {})

    def test_intermitente(self, tenant, store, warehouse, product, sin_feriados):
        _historia(tenant, product, warehouse, lambda i: 40)
        fm = _modelo(tenant, product, warehouse, patron="intermittent")
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        self._sin_mezcla(product, fm)

    def test_producto_mas_nuevo_que_la_ventana(self, tenant, store, warehouse, product,
                                               product_b, sin_feriados):
        """Los dias en que no existia lo diluirian."""
        _historia(tenant, product_b, warehouse, lambda i: 1)
        _historia(tenant, product, warehouse, lambda i: 40 if i <= 20 else None)
        fm = _modelo(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        self._sin_mezcla(product, fm)

    def test_interruptor_de_apagado(self, tenant, store, warehouse, product,
                                    sin_feriados, monkeypatch):
        _historia(tenant, product, warehouse, lambda i: 40)
        fm = _modelo(tenant, product, warehouse, params={"mezcla_prom28": {"nivel": 1.0}})
        monkeypatch.setenv("FORECAST_MEZCLA_OFF", "1")
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        self._sin_mezcla(product, fm)        # y la marca vieja se retira


@pytest.mark.django_db
class TestConLoDemas:
    def test_lo_mezclado_no_recibe_correccion_de_sesgo(
            self, tenant, store, warehouse, product, sin_feriados):
        """El 75% del punto ya es el promedio de la demanda real. Con el modelo
        prediciendo 10 contra 4 reales, el sesgo daria x0,7; no tiene que
        aplicarse, y la marca vieja de sesgo se retira."""
        _historia(tenant, product, warehouse, lambda i: 40)
        for i in range(1, 29):
            ForecastAccuracy.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=hoy() - datetime.timedelta(days=i), qty_predicted=D("10"),
                qty_actual=D("4"), error=D("6"), algorithm="theta",
            )
        fm = _modelo(tenant, product, warehouse, params={"sesgo": {"factor": 0.7}})

        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})

        assert _cerca(_semana_suma(product), "197.5")
        fm.refresh_from_db()
        assert "sesgo" not in fm.model_params
        assert fm.model_params["mezcla_prom28"]["nivel"] == 40.0

    def test_la_banda_calibrada_sigue_conteniendo_al_punto(
            self, tenant, store, warehouse, product, sin_feriados):
        _historia(tenant, product, warehouse, lambda i: 40)
        for i in range(1, 29):
            ForecastAccuracy.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=hoy() - datetime.timedelta(days=i), qty_predicted=D("40"),
                qty_actual=D(str(30 + (i % 5) * 5)), error=D("0"), algorithm="theta",
            )
        fm = _modelo(tenant, product, warehouse)
        services.save_forecasts(tenant, product, warehouse.id, fm, _semana(), D("70"), {})
        filas = _publicado(product)
        assert filas
        for f in filas:
            assert f.lower_bound <= f.qty_predicted <= f.upper_bound, (
                "%s: %s fuera de [%s, %s]" % (f.forecast_date, f.qty_predicted,
                                              f.lower_bound, f.upper_bound))


@pytest.mark.django_db
def test_llega_a_la_tabla_por_el_entrenamiento_real_dos_noches(
        tenant, store, warehouse, product):
    """De punta a punta por el comando. La segunda corrida es la del kept-path,
    que regenera las filas: es el camino que ya se comio una correccion antes
    (ver test_correccion_sesgo)."""
    borde = _ventana_de_28()
    _historia(tenant, product, warehouse, lambda i: 40 if i <= borde else 80, dias=90)

    for noche in (1, 2):
        call_command("train_forecast_models", tenant=tenant.id, product=product.id,
                     horizon=14, verbosity=0)
        fm = ForecastModel.objects.get(product=product, is_active=True)
        assert fm.demand_pattern == "smooth", "precondicion: la serie es smooth"
        assert fm.model_params.get("mezcla_prom28", {}).get("nivel") == 40.0, (
            "noche %d: el nivel no llego (%s)" % (noche, fm.model_params))


@pytest.mark.django_db
class TestConFeriado:
    """El feriado va UNA vez a las dos partes de la mezcla. En un organico se
    aplica despues, sobre lo mezclado. En un derivado de receta su modelo ya lo
    trae de las bebidas (ver test_feriado_derivado), asi que se le aplica solo
    al nivel."""

    def _caso(self, tenant, warehouse, product, algoritmo):
        from forecast.models import Holiday
        _historia(tenant, product, warehouse, lambda i: 40)            # nivel 40
        h = _proximo(2)                                                 # un miercoles
        Holiday.objects.create(tenant=None, name="Feriado de prueba", date=h,
                               demand_multiplier=D("0.50"), pre_days=0,
                               pre_multiplier=D("1"), ramp_type="instant")
        fm = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse, algorithm=algoritmo,
            demand_pattern="smooth", is_active=True, model_params={}, metrics={})
        normal = h + datetime.timedelta(days=1)                         # jueves
        services.save_forecasts(tenant, product, warehouse.id, fm,
                                [_dia(h), _dia(normal)], D("70"), {})
        pub = {f.forecast_date: f.qty_predicted for f in _publicado(product)}
        return pub[h], pub[normal]

    def test_organico_el_feriado_sobre_lo_mezclado(self, tenant, store, warehouse, product):
        en_feriado, normal = self._caso(tenant, warehouse, product, "theta")
        assert normal == D("32.500")                                    # 2,5 + 30
        assert en_feriado == D("16.250")                                # (2,5 + 30) x 0,5

    def test_derivado_el_feriado_solo_al_nivel(self, tenant, store, warehouse, product):
        en_feriado, normal = self._caso(tenant, warehouse, product, "ingredient_derived")
        assert normal == D("32.500")
        assert en_feriado == D("17.500"), (
            "el modelo del derivado ya trae el feriado: 0,25 x 10 + 0,75 x 40 x 0,5")
