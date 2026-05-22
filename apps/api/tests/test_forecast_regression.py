"""
Tests de REGRESION del motor de forecast — los 6 bugs corregidos el 22/05/26.

Cada test FALLA si el bug correspondiente vuelve a aparecer. Este archivo es
el blindaje del motor: garantiza que un cambio futuro no re-rompa lo arreglado.

Bugs cubiertos:
  1. MAPE roto -> WAPE robusto
  2. Holt-Winters daba 0 los sabados (dias cerrados)
  3. Ensemble no calculaba WAPE -> ganaba la seleccion injustamente
  4. Ingredientes inactivos no se entrenaban
  5. _regen_from_existing devolvia 0 para theta/croston
  6. Periodo de transicion de migracion contaminaba el forecast de ingredientes

+ Casos borde (robustez multi-tenant).
"""
import datetime
from decimal import Decimal

import pytest


# ════════════════════════════════════════════════════════════════════════
# BUG 1 — MAPE roto -> WAPE
# ════════════════════════════════════════════════════════════════════════

class TestBug1WapeMetric:
    def test_compute_metrics_incluye_wape(self):
        from forecast.engine.utils import _compute_metrics
        m = _compute_metrics([10, 10, 10], [10, 10, 10])
        assert "wape" in m

    def test_wape_no_explota_con_dia_de_demanda_chica(self):
        """El MAPE clasico explota si un dia se vende 1 y se predice 5
        (|5-1|/1 = 400%). WAPE suma global -> robusto."""
        from forecast.engine.utils import _compute_metrics
        actuals = [50, 50, 1, 50, 50]
        predictions = [48, 52, 5, 49, 51]
        m = _compute_metrics(actuals, predictions)
        # El MAPE DEBE explotar — es la naturaleza del bug que evitamos.
        assert m["mape"] > 70, f"MAPE deberia explotar, fue {m['mape']}"
        # WAPE = Σ|err|/Σreal = 10/201 ≈ 5% — robusto.
        assert m["wape"] < 15, f"WAPE deberia ser robusto, fue {m['wape']}"

    def test_wape_cero_cuando_no_hay_error(self):
        from forecast.engine.utils import _compute_metrics
        m = _compute_metrics([10, 20, 30], [10, 20, 30])
        assert m["wape"] == 0

    def test_wape_perfecto_con_demanda_cero(self):
        from forecast.engine.utils import _compute_metrics
        m = _compute_metrics([0, 0, 0], [0, 0, 0])
        assert m["wape"] == 0

    def test_average_metrics_incluye_wape(self):
        from forecast.engine.utils import _average_metrics
        folds = [
            {"mae": 5, "mape": 20, "wape": 25, "rmse": 7, "bias": 1},
            {"mae": 6, "mape": 22, "wape": 27, "rmse": 8, "bias": 2},
        ]
        avg = _average_metrics(folds)
        assert "wape" in avg
        assert avg["wape"] == 26.0

    def test_confidence_label_usa_wape(self):
        """La confianza debe basarse en WAPE, no en el MAPE roto."""
        from forecast.services import compute_confidence_label
        _, reason = compute_confidence_label(60, 25, "smooth")
        assert "WAPE" in reason
        assert "MAPE" not in reason


# ════════════════════════════════════════════════════════════════════════
# BUG 2 — Holt-Winters daba 0 los sabados (dias cerrados)
# ════════════════════════════════════════════════════════════════════════

def _serie_semanal(dias, cerrado_dow=None, base=100.0):
    """Serie diaria; si cerrado_dow esta seteado, ese dia de semana = 0."""
    serie = []
    d = datetime.date(2025, 1, 6)  # lunes
    for i in range(dias):
        dia = d + datetime.timedelta(days=i)
        qty = 0.0 if dia.weekday() == cerrado_dow else base
        serie.append((dia, Decimal(str(qty))))
    return serie


class TestBug2HoltWintersClosedDays:
    def test_has_closed_weekday_detecta_dia_cerrado(self):
        from forecast.engine.algorithms.holt_winters import _has_closed_weekday
        serie = _serie_semanal(63, cerrado_dow=6)  # domingos en 0
        assert _has_closed_weekday(serie) is True

    def test_has_closed_weekday_falso_si_todos_abren(self):
        from forecast.engine.algorithms.holt_winters import _has_closed_weekday
        serie = _serie_semanal(63)  # todos los dias venden
        assert _has_closed_weekday(serie) is False

    def test_holt_winters_se_descarta_con_dia_cerrado(self):
        """HW no debe competir si hay un dia sistematicamente cerrado —
        produce estacionalidad negativa que da forecast 0 los dias flojos."""
        from forecast.engine.algorithms.holt_winters import HoltWinters
        serie = _serie_semanal(63, cerrado_dow=6)
        res = HoltWinters().forecast(serie, horizon_days=14)
        assert res is None, "HW debe auto-descartarse con un dia cerrado"

    def test_holt_winters_funciona_sin_dias_cerrados(self):
        """Sin dias cerrados, HW debe seguir produciendo forecast."""
        from forecast.engine.algorithms.holt_winters import HoltWinters
        serie = _serie_semanal(63)
        res = HoltWinters().forecast(serie, horizon_days=14)
        # Puede ser None si statsmodels no esta, pero si esta debe predecir.
        if res is not None:
            assert len(res["forecasts"]) == 14
            assert all(float(f["qty_predicted"]) > 0 for f in res["forecasts"])


# ════════════════════════════════════════════════════════════════════════
# BUG 3 — Ensemble no calculaba WAPE
# ════════════════════════════════════════════════════════════════════════

class TestBug3EnsembleWape:
    def _candidate(self, algo, qty, wape):
        fechas = [datetime.date(2025, 3, 1) + datetime.timedelta(days=i) for i in range(14)]
        return {
            "algorithm": algo,
            "forecasts": [
                {"date": f, "qty_predicted": Decimal(str(qty)),
                 "lower_bound": Decimal("0"), "upper_bound": Decimal(str(qty * 2))}
                for f in fechas
            ],
            "metrics": {"mae": 5, "mape": 20, "wape": wape, "rmse": 7, "bias": 0},
            "data_points": 120,
        }

    def test_ensemble_calcula_wape_en_metrics(self):
        """El ensemble debe exponer WAPE para competir de igual a igual en
        select_best_model (antes solo tenia MAPE y ganaba comparando mal)."""
        from forecast.engine.algorithms.ensemble import EnsembleForecast
        serie = _serie_semanal(120)
        candidates = [
            self._candidate("theta", 10, 30),
            self._candidate("adaptive_ma", 12, 40),
        ]
        res = EnsembleForecast().forecast(
            serie, horizon_days=14, candidates=candidates, demand_pattern="smooth",
        )
        assert res is not None
        assert "wape" in res["metrics"], "ensemble debe calcular WAPE"
        # WAPE del ensemble = promedio ponderado de los componentes (30 y 40)
        assert 25 <= res["metrics"]["wape"] <= 45


# ════════════════════════════════════════════════════════════════════════
# BUG 4 — Ingredientes inactivos no se entrenaban
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBug4IngredienteInactivoEntrena:
    def test_ingrediente_inactivo_de_receta_activa_se_entrena(self, tenant, warehouse):
        """Un ingrediente puede estar is_active=False (no se vende directo)
        pero ser parte de una receta activa -> debe entrenarse igual."""
        from catalog.models import Product, Recipe, RecipeLine
        from forecast.models import DailySales, ForecastModel
        from django.core.management import call_command

        # Producto vendible (con receta) + ingrediente INACTIVO
        bebida = Product.objects.create(
            tenant=tenant, name="Bebida test", price=Decimal("3000"), is_active=True)
        ingrediente = Product.objects.create(
            tenant=tenant, name="Insumo test", price=Decimal("0"), is_active=False)
        recipe = Recipe.objects.create(tenant=tenant, product=bebida, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=ingrediente, qty=Decimal("10"))

        # DailySales para el ingrediente (60 dias terminando ayer — sin gap).
        hoy = datetime.date.today()
        for i in range(60):
            DailySales.objects.create(
                tenant=tenant, product=ingrediente, warehouse=warehouse,
                date=hoy - datetime.timedelta(days=60 - i),
                qty_sold=Decimal("50"), forecast_only=True)

        call_command("train_forecast_models", tenant=tenant.id)

        modelo = ForecastModel.objects.filter(
            tenant=tenant, product=ingrediente, is_active=True).first()
        assert modelo is not None, (
            "el ingrediente inactivo de una receta activa debe tener modelo")


# ════════════════════════════════════════════════════════════════════════
# BUG 5 — _regen_from_existing devolvia 0 para theta/croston
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBug5RegenNoDevuelveCero:
    def test_regen_con_theta_no_da_forecast_cero(self, tenant, warehouse, product):
        """_regen_from_existing debe RE-EJECUTAR el algoritmo. Antes re-derivaba
        desde params (avg_daily) que theta no guarda -> forecast 0."""
        from forecast.models import ForecastModel, Forecast
        from forecast.services import _regen_from_existing
        from inventory.models import StockItem

        # Modelo theta (theta no guarda avg_daily en params)
        fm = ForecastModel.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            algorithm="theta", version=1,
            model_params={"alpha": 0.2, "slope": 0.1, "intercept": 50},
            metrics={"mae": 5, "wape": 30}, data_points=120, is_active=True)
        si = StockItem.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            on_hand=Decimal("100"), avg_cost=Decimal("10"),
            stock_value=Decimal("1000"))
        # Serie con demanda real consistente (~50/dia)
        d0 = datetime.date(2026, 1, 1)
        serie = [(d0 + datetime.timedelta(days=i), Decimal("50")) for i in range(120)]

        _regen_from_existing(
            tenant, product, warehouse.id, fm,
            today=datetime.date(2026, 5, 1), horizon=14, window=21,
            series=serie, stock_items={(warehouse.id, product.id): si})

        fcs = Forecast.objects.filter(tenant=tenant, product=product)
        assert fcs.exists(), "_regen debe guardar forecasts"
        total = sum((f.qty_predicted for f in fcs), Decimal("0"))
        assert total > 0, "_regen no debe devolver forecast 0 para theta"


# ════════════════════════════════════════════════════════════════════════
# BUG 6 — Periodo de transicion contamina el forecast de ingredientes
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBug6PeriodoTransicion:
    def test_dias_de_transicion_se_interpolan(self, tenant, warehouse):
        """Con ingredient_forecast_trusted_from seteado, los dias de Pulstock
        (forecast_only=False) anteriores a esa fecha se interpolan en vez de
        usar el valor subregistrado de la transicion."""
        from catalog.models import Product, Recipe, RecipeLine
        from forecast.models import DailySales, ForecastModel, Forecast
        from django.core.management import call_command

        hoy = datetime.date.today()
        # trusted_from = mañana -> TODO dato de Pulstock previo a hoy es
        # "transicion" y debe interpolarse.
        tenant.ingredient_forecast_trusted_from = hoy + datetime.timedelta(days=1)
        tenant.save(update_fields=["ingredient_forecast_trusted_from"])

        bebida = Product.objects.create(
            tenant=tenant, name="Bebida T", price=Decimal("3000"), is_active=True)
        ingrediente = Product.objects.create(
            tenant=tenant, name="Leche T", price=Decimal("0"), is_active=True)
        recipe = Recipe.objects.create(tenant=tenant, product=bebida, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=ingrediente, qty=Decimal("10"))

        # Serie de 95 dias terminando AYER (sin gap con `today`):
        #   - primeros 75: historico confiable (Fudo) consumo alto ~200
        #   - ultimos 20: transicion (Pulstock real) subregistrada ~10
        inicio = hoy - datetime.timedelta(days=95)
        for i in range(95):
            fecha = inicio + datetime.timedelta(days=i)
            if i < 75:
                qty, fo = Decimal("200"), True
            else:
                qty, fo = Decimal("10"), False  # transicion subregistrada
            DailySales.objects.create(
                tenant=tenant, product=ingrediente, warehouse=warehouse,
                date=fecha, qty_sold=qty, forecast_only=fo)

        call_command("train_forecast_models", tenant=tenant.id)

        fm = ForecastModel.objects.filter(
            tenant=tenant, product=ingrediente, is_active=True).first()
        assert fm is not None
        fcs = list(Forecast.objects.filter(tenant=tenant, product=ingrediente)
                   .order_by("forecast_date")[:7])
        fc7 = sum((f.qty_predicted for f in fcs), Decimal("0"))
        # Sin el fix, los 20 dias de transicion en ~10 arrastrarian el
        # forecast hacia abajo. Con el fix, se interpolan -> forecast cerca
        # del nivel historico (~200/dia -> ~1400/semana).
        assert fc7 > 700, (
            f"el forecast deberia ignorar la transicion subregistrada, fue {fc7}")


# ════════════════════════════════════════════════════════════════════════
# CASOS BORDE — robustez multi-tenant
# ════════════════════════════════════════════════════════════════════════

class TestCasosBordeEngine:
    def test_compute_metrics_lista_vacia(self):
        from forecast.engine.utils import _compute_metrics
        m = _compute_metrics([], [])
        assert m["mae"] == 0

    def test_has_closed_weekday_serie_vacia(self):
        from forecast.engine.algorithms.holt_winters import _has_closed_weekday
        assert _has_closed_weekday([]) is False

    def test_has_closed_weekday_serie_corta(self):
        """Pocos dias (< min_occurrences) no deben marcar dia cerrado."""
        from forecast.engine.algorithms.holt_winters import _has_closed_weekday
        serie = _serie_semanal(5, cerrado_dow=6)
        assert _has_closed_weekday(serie) is False

    def test_confidence_label_data_points_cero(self):
        from forecast.services import compute_confidence_label
        label, _ = compute_confidence_label(0, 999, "insufficient")
        assert label in ("very_low", "low")


@pytest.mark.django_db
class TestCasosBordeEntrenamiento:
    def test_producto_sin_ventas_no_rompe_entrenamiento(self, tenant, warehouse, product):
        """Un producto sin ninguna DailySales no debe tumbar el comando."""
        from django.core.management import call_command
        # No se crea ninguna DailySales — el comando debe correr sin excepcion.
        call_command("train_forecast_models", tenant=tenant.id)

    def test_producto_un_solo_dia_no_rompe(self, tenant, warehouse, product):
        """Un producto con un unico dia de datos no debe romper el comando."""
        from forecast.models import DailySales
        from django.core.management import call_command
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=datetime.date(2026, 5, 1), qty_sold=Decimal("5"))
        call_command("train_forecast_models", tenant=tenant.id)
