"""
tests/test_demand_stopped.py — dejar de pedir lo que dejó de venderse.

Medido en Marbrava el 11/08/26: de 4.931 unidades de sobre-predicción en 7
días, 1.642 eran HELADO con CERO ventas. Es agosto, invierno en Chile; el
helado paró hace meses y el modelo seguía anclado al verano. Vía recetas el
mismo problema costaba más caro: Milkshake, Café Helado y Latte avellana con 0
ventas arrastraban ~1.300 ml de leche fantasma al pedido de compra.

La regla compara la racha seca contra el RITMO PROPIO del producto. Contra un
corte fijo a 7 días secos, sobre los mismos 14 días reales:

    regla              deja de predecir   corta y el producto SÍ vendió
    corte fijo 7d          2.515 uds        31 casos / 87 uds
    esta (3x el ritmo)     1.980 uds         2 casos /  2 uds

Por eso los tests de "NO cortar" son tan importantes como los de cortar: el
corte fijo bajaba más el WAPE anulando productos vivos de rotación lenta.
"""
import datetime
from decimal import Decimal

import pytest

from catalog.models import Product
from forecast.models import DailySales
from forecast.services import (
    demand_stopped,
    _STOPPED_CACHE,
    STOPPED_MIN_DRY_DAYS,
)

D = Decimal
HOY = datetime.date(2026, 8, 11)


@pytest.fixture(autouse=True)
def _limpiar_cache():
    _STOPPED_CACHE.clear()
    yield
    _STOPPED_CACHE.clear()


def _vender(tenant, wh, product, dia, qty=5):
    DailySales.objects.create(
        tenant=tenant, product=product, warehouse=wh, date=dia, qty_sold=D(str(qty)),
    )


def _negocio_abierto(tenant, wh, dias_atras=120, cerrado_dow=6):
    """Producto 'ancla' que vende todos los días operativos.

    Define qué días operó el negocio: sin esto no hay calendario contra el cual
    medir rachas.
    """
    ancla = Product.objects.create(tenant=tenant, name="Café (ancla)", price=D("1000"), is_active=True)
    for i in range(1, dias_atras + 1):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() == cerrado_dow:
            continue
        _vender(tenant, wh, ancla, d, 20)
    return ancla


# ── Sí cortar: demanda que paró ──────────────────────────────────────────────

@pytest.mark.django_db
def test_el_helado_de_invierno_se_corta(tenant, warehouse, product):
    """EL CASO REAL. Vendía a diario en verano, lleva meses sin vender."""
    _negocio_abierto(tenant, warehouse)
    # Vendió todos los días entre hace 120 y hace 60 días; después, nada.
    for i in range(60, 121):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() != 6:
            _vender(tenant, warehouse, product, d, 8)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is True


@pytest.mark.django_db
def test_producto_que_nunca_vendio_se_corta(tenant, warehouse, product):
    """El agujero de la primera versión: sin ritmo con qué comparar, la regla
    los dejaba pasar — y son justo los más muertos."""
    _negocio_abierto(tenant, warehouse)
    # `product` no registra ni una venta.
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is True


@pytest.mark.django_db
def test_producto_con_una_sola_venta_vieja_se_corta(tenant, warehouse, product):
    _negocio_abierto(tenant, warehouse)
    _vender(tenant, warehouse, product, HOY - datetime.timedelta(days=90), 3)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is True


# ── NO cortar: lo que protege a Mario de un quiebre ──────────────────────────

@pytest.mark.django_db
def test_producto_que_vende_a_diario_NO_se_corta(tenant, warehouse, product):
    _negocio_abierto(tenant, warehouse)
    for i in range(1, 60):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() != 6:
            _vender(tenant, warehouse, product, d, 10)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


@pytest.mark.django_db
def test_rotacion_lenta_en_su_ritmo_NO_se_corta(tenant, warehouse, product):
    """EL TEST QUE DESCARTÓ EL CORTE FIJO.

    El Preparado chai vende en tandas cada ~10 días. Con un corte fijo a 7 días
    secos quedaría en cero justo antes de cada tanda — 30 unidades de demanda
    real perdidas en los datos de Marbrava. Su ritmo es ese: no ha parado.
    """
    _negocio_abierto(tenant, warehouse)
    # Vende cada 10 días calendario; la última venta fue hace 9 días.
    for i in range(9, 100, 10):
        _vender(tenant, warehouse, product, HOY - datetime.timedelta(days=i), 4)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


@pytest.mark.django_db
def test_racha_corta_nunca_se_corta(tenant, warehouse, product):
    """Un producto diario con pocos días sin vender no se toca: por debajo del
    mínimo ni siquiera se evalúa el ritmo."""
    _negocio_abierto(tenant, warehouse)
    for i in range(3, 60):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() != 6:
            _vender(tenant, warehouse, product, d, 10)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


@pytest.mark.django_db
def test_sin_historial_no_corta_nada(tenant, warehouse, product):
    """Tenant nuevo: sin calendario no hay racha que medir. Preferimos no
    enmascarar antes que vaciarle el pronóstico a un local que recién arranca."""
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


@pytest.mark.django_db
def test_los_domingos_cerrados_no_inflan_la_racha(tenant, warehouse, product):
    """La racha se cuenta en días OPERATIVOS. Si contáramos días calendario, un
    local que cierra domingos acumularía rachas falsas más rápido."""
    _negocio_abierto(tenant, warehouse)
    # Vendió hace 8 días operativos (que abarcan más de 8 días calendario).
    dias_op = [HOY - datetime.timedelta(days=i) for i in range(1, 30)
               if (HOY - datetime.timedelta(days=i)).weekday() != 6]
    for d in dias_op[7:14]:
        _vender(tenant, warehouse, product, d, 5)
    # 7 días operativos secos < mínimo de 10 → no se corta
    assert STOPPED_MIN_DRY_DAYS == 10
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


# ── La espiral del quiebre: sin stock, la sequía no prueba nada ──────────────

@pytest.mark.django_db
def test_quiebre_reciente_NO_se_confunde_con_demanda_muerta(tenant, warehouse, product):
    """EL BUG QUE CASI DESPLEGAMOS.

    Encontrado el 11/08/26 probando contra la copia real: `Jamon granel` tenía
    stock 0 y 10 días operativos secos, pero había consumido 90 unidades dos
    semanas antes. No dejó de venderse — se quedaron sin jamón.

    Si lo cortáramos, la espiral se retroalimenta sola: sin stock → sin consumo
    → "demanda detenida" → no se pide → sigue sin stock. Para siempre, y sin
    que nadie se dé cuenta salvo el cliente al que le falta el sándwich.
    """
    _negocio_abierto(tenant, warehouse)
    # Consumía cada ~2 días hasta hace 14 días (≈12 días operativos); después
    # nada: se acabó el stock. Queda por encima del mínimo "con stock" (10) y
    # muy por debajo del mínimo "sin stock" (30).
    for i in range(14, 60, 2):
        _vender(tenant, warehouse, product, HOY - datetime.timedelta(days=i), 30)

    # Con stock en cero exigimos una racha mucho más larga: no lo cortamos.
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY, on_hand=0) is False
    # Con stock disponible, la misma sequía SÍ es evidencia de que nadie lo quiere.
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY, on_hand=500) is True


@pytest.mark.django_db
def test_sin_stock_pero_muerto_hace_meses_si_se_corta(tenant, warehouse, product):
    """El helado: stock 0 igual que el jamón, pero lleva una temporada entera
    sin moverse. Ahí la sequía ya no se explica por el quiebre."""
    _negocio_abierto(tenant, warehouse)
    for i in range(70, 121):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() != 6:
            _vender(tenant, warehouse, product, d, 8)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY, on_hand=0) is True


@pytest.mark.django_db
def test_sin_dato_de_stock_se_asume_lo_conservador(tenant, warehouse, product):
    """Si no sabemos el stock, tratamos el caso como 'sin stock' (umbral largo).
    Preferimos pedir de más antes que dejar a Mario sin producto."""
    _negocio_abierto(tenant, warehouse)
    for i in range(14, 60, 2):
        _vender(tenant, warehouse, product, HOY - datetime.timedelta(days=i), 30)
    assert demand_stopped(tenant.id, product.id, warehouse.id, today=HOY) is False


# ── Integración: el pronóstico realmente se pone en cero ─────────────────────

@pytest.mark.django_db
def test_save_forecasts_pone_en_cero_lo_que_paro(tenant, warehouse, product, store):
    from forecast.models import ForecastModel, Forecast
    from forecast.services import save_forecasts

    _negocio_abierto(tenant, warehouse)
    # product sin ventas => demanda detenida
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="adaptive_ma", data_points=60, demand_pattern="lumpy",
        confidence_label="medium",
    )
    daily = [
        {"date": HOY + datetime.timedelta(days=i),
         "qty_predicted": D("12.000"), "lower_bound": D("8.000"), "upper_bound": D("16.000")}
        for i in range(1, 8)
    ]
    save_forecasts(tenant, product, warehouse.id, fm, daily, Decimal("70"), {})

    guardados = Forecast.objects.filter(tenant=tenant, product=product)
    assert guardados.exists()
    assert all(f.qty_predicted == D("0.000") for f in guardados), \
        "un producto que dejó de venderse no debe generar pedido de compra"


@pytest.mark.django_db
def test_save_forecasts_respeta_al_producto_vivo(tenant, warehouse, product, store):
    """Control: el que sigue vendiendo conserva su pronóstico intacto."""
    from forecast.models import ForecastModel, Forecast
    from forecast.services import save_forecasts

    _negocio_abierto(tenant, warehouse)
    for i in range(1, 60):
        d = HOY - datetime.timedelta(days=i)
        if d.weekday() != 6:
            _vender(tenant, warehouse, product, d, 10)

    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="adaptive_ma", data_points=60, demand_pattern="smooth",
        confidence_label="high",
    )
    daily = [
        {"date": HOY + datetime.timedelta(days=i),
         "qty_predicted": D("12.000"), "lower_bound": D("8.000"), "upper_bound": D("16.000")}
        for i in range(1, 8)
    ]
    save_forecasts(tenant, product, warehouse.id, fm, daily, Decimal("70"), {})
    assert Forecast.objects.filter(
        tenant=tenant, product=product, qty_predicted__gt=0,
    ).exists()
