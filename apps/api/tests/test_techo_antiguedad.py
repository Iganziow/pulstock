"""
tests/test_techo_antiguedad.py — un modelo no puede vivir para siempre.

Medido en produccion el 21-sep-2026, ventana 30-jun a 13-sep: el nivel que
publica el modelo NO se parece al real dia contra dia (correlacion +0,07 en
Leche entera) pero se parece muchisimo corrido 11 dias (+0,83). La señal esta;
llega tarde. Un promedio movil de 28 dias, que atrasa 6, le gana por eso.

De donde sale el atraso: el kept-path conserva el modelo de anoche cuando el
fresco no le gana, y en los productos erraticos el fresco casi nunca gana
--el WAPE del incumbente es un backtest congelado--. Quedaban 70 de 197 modelos
activos con mas de 30 dias, promedio 62,7.

El caso que mas duele: la Leche entera se reentrena TODAS las noches, pero se
arma sumando 27 modelos padre cuya antiguedad mediana es de 30 dias. Una suma
fresca de partes rancias. Por eso los padres tienen un techo mas corto.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from catalog.models import Product, Recipe, RecipeLine, Unit
from forecast.models import DailySales, ForecastModel
from forecast.services import (
    MAX_EDAD_MODELO_DIAS, MAX_EDAD_MODELO_PADRE_DIAS, modelo_vencido,
)

HOY = date.today()


@pytest.fixture
def ruidoso(db, tenant, warehouse_a):
    """Demanda ruidosa: cualquier modelo fresco da WAPE alto, asi que el legacy
    con WAPE 5% es imbatible y el kept-path aplica. Es lo que queremos ejercitar."""
    u, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN", defaults={"name": "Unidad", "family": "COUNT"},
    )
    p = Product.objects.create(tenant=tenant, name="Ruidoso", unit_obj=u, is_active=True)
    noise = [1, 5, 2, 6, 3]
    for i in range(70, 0, -1):
        d = HOY - timedelta(days=i)
        if d.weekday() == 6:
            continue
        DailySales.objects.create(
            tenant=tenant, product=p, warehouse=warehouse_a, date=d,
            qty_sold=Decimal(str(noise[i % len(noise)])), forecast_only=False,
        )
    return p


def _modelo(tenant, product, warehouse, dias_de_antiguedad):
    """Modelo 'imbatible' por WAPE, entrenado hace N dias."""
    fm = ForecastModel.objects.create(
        tenant=tenant, product=product, warehouse=warehouse,
        algorithm="adaptive_ma", version=1, is_active=True,
        model_params={"avg_daily": "3"},
        metrics={"wape": 5.0, "mae": 0.1, "mape": 5.0},
        data_points=60, demand_pattern="smooth",
        confidence_label="high", confidence_reason="(legacy)",
    )
    # trained_at es auto_now_add: hay que pisarlo despues de crear.
    ForecastModel.objects.filter(id=fm.id).update(
        trained_at=fm.trained_at - timedelta(days=dias_de_antiguedad),
    )
    fm.refresh_from_db()
    return fm


def _hacer_padre(tenant, padre, ingrediente):
    r = Recipe.objects.create(tenant=tenant, product=padre, is_active=True)
    RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=ingrediente,
                              qty=Decimal("1.0"))


# ── la regla ─────────────────────────────────────────────────────────────────

def test_un_modelo_nuevo_no_esta_vencido(db, tenant, warehouse_a, ruidoso):
    fm = _modelo(tenant, ruidoso, warehouse_a, 1)
    assert not modelo_vencido(tenant.id, ruidoso, fm, HOY)


def test_al_llegar_al_techo_esta_vencido(db, tenant, warehouse_a, ruidoso):
    fm = _modelo(tenant, ruidoso, warehouse_a, MAX_EDAD_MODELO_DIAS)
    assert modelo_vencido(tenant.id, ruidoso, fm, HOY)


def test_un_dia_antes_del_techo_todavia_no(db, tenant, warehouse_a, ruidoso):
    fm = _modelo(tenant, ruidoso, warehouse_a, MAX_EDAD_MODELO_DIAS - 1)
    assert not modelo_vencido(tenant.id, ruidoso, fm, HOY)


def test_el_padre_de_una_receta_tiene_techo_mas_corto(
    db, tenant, warehouse_a, ruidoso, product,
):
    """De los padres cuelgan los ingredientes derivados, que son el nucleo."""
    _hacer_padre(tenant, ruidoso, product)
    edad = MAX_EDAD_MODELO_PADRE_DIAS
    assert edad < MAX_EDAD_MODELO_DIAS
    fm = _modelo(tenant, ruidoso, warehouse_a, edad)
    assert modelo_vencido(tenant.id, ruidoso, fm, HOY), (
        "Un padre con %d dias ya tiene que estar vencido" % edad
    )


def test_una_receta_inactiva_no_acorta_el_techo(
    db, tenant, warehouse_a, ruidoso, product,
):
    r = Recipe.objects.create(tenant=tenant, product=ruidoso, is_active=False)
    RecipeLine.objects.create(tenant=tenant, recipe=r, ingredient=product,
                              qty=Decimal("1.0"))
    fm = _modelo(tenant, ruidoso, warehouse_a, MAX_EDAD_MODELO_PADRE_DIAS)
    assert not modelo_vencido(tenant.id, ruidoso, fm, HOY)


def test_sin_modelo_previo_no_explota(db, tenant, ruidoso):
    assert not modelo_vencido(tenant.id, ruidoso, None, HOY)


# ── el efecto en la noche ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_un_modelo_vencido_se_reentrena_aunque_su_wape_sea_imbatible(
    tenant, warehouse_a, ruidoso,
):
    """El caso que importa: WAPE fosil de 5% que ningun candidato honesto puede
    batir. Sin techo, ese modelo vivia para siempre."""
    viejo = _modelo(tenant, ruidoso, warehouse_a, MAX_EDAD_MODELO_DIAS + 20)

    call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

    activo = ForecastModel.objects.filter(
        tenant=tenant, product=ruidoso, is_active=True,
    ).first()
    assert activo is not None
    assert activo.id != viejo.id, (
        "Pasado el techo de antiguedad el kept-path tiene que bypassearse."
    )


@pytest.mark.django_db
def test_un_modelo_reciente_se_sigue_conservando(tenant, warehouse_a, ruidoso):
    """Control: no rompimos el kept-path, que existe para dar estabilidad."""
    viejo = _modelo(tenant, ruidoso, warehouse_a, 2)

    call_command("train_forecast_models", tenant=tenant.id, verbosity=0)

    activo = ForecastModel.objects.filter(
        tenant=tenant, product=ruidoso, is_active=True,
    ).first()
    assert activo is not None and activo.id == viejo.id, (
        "Bajo el techo, el modelo de anoche se sigue conservando."
    )
