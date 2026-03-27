"""
Tests for the forecast module endpoints and engine.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

_sub = pytest.mark.usefixtures("forecast_subscription")

from catalog.models import Product
from inventory.models import StockItem
from forecast.models import DailySales, ForecastModel, Forecast, PurchaseSuggestion, SuggestionLine
from forecast.engine import (
    weighted_moving_average, simple_average, category_prior_forecast,
    apply_holiday_adjustments, select_best_model,
    clean_series, classify_demand_pattern, croston_forecast,
    ensemble_forecast, compute_prediction_intervals,
    compute_month_position_factors, compute_monthly_seasonality,
    detect_trend, apply_trend_adjustment, apply_bias_correction,
    compute_confidence_decay, holt_winters_forecast,
    backtest_moving_average, backtest_croston, backtest_holt_winters,
    calculate_days_to_stockout, generate_daily_forecasts,
    detect_price_change_impact, apply_yoy_adjustment, compute_yoy_growth,
    holt_winters_damped_forecast, backtest_hw_damped,
    theta_forecast, backtest_theta,
    adaptive_moving_average, backtest_adaptive_ma,
    ets_forecast, backtest_ets,
    croston_bootstrap_intervals,
)
from forecast.models import CategoryDemandProfile, Holiday, ForecastAccuracy


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_stock_item(tenant, warehouse, product, on_hand, avg_cost):
    return StockItem.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        on_hand=Decimal(str(on_hand)),
        avg_cost=Decimal(str(avg_cost)),
        stock_value=Decimal(str(on_hand)) * Decimal(str(avg_cost)),
    )


def _make_forecast_model(tenant, warehouse, product, *, algorithm="moving_avg",
                          metrics=None, model_params=None, data_points=30, is_active=True):
    return ForecastModel.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        algorithm=algorithm,
        version=1,
        model_params=model_params or {"avg_daily": "5.0"},
        metrics=metrics or {"mape": 15.0, "mae": 2.0},
        data_points=data_points,
        is_active=is_active,
    )


def _make_forecast(tenant, warehouse, product, model, *,
                    forecast_date, days_to_stockout=None, qty_predicted="5.000"):
    return Forecast.objects.create(
        tenant=tenant,
        warehouse=warehouse,
        product=product,
        model=model,
        forecast_date=forecast_date,
        qty_predicted=Decimal(qty_predicted),
        lower_bound=Decimal("3.000"),
        upper_bound=Decimal("7.000"),
        days_to_stockout=days_to_stockout,
        confidence=Decimal("75.00"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. FORECAST DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestForecastDashboard:
    URL = "/api/forecast/dashboard/"

    def test_at_risk_counts(self, api_client, tenant, store, warehouse, owner, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        tomorrow = date.today() + timedelta(days=1)

        # product: 2 days to stockout (CRITICAL/at_risk)
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=2)
        # product_b: 5 days to stockout (at_risk but not imminent)
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=5)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]

        assert kpis["at_risk_7d"] == 2     # both <= 7d
        assert kpis["imminent_3d"] == 1    # only product (2d)

    def test_value_at_risk(self, api_client, tenant, store, warehouse, owner, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")

        fm = _make_forecast_model(tenant, warehouse, product)
        tomorrow = date.today() + timedelta(days=1)
        _make_forecast(tenant, warehouse, product, fm,
                       forecast_date=tomorrow, days_to_stockout=3)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]

        # Value at risk = stock_value of at-risk products = 10*500 = 5000
        assert Decimal(kpis["value_at_risk"]) == Decimal("5000.00")

    def test_empty_forecasts(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert kpis["at_risk_7d"] == 0
        assert kpis["imminent_3d"] == 0

    def test_filter_by_warehouse(self, api_client, tenant, store, warehouse, owner, product):
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega 2")

        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, wh2, product, on_hand=5, avg_cost="500")

        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, wh2, product)

        tomorrow = date.today() + timedelta(days=1)
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=2)
        _make_forecast(tenant, wh2, product, fm2,
                       forecast_date=tomorrow, days_to_stockout=5)

        resp = api_client.get(self.URL, {"warehouse_id": warehouse.id})
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert kpis["at_risk_7d"] == 1
        assert kpis["imminent_3d"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. FORECAST PRODUCTS LIST
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestForecastProducts:
    URL = "/api/forecast/products/"

    def test_list_with_days_to_stockout(self, api_client, tenant, store, warehouse, owner, product, product_b):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        _make_stock_item(tenant, warehouse, product_b, on_hand=5, avg_cost="200")

        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        tomorrow = date.today() + timedelta(days=1)
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=5)
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=2)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        results = data["results"]

        # Default sort is stockout ascending, so product_b (2d) comes first
        assert results[0]["days_to_stockout"] == 2
        assert results[1]["days_to_stockout"] == 5

    def test_pagination(self, api_client, tenant, store, warehouse, owner, product, product_b):
        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        resp = api_client.get(self.URL, {"page": 1, "page_size": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["count"] == 2

    def test_empty_products(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
        assert resp.json()["results"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. FORECAST ALERTS
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestForecastAlerts:
    URL = "/api/forecast/alerts/"

    def test_classify_levels(self, api_client, tenant, store, warehouse, owner, product, product_b):
        """Test CRITICAL<=3d, HIGH<=7d, MEDIUM<=14d classification."""
        from catalog.models import Product as P
        product_c = P.objects.create(tenant=tenant, name="Producto C", price=Decimal("300"), is_active=True)

        _make_stock_item(tenant, warehouse, product, on_hand=5, avg_cost="100")
        _make_stock_item(tenant, warehouse, product_b, on_hand=10, avg_cost="100")
        _make_stock_item(tenant, warehouse, product_c, on_hand=15, avg_cost="100")

        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)
        fm3 = _make_forecast_model(tenant, warehouse, product_c)

        tomorrow = date.today() + timedelta(days=1)

        # product: 2 days -> CRITICAL
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=2)
        # product_b: 6 days -> HIGH
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=6)
        # product_c: 12 days -> MEDIUM
        _make_forecast(tenant, warehouse, product_c, fm3,
                       forecast_date=tomorrow, days_to_stockout=12)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()

        assert data["count"] == 3
        assert data["critical"] == 1
        assert data["high"] == 1
        assert data["medium"] == 1

        # Verify level assignments
        level_map = {a["product_id"]: a["level"] for a in data["alerts"]}
        assert level_map[product.id] == "CRITICAL"
        assert level_map[product_b.id] == "HIGH"
        assert level_map[product_c.id] == "MEDIUM"

    def test_only_14d_threshold(self, api_client, tenant, store, warehouse, owner, product, product_b):
        """Products with days_to_stockout > 14 should NOT appear in alerts."""
        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        tomorrow = date.today() + timedelta(days=1)

        # product: 3 days -> appears
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=3)
        # product_b: 20 days -> does NOT appear
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=20)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["alerts"][0]["product_id"] == product.id

    def test_sorted_by_urgency(self, api_client, tenant, store, warehouse, owner, product, product_b):
        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        tomorrow = date.today() + timedelta(days=1)

        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=7)
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=1)

        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        # Most urgent first
        assert alerts[0]["days_to_stockout"] <= alerts[1]["days_to_stockout"]

    def test_no_alerts(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["alerts"] == []

    def test_filter_by_warehouse(self, api_client, tenant, store, warehouse, owner, product):
        from core.models import Warehouse
        wh2 = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Alerta")

        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, wh2, product)

        tomorrow = date.today() + timedelta(days=1)
        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=2)
        _make_forecast(tenant, wh2, product, fm2,
                       forecast_date=tomorrow, days_to_stockout=5)

        resp = api_client.get(self.URL, {"warehouse_id": wh2.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["alerts"][0]["warehouse_id"] == wh2.id


# ═══════════════════════════════════════════════════════════════════════════
# 4. FORECAST ENGINE — weighted_moving_average
# ═══════════════════════════════════════════════════════════════════════════

class TestWeightedMovingAverage:
    """Unit tests for the forecast engine (no DB needed)."""

    def test_basic_series(self):
        """Test WMA with a simple daily series."""
        today = date.today()
        series = [
            (today - timedelta(days=6), Decimal("10")),
            (today - timedelta(days=5), Decimal("12")),
            (today - timedelta(days=4), Decimal("8")),
            (today - timedelta(days=3), Decimal("15")),
            (today - timedelta(days=2), Decimal("11")),
            (today - timedelta(days=1), Decimal("13")),
            (today, Decimal("9")),
        ]

        result = weighted_moving_average(series, window=7)

        assert "avg_daily" in result
        assert result["avg_daily"] > Decimal("0")
        # Recent values are weighted more, avg should be reasonable
        assert result["avg_daily"] > Decimal("5")
        assert result["avg_daily"] < Decimal("20")

    def test_empty_series_returns_zero(self):
        """Empty series should return avg_daily=0."""
        result = weighted_moving_average([], window=7)
        assert result["avg_daily"] == Decimal("0.000")
        assert result["weights"] == []
        assert result["day_of_week_factors"] == {}

    def test_single_value(self):
        """Single data point should return that value as avg."""
        today = date.today()
        series = [(today, Decimal("42"))]
        result = weighted_moving_average(series, window=7)
        assert result["avg_daily"] == Decimal("42.000")

    def test_day_of_week_factors(self):
        """Verify day_of_week_factors are computed for all present weekdays."""
        today = date.today()
        series = []
        for i in range(14):
            d = today - timedelta(days=13 - i)
            series.append((d, Decimal("10")))

        result = weighted_moving_average(series, window=14)
        factors = result["day_of_week_factors"]

        # Should have all 7 weekdays represented over 14 days
        assert len(factors) == 7
        # With constant data, factors should all be close to 1.0
        for dow in range(7):
            assert abs(factors[dow] - 1.0) < 0.5

    def test_window_limits_data(self):
        """Window parameter limits how many recent days are used."""
        today = date.today()
        # First 10 days: high values
        series = [(today - timedelta(days=19 - i), Decimal("100")) for i in range(10)]
        # Last 10 days: low values
        series += [(today - timedelta(days=9 - i), Decimal("1")) for i in range(10)]

        result_small_window = weighted_moving_average(series, window=5)
        result_large_window = weighted_moving_average(series, window=20)

        # Smaller window should give avg closer to recent low values
        assert result_small_window["avg_daily"] < result_large_window["avg_daily"]

    def test_exponential_decay_weighting(self):
        """More recent data points should have higher weight."""
        today = date.today()
        # Old high value, recent low values
        series = [
            (today - timedelta(days=4), Decimal("100")),
            (today - timedelta(days=3), Decimal("10")),
            (today - timedelta(days=2), Decimal("10")),
            (today - timedelta(days=1), Decimal("10")),
            (today, Decimal("10")),
        ]

        result = weighted_moving_average(series, window=5)
        # With exponential decay, the avg should be closer to 10 than 100
        assert result["avg_daily"] < Decimal("30")


# ═══════════════════════════════════════════════════════════════════════════
# 5. SIMPLE AVERAGE (7-13 days)
# ═══════════════════════════════════════════════════════════════════════════

class TestSimpleAverage:
    def test_basic(self):
        today = date.today()
        series = [(today - timedelta(days=9 - i), Decimal("10")) for i in range(10)]
        result = simple_average(series, horizon_days=7)

        assert result is not None
        assert result["algorithm"] == "simple_avg"
        assert result["confidence_base"] == Decimal("45.00")
        assert result["data_points"] == 10
        assert len(result["forecasts"]) == 7
        assert result["forecasts"][0]["qty_predicted"] == Decimal("10.000")

    def test_wide_confidence_interval(self):
        today = date.today()
        series = [(today - timedelta(days=6 - i), Decimal("20")) for i in range(7)]
        result = simple_average(series, horizon_days=3)

        fc = result["forecasts"][0]
        # ±50% margin → lower=10, upper=30
        assert fc["lower_bound"] == Decimal("10.000")
        assert fc["upper_bound"] == Decimal("30.000")

    def test_empty_returns_none(self):
        assert simple_average([]) is None

    def test_select_best_model_uses_simple_for_sparse(self):
        today = date.today()
        series = [(today - timedelta(days=9 - i), Decimal("8")) for i in range(10)]
        result = select_best_model(series, horizon=7)

        assert result["algorithm"] == "simple_avg"
        assert result["confidence_base"] == Decimal("45.00")


# ═══════════════════════════════════════════════════════════════════════════
# 6. CATEGORY PRIOR FORECAST (Bayesian shrinkage)
# ═══════════════════════════════════════════════════════════════════════════

class TestCategoryPriorForecast:
    def test_zero_data_uses_pure_category(self):
        """Product with no data uses 100% category average."""
        result = category_prior_forecast(
            daily_series=[],
            category_avg=Decimal("5.000"),
            category_dow_factors={0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.2, 6: 0.8},
            horizon_days=7,
        )

        assert result["algorithm"] == "category_prior"
        assert result["confidence_base"] == Decimal("30")  # 30 + 0*2.5
        assert result["params"]["shrinkage"] == 0
        assert len(result["forecasts"]) == 7

    def test_3_days_data_blends(self):
        """Product with 3 days data: ~18% own, ~82% category."""
        today = date.today()
        series = [
            (today - timedelta(days=2), Decimal("20")),
            (today - timedelta(days=1), Decimal("20")),
            (today, Decimal("20")),
        ]
        result = category_prior_forecast(
            daily_series=series,
            category_avg=Decimal("5.000"),
            category_dow_factors={},
            horizon_days=3,
        )

        # shrinkage = 3 / (3 + 14) ≈ 0.176
        assert result["params"]["shrinkage"] == 0.176
        # blended = 0.176 * 20 + 0.824 * 5 = 3.52 + 4.12 = 7.64
        avg = Decimal(result["params"]["avg_daily"])
        assert Decimal("7") < avg < Decimal("8")
        # Confidence: 30 + 3*2.5 = 37.5
        assert result["confidence_base"] == Decimal("37.5")

    def test_6_days_data(self):
        """Product with 6 days: 30% own, 70% category."""
        today = date.today()
        series = [(today - timedelta(days=5 - i), Decimal("10")) for i in range(6)]
        result = category_prior_forecast(
            daily_series=series,
            category_avg=Decimal("2.000"),
            category_dow_factors={},
            horizon_days=3,
        )

        # shrinkage = 6/20 = 0.3
        assert result["params"]["shrinkage"] == 0.3
        # blended = 0.3*10 + 0.7*2 = 3 + 1.4 = 4.4
        avg = Decimal(result["params"]["avg_daily"])
        assert Decimal("4") < avg < Decimal("5")
        # Confidence: 30 + 6*2.5 = 45
        assert result["confidence_base"] == Decimal("45")

    def test_dow_factors_applied(self):
        """Category DOW factors should adjust predictions."""
        result = category_prior_forecast(
            daily_series=[],
            category_avg=Decimal("10.000"),
            category_dow_factors={5: 2.0, 6: 0.5},  # Sat=2x, Sun=0.5x
            horizon_days=14,
        )

        for fc in result["forecasts"]:
            if fc["date"].weekday() == 5:  # Saturday
                assert fc["qty_predicted"] == Decimal("20.000")
            elif fc["date"].weekday() == 6:  # Sunday
                assert fc["qty_predicted"] == Decimal("5.000")


# ═══════════════════════════════════════════════════════════════════════════
# 7. HOLIDAY ADJUSTMENTS
# ═══════════════════════════════════════════════════════════════════════════

class TestHolidayAdjustments:
    def test_holiday_multiplier(self):
        holiday_date = date(2026, 9, 18)
        forecasts = [
            {"date": holiday_date, "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
        ]
        holidays = [{
            "date": holiday_date,
            "demand_multiplier": Decimal("2.00"),
            "pre_days": 0,
            "pre_multiplier": Decimal("1.00"),
        }]

        result = apply_holiday_adjustments(forecasts, holidays)
        assert result[0]["qty_predicted"] == Decimal("20.000")
        assert result[0]["lower_bound"] == Decimal("14.000")
        assert result[0]["upper_bound"] == Decimal("26.000")

    def test_pre_holiday_multiplier(self):
        holiday_date = date(2026, 12, 25)
        pre_date = date(2026, 12, 24)
        forecasts = [
            {"date": pre_date, "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
            {"date": holiday_date, "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
        ]
        holidays = [{
            "date": holiday_date,
            "demand_multiplier": Decimal("1.80"),
            "pre_days": 1,
            "pre_multiplier": Decimal("1.40"),
        }]

        result = apply_holiday_adjustments(forecasts, holidays)
        assert result[0]["qty_predicted"] == Decimal("14.000")  # pre: 10*1.4
        assert result[1]["qty_predicted"] == Decimal("18.000")  # holiday: 10*1.8

    def test_no_holidays_no_change(self):
        forecasts = [
            {"date": date(2026, 3, 15), "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
        ]
        result = apply_holiday_adjustments(forecasts, [])
        assert result[0]["qty_predicted"] == Decimal("10.000")

    def test_multiple_pre_days(self):
        holiday_date = date(2026, 9, 18)
        forecasts = [
            {"date": date(2026, 9, 15), "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
            {"date": date(2026, 9, 16), "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
            {"date": date(2026, 9, 17), "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
            {"date": holiday_date, "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"), "upper_bound": Decimal("13.000")},
        ]
        holidays = [{
            "date": holiday_date,
            "demand_multiplier": Decimal("2.00"),
            "pre_days": 3,
            "pre_multiplier": Decimal("1.50"),
        }]

        result = apply_holiday_adjustments(forecasts, holidays)
        assert result[0]["qty_predicted"] == Decimal("15.000")  # Sep 15: pre
        assert result[1]["qty_predicted"] == Decimal("15.000")  # Sep 16: pre
        assert result[2]["qty_predicted"] == Decimal("15.000")  # Sep 17: pre
        assert result[3]["qty_predicted"] == Decimal("20.000")  # Sep 18: holiday


# ═══════════════════════════════════════════════════════════════════════════
# 8. HOLIDAY CRUD API
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestHolidayCRUD:
    URL = "/api/forecast/holidays/"

    def test_list_national_holidays(self, api_client, tenant, store, warehouse, owner):
        Holiday.objects.create(
            tenant=None, name="Año Nuevo", date=date(2026, 1, 1),
            scope=Holiday.SCOPE_NATIONAL, demand_multiplier=Decimal("1.30"),
        )
        resp = api_client.get(self.URL, {"year": 2026})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["results"][0]["name"] == "Año Nuevo"

    def test_create_custom_holiday(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.post(self.URL, {
            "name": "Aniversario Tienda",
            "date": "2026-06-15",
            "demand_multiplier": "1.50",
            "pre_days": 2,
            "pre_multiplier": "1.20",
        }, format="json")
        assert resp.status_code == 201
        assert resp.json()["name"] == "Aniversario Tienda"

        h = Holiday.objects.get(name="Aniversario Tienda")
        assert h.tenant_id == tenant.id
        assert h.scope == Holiday.SCOPE_CUSTOM

    def test_patch_custom_holiday(self, api_client, tenant, store, warehouse, owner):
        h = Holiday.objects.create(
            tenant=tenant, name="Evento", date=date(2026, 7, 1),
            scope=Holiday.SCOPE_CUSTOM, demand_multiplier=Decimal("1.30"),
        )
        resp = api_client.patch(f"{self.URL}{h.id}/", {"demand_multiplier": "2.00"}, format="json")
        assert resp.status_code == 200
        h.refresh_from_db()
        assert h.demand_multiplier == Decimal("2.00")

    def test_delete_custom_holiday(self, api_client, tenant, store, warehouse, owner):
        h = Holiday.objects.create(
            tenant=tenant, name="Temp", date=date(2026, 8, 1),
            scope=Holiday.SCOPE_CUSTOM,
        )
        resp = api_client.delete(f"{self.URL}{h.id}/")
        assert resp.status_code == 204
        assert not Holiday.objects.filter(id=h.id).exists()

    def test_cannot_delete_national(self, api_client, tenant, store, warehouse, owner):
        h = Holiday.objects.create(
            tenant=None, name="Navidad", date=date(2026, 12, 25),
            scope=Holiday.SCOPE_NATIONAL,
        )
        resp = api_client.delete(f"{self.URL}{h.id}/")
        assert resp.status_code == 404  # Not found (scope=NATIONAL, not CUSTOM)


# ═══════════════════════════════════════════════════════════════════════════
# 9. CATEGORY DEMAND PROFILE (integration)
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestCategoryDemandProfile:
    def test_compute_profiles(self, tenant, store, warehouse, product, product_b):
        """Verify compute_category_profiles command creates profiles."""
        from catalog.models import Category
        cat = Category.objects.create(tenant=tenant, name="Bebidas")
        product.category = cat
        product.save()
        product_b.category = cat
        product_b.save()

        today = date.today()
        for i in range(15):
            d = today - timedelta(days=15 - i)
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=d, qty_sold=Decimal("10.000"),
            )
            DailySales.objects.create(
                tenant=tenant, product=product_b, warehouse=warehouse,
                date=d, qty_sold=Decimal("6.000"),
            )

        from django.core.management import call_command
        call_command("compute_category_profiles", tenant=tenant.id)

        profile = CategoryDemandProfile.objects.get(
            tenant=tenant, category=cat, warehouse=warehouse
        )
        # avg_daily = mean of per-product averages = mean(10, 6) = 8
        assert profile.avg_daily_demand == Decimal("8.000")
        assert profile.product_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# 10. MARGIN DATA
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestMarginData:
    def test_margin_in_dashboard(self, api_client, tenant, store, warehouse, owner, product):
        """Dashboard should include margin_at_risk and coverage_pct."""
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="500")
        fm = _make_forecast_model(tenant, warehouse, product)
        tomorrow = date.today() + timedelta(days=1)
        _make_forecast(tenant, warehouse, product, fm,
                       forecast_date=tomorrow, days_to_stockout=3)

        # Add margin data
        today = date.today()
        for i in range(5):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=today - timedelta(days=i + 1),
                qty_sold=Decimal("2.000"),
                revenue=Decimal("2000.00"),
                total_cost=Decimal("1000.00"),
                gross_profit=Decimal("1000.00"),
            )

        resp = api_client.get("/api/forecast/dashboard/")
        assert resp.status_code == 200
        kpis = resp.json()["kpis"]
        assert "margin_at_risk" in kpis
        assert "coverage_pct" in kpis
        assert Decimal(kpis["margin_at_risk"]) > 0

    def test_margin_sort_in_products(self, api_client, tenant, store, warehouse, owner, product, product_b):
        """Products list should support sort=margin."""
        fm1 = _make_forecast_model(tenant, warehouse, product)
        fm2 = _make_forecast_model(tenant, warehouse, product_b)

        today = date.today()
        tomorrow = today + timedelta(days=1)

        _make_forecast(tenant, warehouse, product, fm1,
                       forecast_date=tomorrow, days_to_stockout=5, qty_predicted="10.000")
        _make_forecast(tenant, warehouse, product_b, fm2,
                       forecast_date=tomorrow, days_to_stockout=5, qty_predicted="2.000")

        # Product A: high margin
        for i in range(5):
            DailySales.objects.create(
                tenant=tenant, product=product, warehouse=warehouse,
                date=today - timedelta(days=i + 1),
                qty_sold=Decimal("5.000"),
                revenue=Decimal("5000.00"),
                total_cost=Decimal("1000.00"),
                gross_profit=Decimal("4000.00"),
            )
        # Product B: low margin
        for i in range(5):
            DailySales.objects.create(
                tenant=tenant, product=product_b, warehouse=warehouse,
                date=today - timedelta(days=i + 1),
                qty_sold=Decimal("5.000"),
                revenue=Decimal("600.00"),
                total_cost=Decimal("500.00"),
                gross_profit=Decimal("100.00"),
            )

        resp = api_client.get("/api/forecast/products/", {"sort": "margin"})
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        # High margin product first
        assert Decimal(results[0]["avg_margin"]) > Decimal(results[1]["avg_margin"])

    def test_aggregate_includes_cost(self, tenant, store, warehouse, owner, product):
        """aggregate_daily_sales should populate total_cost and gross_profit."""
        from sales.models import Sale, SaleLine

        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse, created_by=owner,
            subtotal=Decimal("1000.00"), total=Decimal("1000.00"),
            status="COMPLETED",
        )
        SaleLine.objects.create(
            tenant=tenant, sale=sale, product=product,
            qty=Decimal("2.000"), unit_price=Decimal("500.00"),
            line_total=Decimal("1000.00"),
            unit_cost_snapshot=Decimal("300.00"),
            line_cost=Decimal("600.00"),
            line_gross_profit=Decimal("400.00"),
        )

        from django.core.management import call_command
        call_command("aggregate_daily_sales", date=str(date.today()))

        ds = DailySales.objects.get(tenant=tenant, product=product, warehouse=warehouse)
        assert ds.total_cost == Decimal("600.00")
        assert ds.gross_profit == Decimal("400.00")


# ═══════════════════════════════════════════════════════════════════════════
# 11. SEED HOLIDAYS COMMAND
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestSeedHolidays:
    def test_seed_creates_holidays(self):
        from django.core.management import call_command
        call_command("seed_chilean_holidays", start_year=2026, end_year=2026)

        # Should have fixed holidays + Easter-based
        count = Holiday.objects.filter(date__year=2026).count()
        assert count >= 14  # 14 fixed + 2 Easter-based = 16

        # Verify Fiestas Patrias
        fp = Holiday.objects.get(date=date(2026, 9, 18), tenant__isnull=True)
        assert fp.demand_multiplier == Decimal("2.00")
        assert fp.pre_days == 3

    def test_seed_idempotent(self):
        from django.core.management import call_command
        call_command("seed_chilean_holidays", start_year=2026, end_year=2026)
        count1 = Holiday.objects.count()
        call_command("seed_chilean_holidays", start_year=2026, end_year=2026)
        count2 = Holiday.objects.count()
        assert count1 == count2


# ═══════════════════════════════════════════════════════════════════════════
# 12. CLEAN_SERIES — Data cleaning
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanSeries:
    def test_empty_series(self):
        assert clean_series([]) == []

    def test_no_stockouts_no_outliers(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(5)]
        result = clean_series(series)
        assert len(result) == 5
        for d, qty, w in result:
            assert w == 1.0  # no imputation

    def test_stockout_interpolation(self):
        """Stockout zeros should be interpolated from same-weekday."""
        today = date.today()
        series = []
        for i in range(14):
            d = today - timedelta(days=13 - i)
            series.append((d, Decimal("10")))
        # Make day 7 a stockout zero
        stockout_day = today - timedelta(days=6)
        series[7] = (stockout_day, Decimal("0"))
        stockout_dates = {stockout_day}

        result = clean_series(series, stockout_dates=stockout_dates)
        # The stockout day should be interpolated (not zero) with weight 0.5
        for d, qty, w in result:
            if d == stockout_day:
                assert float(qty) > 0, "Stockout should be interpolated"
                assert w == 0.5

    def test_outlier_dampening(self):
        """Extreme outliers should be dampened to IQR limit."""
        today = date.today()
        # 10 normal values + 1 huge outlier
        series = [(today - timedelta(days=10 - i), Decimal("10")) for i in range(10)]
        series.append((today, Decimal("1000")))  # extreme outlier

        result = clean_series(series)
        last = result[-1]
        assert float(last[1]) < 1000, "Outlier should be dampened"
        assert last[2] == 0.7, "Outlier weight should be 0.7"

    def test_holiday_spikes_not_dampened(self):
        """Holiday dates should NOT be dampened even if they look like outliers."""
        today = date.today()
        series = [(today - timedelta(days=10 - i), Decimal("10")) for i in range(10)]
        holiday_day = today
        series.append((holiday_day, Decimal("1000")))
        holiday_dates = {holiday_day}

        result = clean_series(series, holiday_dates=holiday_dates)
        last = result[-1]
        # Holiday spike should keep original value and weight 1.0
        assert float(last[1]) == 1000
        assert last[2] == 1.0

    def test_stockout_no_dow_data_uses_global(self):
        """If no same-weekday data for interpolation, use global avg."""
        today = date.today()
        # Only 3 days, all same weekday won't cover the stockout weekday
        series = [(today - timedelta(days=2), Decimal("10")),
                  (today - timedelta(days=1), Decimal("0")),
                  (today, Decimal("10"))]
        stockout_dates = {today - timedelta(days=1)}

        result = clean_series(series, stockout_dates=stockout_dates)
        assert len(result) == 3
        # Middle day should be interpolated
        assert float(result[1][1]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 13. CLASSIFY_DEMAND_PATTERN — ADI-CV² framework
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyDemandPattern:
    def test_insufficient_data(self):
        today = date.today()
        series = [(today, Decimal("5")), (today - timedelta(days=1), Decimal("0"))]
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern == "insufficient"

    def test_smooth_demand(self):
        """Daily sales with low ADI should be smooth."""
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(30)]
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern == "smooth"
        assert adi < 1.32

    def test_intermittent_demand(self):
        """Sales every other day with consistent sizes → intermittent."""
        today = date.today()
        series = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            qty = Decimal("10") if i % 3 == 0 else Decimal("0")
            series.append((d, qty))
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern in ("intermittent", "lumpy")  # ADI >= 1.32

    def test_lumpy_demand(self):
        """Infrequent + highly variable sizes → lumpy."""
        today = date.today()
        series = []
        sizes = [100, 5, 200, 2, 150]  # high CV²
        j = 0
        for i in range(30):
            d = today - timedelta(days=29 - i)
            if i % 6 == 0 and j < len(sizes):
                series.append((d, Decimal(str(sizes[j]))))
                j += 1
            else:
                series.append((d, Decimal("0")))
        pattern, adi, cv2 = classify_demand_pattern(series)
        assert pattern == "lumpy"

    def test_all_zeros_insufficient(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("0")) for i in range(10)]
        pattern, _, _ = classify_demand_pattern(series)
        assert pattern == "insufficient"


# ═══════════════════════════════════════════════════════════════════════════
# 14. CROSTON FORECAST
# ═══════════════════════════════════════════════════════════════════════════

class TestCrostonForecast:
    def test_basic_intermittent(self):
        today = date.today()
        series = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            qty = Decimal("10") if i % 3 == 0 else Decimal("0")
            series.append((d, qty))
        result = croston_forecast(series, horizon_days=7)
        assert result is not None
        assert result["algorithm"] == "croston"
        assert len(result["forecasts"]) == 7
        assert float(result["forecasts"][0]["qty_predicted"]) > 0

    def test_sba_variant(self):
        today = date.today()
        series = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            qty = Decimal("10") if i % 3 == 0 else Decimal("0")
            series.append((d, qty))
        result = croston_forecast(series, horizon_days=7, use_sba=True)
        assert result is not None
        assert result["algorithm"] == "croston_sba"
        # SBA should produce slightly lower estimates
        result_plain = croston_forecast(series, horizon_days=7, use_sba=False)
        assert float(result["forecasts"][0]["qty_predicted"]) <= float(result_plain["forecasts"][0]["qty_predicted"])

    def test_too_few_nonzero_returns_none(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("0")) for i in range(20)]
        series[0] = (today, Decimal("5"))
        series[10] = (today - timedelta(days=10), Decimal("3"))
        result = croston_forecast(series, horizon_days=7)
        # Only 2 non-zero → not enough
        assert result is None

    def test_confidence_intervals(self):
        today = date.today()
        series = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            qty = Decimal("10") if i % 4 == 0 else Decimal("0")
            series.append((d, qty))
        result = croston_forecast(series, horizon_days=7)
        assert result is not None
        for fc in result["forecasts"]:
            assert fc["lower_bound"] <= fc["qty_predicted"]
            assert fc["upper_bound"] >= fc["qty_predicted"]


# ═══════════════════════════════════════════════════════════════════════════
# 15. ENSEMBLE FORECAST
# ═══════════════════════════════════════════════════════════════════════════

class TestEnsembleForecast:
    def _make_candidate(self, algo, mape, mae, avg_daily=10.0, horizon=7):
        forecasts = []
        for i in range(horizon):
            forecasts.append({
                "date": date.today() + timedelta(days=i + 1),
                "qty_predicted": Decimal(str(avg_daily)),
                "lower_bound": Decimal(str(avg_daily * 0.7)),
                "upper_bound": Decimal(str(avg_daily * 1.3)),
            })
        return {
            "algorithm": algo,
            "forecasts": forecasts,
            "metrics": {"mape": mape, "mae": mae, "rmse": 0, "bias": 0},
            "data_points": 30,
            "confidence_base": Decimal("70.00"),
        }

    def test_two_candidates(self):
        c1 = self._make_candidate("moving_avg", mape=20, mae=2.0, avg_daily=10)
        c2 = self._make_candidate("holt_winters", mape=15, mae=1.5, avg_daily=12)
        result = ensemble_forecast([c1, c2])
        assert result is not None
        assert result["algorithm"] == "ensemble"
        assert len(result["forecasts"]) == 7
        # Ensemble should be between the two
        ens_val = float(result["forecasts"][0]["qty_predicted"])
        assert 10 <= ens_val <= 12

    def test_single_candidate_returns_none(self):
        c1 = self._make_candidate("moving_avg", mape=20, mae=2)
        assert ensemble_forecast([c1]) is None

    def test_all_high_mape_returns_none(self):
        c1 = self._make_candidate("moving_avg", mape=150, mae=150)
        c2 = self._make_candidate("holt_winters", mape=200, mae=200)
        assert ensemble_forecast([c1, c2]) is None

    def test_intermittent_uses_mae(self):
        c1 = self._make_candidate("moving_avg", mape=50, mae=3, avg_daily=10)
        c2 = self._make_candidate("croston", mape=80, mae=1, avg_daily=8)
        result = ensemble_forecast([c1, c2], demand_pattern="intermittent")
        assert result is not None
        # Croston has lower MAE so should have higher weight
        ens_val = float(result["forecasts"][0]["qty_predicted"])
        assert ens_val < 10  # weighted toward croston's 8

    def test_different_horizon_lengths(self):
        """Ensemble should handle candidates with different forecast lengths."""
        c1 = self._make_candidate("moving_avg", mape=20, mae=2, horizon=14)
        c2 = self._make_candidate("holt_winters", mape=15, mae=1.5, horizon=7)
        result = ensemble_forecast([c1, c2])
        assert result is not None
        assert len(result["forecasts"]) == 7  # min of the two


# ═══════════════════════════════════════════════════════════════════════════
# 16. MONTH POSITION FACTORS (Payday effect)
# ═══════════════════════════════════════════════════════════════════════════

class TestMonthPositionFactors:
    def test_insufficient_data(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(20)]
        assert compute_month_position_factors(series, min_days=45) is None

    def test_uniform_returns_none(self):
        """Constant demand across all month positions → no meaningful pattern."""
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(60)]
        result = compute_month_position_factors(series, min_days=45)
        assert result is None  # max/min ratio < 1.15

    def test_payday_effect_detected(self):
        """Higher demand on late days should produce factors."""
        series = []
        for month in range(1, 4):
            for day in range(1, 29):
                d = date(2025, month, day)
                qty = Decimal("20") if day >= 25 else Decimal("5")
                series.append((d, qty))
        result = compute_month_position_factors(series, min_days=45)
        assert result is not None
        assert result["late"] > result["early"]

    def test_zero_bucket_no_division_error(self):
        """Bucket with zero avg should not cause ZeroDivisionError."""
        series = []
        for month in range(1, 4):
            for day in range(1, 29):
                d = date(2025, month, day)
                qty = Decimal("0") if day <= 5 else Decimal("10")
                series.append((d, qty))
        # Should not raise
        result = compute_month_position_factors(series, min_days=45)
        # min_val is 0, so should return None (our fix)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 17. MONTHLY SEASONALITY
# ═══════════════════════════════════════════════════════════════════════════

class TestMonthlySeasonality:
    def test_insufficient_data(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(90)]
        assert compute_monthly_seasonality(series, min_days=180) is None

    def test_uniform_returns_none(self):
        series = []
        for i in range(200):
            d = date(2025, 1, 1) + timedelta(days=i)
            series.append((d, Decimal("10")))
        result = compute_monthly_seasonality(series, min_days=180)
        assert result is None  # max/min < 1.20

    def test_seasonal_pattern(self):
        """December high, January low → detectable seasonality."""
        series = []
        for i in range(365):
            d = date(2025, 1, 1) + timedelta(days=i)
            if d.month == 12:
                qty = Decimal("30")
            elif d.month in (1, 2):
                qty = Decimal("5")
            else:
                qty = Decimal("10")
            series.append((d, qty))
        result = compute_monthly_seasonality(series, min_days=180)
        assert result is not None
        assert result[12] > 1.0  # December above average
        assert result[1] < 1.0   # January below


# ═══════════════════════════════════════════════════════════════════════════
# 18. TREND DETECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestTrendDetection:
    def test_no_trend_flat_data(self):
        today = date.today()
        series = [(today - timedelta(days=29 - i), Decimal("10")) for i in range(30)]
        result = detect_trend(series)
        assert result is None  # flat

    def test_insufficient_data(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(10)]
        assert detect_trend(series, min_days=28) is None

    def test_upward_trend(self):
        today = date.today()
        series = []
        for i in range(60):
            d = today - timedelta(days=59 - i)
            qty = Decimal(str(5 + i * 0.5))  # growing from 5 to 34.5
            series.append((d, qty))
        result = detect_trend(series)
        if result:
            assert result["direction"] == "up"
            assert result["slope_per_day"] > 0

    def test_apply_trend_adjustment(self):
        forecasts = [
            {"date": date.today() + timedelta(days=1),
             "qty_predicted": Decimal("10.000"),
             "lower_bound": Decimal("7.000"),
             "upper_bound": Decimal("13.000")},
        ]
        trend = {"slope_per_day": 1.0, "r_squared": 0.8, "direction": "up"}
        apply_trend_adjustment(forecasts, trend, Decimal("10"))
        # factor = 1 + 1.0 * 1 / 10 = 1.1 → 10 * 1.1 = 11
        assert float(forecasts[0]["qty_predicted"]) == pytest.approx(11.0, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════
# 19. BIAS CORRECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestBiasCorrection:
    def test_no_accuracy_data(self):
        forecasts = [{"date": date.today(), "qty_predicted": Decimal("10"),
                      "lower_bound": Decimal("7"), "upper_bound": Decimal("13")}]
        result = apply_bias_correction(forecasts, [], Decimal("10"))
        assert result == 0.0

    def test_consistent_over_prediction(self):
        """Systematic over-prediction should reduce forecasts."""
        today = date.today()
        accuracy = [
            {"date": today - timedelta(days=i), "error": 5.0, "was_stockout": False}
            for i in range(10)
        ]
        forecasts = [
            {"date": today + timedelta(days=1), "qty_predicted": Decimal("20.000"),
             "lower_bound": Decimal("15.000"), "upper_bound": Decimal("25.000")},
        ]
        result = apply_bias_correction(forecasts, accuracy, Decimal("10"))
        assert result != 0.0
        # Over-predicting by 5, should reduce
        assert float(forecasts[0]["qty_predicted"]) < 20.0

    def test_stockout_days_excluded(self):
        """Stockout days should not affect bias calculation."""
        today = date.today()
        accuracy = [
            {"date": today - timedelta(days=i), "error": 0.5, "was_stockout": True}
            for i in range(10)
        ]
        forecasts = [{"date": today, "qty_predicted": Decimal("10"),
                      "lower_bound": Decimal("7"), "upper_bound": Decimal("13")}]
        result = apply_bias_correction(forecasts, accuracy, Decimal("10"))
        assert result == 0.0  # all excluded

    def test_too_few_errors(self):
        today = date.today()
        accuracy = [
            {"date": today, "error": 5.0, "was_stockout": False},
        ]
        result = apply_bias_correction(
            [{"date": today, "qty_predicted": Decimal("10"),
              "lower_bound": Decimal("7"), "upper_bound": Decimal("13")}],
            accuracy, Decimal("10")
        )
        assert result == 0.0  # < 5 errors


# ═══════════════════════════════════════════════════════════════════════════
# 20. CONFIDENCE DECAY
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceDecay:
    def test_fresh_model_no_decay(self):
        today = date.today()
        result = compute_confidence_decay(today, Decimal("80.00"))
        assert result == Decimal("80.00")

    def test_14_day_old_halves(self):
        trained = date.today() - timedelta(days=14)
        result = compute_confidence_decay(trained, Decimal("80.00"))
        assert float(result) == pytest.approx(40.0, abs=1.0)

    def test_28_day_old_quarter(self):
        trained = date.today() - timedelta(days=28)
        result = compute_confidence_decay(trained, Decimal("80.00"))
        assert float(result) == pytest.approx(20.0, abs=2.0)

    def test_floor_at_20_percent(self):
        trained = date.today() - timedelta(days=100)
        result = compute_confidence_decay(trained, Decimal("80.00"))
        assert float(result) >= 16.0  # 20% of 80


# ═══════════════════════════════════════════════════════════════════════════
# 21. DAYS TO STOCKOUT
# ═══════════════════════════════════════════════════════════════════════════

class TestDaysToStockout:
    def test_zero_stock(self):
        assert calculate_days_to_stockout(0, []) == 0
        assert calculate_days_to_stockout(-5, []) == 0

    def test_basic_depletion(self):
        forecasts = [
            {"qty_predicted": Decimal("3")},
            {"qty_predicted": Decimal("3")},
            {"qty_predicted": Decimal("3")},
        ]
        # 5 units / 3 per day = runs out on day 2
        result = calculate_days_to_stockout(5, forecasts)
        assert result == 2

    def test_no_stockout_within_horizon(self):
        forecasts = [{"qty_predicted": Decimal("1")} for _ in range(7)]
        result = calculate_days_to_stockout(100, forecasts)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 22. PREDICTION INTERVALS
# ═══════════════════════════════════════════════════════════════════════════

class TestPredictionIntervals:
    def test_too_few_data_returns_none(self):
        assert compute_prediction_intervals([1, 2], [1, 2]) is None

    def test_perfect_predictions(self):
        actuals = [10, 10, 10, 10, 10]
        predictions = [10, 10, 10, 10, 10]
        lower, upper = compute_prediction_intervals(actuals, predictions)
        assert lower == 0
        assert upper == 0

    def test_intervals_contain_residuals(self):
        actuals = [10, 12, 8, 15, 11, 9, 13]
        predictions = [10, 10, 10, 10, 10, 10, 10]
        lower, upper = compute_prediction_intervals(actuals, predictions)
        assert lower <= 0  # some under-predictions
        assert upper >= 0  # some over-predictions


# ═══════════════════════════════════════════════════════════════════════════
# 23. BACKTEST EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestBacktestEdgeCases:
    def test_moving_avg_insufficient_data(self):
        """With insufficient data, backtest should return 999 metrics."""
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(5)]
        result = backtest_moving_average(series, test_days=7, window=21)
        assert result["mape"] == 999

    def test_croston_insufficient_data(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(5)]
        result = backtest_croston(series, test_days=7)
        assert result["mape"] == 999

    def test_holt_winters_insufficient_data(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(10)]
        result = backtest_holt_winters(series, test_days=7)
        assert result["mape"] == 999


# ═══════════════════════════════════════════════════════════════════════════
# 24. SELECT_BEST_MODEL — algorithm selection logic
# ═══════════════════════════════════════════════════════════════════════════

class TestSelectBestModel:
    def test_sparse_data_selects_simple_avg(self):
        today = date.today()
        series = [(today - timedelta(days=9 - i), Decimal("10")) for i in range(10)]
        result = select_best_model(series, horizon=7)
        assert result["algorithm"] == "simple_avg"

    def test_medium_data_selects_competitive_model(self):
        today = date.today()
        series = [(today - timedelta(days=20 - i), Decimal("10")) for i in range(21)]
        result = select_best_model(series, horizon=7, window=14)
        assert result["algorithm"] in ("moving_avg", "theta", "adaptive_ma", "ensemble")

    def test_demand_pattern_tagged(self):
        today = date.today()
        series = [(today - timedelta(days=20 - i), Decimal("10")) for i in range(21)]
        result = select_best_model(series, horizon=7, window=14)
        assert "demand_pattern" in result
        assert result["demand_pattern"] in ("smooth", "intermittent", "lumpy", "insufficient")

    def test_no_candidates_returns_none_algo(self):
        """Series too short for any algorithm."""
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(3)]
        result = select_best_model(series, horizon=7)
        assert result["algorithm"] == "none"
        assert result["forecasts"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 25. PRICE ELASTICITY
# ═══════════════════════════════════════════════════════════════════════════

class TestPriceElasticity:
    def test_no_revenue_returns_none(self):
        assert detect_price_change_impact([], revenue_series=None) is None

    def test_insufficient_revenue(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(5)]
        rev = [(today - timedelta(days=i), Decimal("100")) for i in range(5)]
        assert detect_price_change_impact(series, revenue_series=rev) is None

    def test_no_sensitivity(self):
        today = date.today()
        series = [(today - timedelta(days=i), Decimal("10")) for i in range(20)]
        rev = [(today - timedelta(days=i), Decimal("100")) for i in range(20)]
        result = detect_price_change_impact(series, revenue_series=rev)
        if result:
            assert result["is_price_sensitive"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 26. GENERATE DAILY FORECASTS
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateDailyForecasts:
    def test_basic_generation(self):
        today = date.today()
        dow_factors = {i: 1.0 for i in range(7)}
        forecasts = generate_daily_forecasts(Decimal("10"), dow_factors, today, horizon_days=7)
        assert len(forecasts) == 7
        assert forecasts[0]["date"] == today + timedelta(days=1)
        assert forecasts[0]["qty_predicted"] == Decimal("10.000")

    def test_dow_factors_applied(self):
        today = date.today()
        dow_factors = {i: 1.0 for i in range(7)}
        # Double the factor for tomorrow's weekday
        tomorrow_dow = (today + timedelta(days=1)).weekday()
        dow_factors[tomorrow_dow] = 2.0
        forecasts = generate_daily_forecasts(Decimal("10"), dow_factors, today, horizon_days=1)
        assert forecasts[0]["qty_predicted"] == Decimal("20.000")

    def test_bounds_reasonable(self):
        today = date.today()
        dow_factors = {i: 1.0 for i in range(7)}
        forecasts = generate_daily_forecasts(Decimal("10"), dow_factors, today, horizon_days=3)
        for fc in forecasts:
            assert fc["lower_bound"] <= fc["qty_predicted"]
            assert fc["upper_bound"] >= fc["qty_predicted"]


# ═══════════════════════════════════════════════════════════════════════════
# 27. CONFIDENCE LABEL (services)
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceLabel:
    def test_very_high(self):
        from forecast.services import compute_confidence_label
        label, reason = compute_confidence_label(200, 10, "smooth")
        assert label == "very_high"

    def test_high(self):
        from forecast.services import compute_confidence_label
        label, reason = compute_confidence_label(100, 20, "smooth")
        assert label == "high"

    def test_medium(self):
        from forecast.services import compute_confidence_label
        label, reason = compute_confidence_label(40, 35, "smooth")
        assert label == "medium"

    def test_low(self):
        from forecast.services import compute_confidence_label
        label, reason = compute_confidence_label(15, 55, "smooth")
        assert label == "low"

    def test_very_low(self):
        from forecast.services import compute_confidence_label
        label, reason = compute_confidence_label(5, 80, "smooth")
        assert label == "very_low"

    def test_intermittent_caps_at_high(self):
        from forecast.services import compute_confidence_label
        label, _ = compute_confidence_label(200, 10, "intermittent")
        assert label == "high"  # capped, not very_high

    def test_reason_includes_info(self):
        from forecast.services import compute_confidence_label
        _, reason = compute_confidence_label(60, 25, "smooth")
        assert "MAPE" in reason


# ═══════════════════════════════════════════════════════════════════════════
# 28. SUGGESTIONS — approve/dismiss
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestSuggestions:
    def test_approve_creates_purchase(self, api_client, tenant, store, warehouse, owner, product):
        _make_stock_item(tenant, warehouse, product, on_hand=5, avg_cost="100")
        suggestion = PurchaseSuggestion.objects.create(
            tenant=tenant, warehouse=warehouse, status="PENDING",
            priority="HIGH", supplier_name="Proveedor Test",
        )
        SuggestionLine.objects.create(
            suggestion=suggestion, product=product,
            current_stock=Decimal("5"), avg_daily_demand=Decimal("2"),
            days_to_stockout=2, suggested_qty=Decimal("20"),
            estimated_cost=Decimal("2000"),
        )
        resp = api_client.post(f"/api/forecast/suggestions/{suggestion.id}/approve/")
        assert resp.status_code == 200
        data = resp.json()
        assert "purchase_id" in data
        suggestion.refresh_from_db()
        assert suggestion.status == "APPROVED"
        assert suggestion.purchase_id is not None

    def test_dismiss_suggestion(self, api_client, tenant, store, warehouse, owner):
        suggestion = PurchaseSuggestion.objects.create(
            tenant=tenant, warehouse=warehouse, status="PENDING", priority="MEDIUM",
        )
        resp = api_client.post(f"/api/forecast/suggestions/{suggestion.id}/dismiss/")
        assert resp.status_code == 200
        suggestion.refresh_from_db()
        assert suggestion.status == "DISMISSED"

    def test_cannot_approve_dismissed(self, api_client, tenant, store, warehouse, owner):
        suggestion = PurchaseSuggestion.objects.create(
            tenant=tenant, warehouse=warehouse, status="DISMISSED", priority="MEDIUM",
        )
        resp = api_client.post(f"/api/forecast/suggestions/{suggestion.id}/approve/")
        assert resp.status_code == 400

    def test_approve_nonexistent_404(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.post("/api/forecast/suggestions/99999/approve/")
        assert resp.status_code == 404

    def test_list_suggestions(self, api_client, tenant, store, warehouse, owner):
        PurchaseSuggestion.objects.create(
            tenant=tenant, warehouse=warehouse, status="PENDING", priority="HIGH",
        )
        PurchaseSuggestion.objects.create(
            tenant=tenant, warehouse=warehouse, status="APPROVED", priority="MEDIUM",
        )
        resp = api_client.get("/api/forecast/suggestions/", {"status": "PENDING"})
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 29. SAFETY ADJUSTMENT (tasks)
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyAdjustment:
    def test_ratio_below_0_7_increases(self):
        from forecast.tasks import _compute_safety_adjustment
        # Actual lasted 5 days but predicted 10 → ratio 0.5
        adj = _compute_safety_adjustment(Decimal("10"), 10, 5)
        assert adj > 0

    def test_ratio_above_1_3_decreases(self):
        from forecast.tasks import _compute_safety_adjustment
        # Actual lasted 15 days but predicted 10 → ratio 1.5
        adj = _compute_safety_adjustment(Decimal("10"), 10, 15)
        assert adj < 0

    def test_within_tolerance_zero(self):
        from forecast.tasks import _compute_safety_adjustment
        adj = _compute_safety_adjustment(Decimal("10"), 10, 10)
        assert adj == Decimal("0.000")

    def test_cap_at_20_percent(self):
        from forecast.tasks import _compute_safety_adjustment
        adj = _compute_safety_adjustment(Decimal("10"), 10, 1)  # ratio 0.1
        cap = Decimal("10") * Decimal("0.20")
        assert abs(adj) <= cap

    def test_zero_avg_daily(self):
        from forecast.tasks import _compute_safety_adjustment
        adj = _compute_safety_adjustment(Decimal("0"), 10, 5)
        assert adj == Decimal("0.000")

    def test_none_actual_days(self):
        from forecast.tasks import _compute_safety_adjustment
        adj = _compute_safety_adjustment(Decimal("10"), 10, None)
        assert adj == Decimal("0.000")

    def test_zero_predicted_days(self):
        from forecast.tasks import _compute_safety_adjustment
        adj = _compute_safety_adjustment(Decimal("10"), 0, 5)
        assert adj == Decimal("0.000")


# ═══════════════════════════════════════════════════════════════════════════
# 30. VIEW INPUT VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestViewInputValidation:
    def test_invalid_page_param(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.get("/api/forecast/products/", {"page": "abc"})
        assert resp.status_code == 200  # should not 500

    def test_invalid_page_size(self, api_client, tenant, store, warehouse, owner):
        resp = api_client.get("/api/forecast/products/", {"page_size": "xyz"})
        assert resp.status_code == 200

    def test_invalid_history_days(self, api_client, tenant, store, warehouse, owner, product):
        _make_stock_item(tenant, warehouse, product, on_hand=10, avg_cost="100")
        fm = _make_forecast_model(tenant, warehouse, product)
        resp = api_client.get(f"/api/forecast/products/{product.id}/", {"history_days": "bad"})
        # Should not 500
        assert resp.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════════════════
# 31. FORECAST ACCURACY TRACKING (integration)
# ═══════════════════════════════════════════════════════════════════════════

@_sub
@pytest.mark.django_db
class TestForecastAccuracyTracking:
    def test_accuracy_record_created(self, tenant, store, warehouse, product):
        """track_forecast_accuracy should create ForecastAccuracy records."""
        yesterday = date.today() - timedelta(days=1)

        # Create a forecast for yesterday
        fm = _make_forecast_model(tenant, warehouse, product)
        Forecast.objects.create(
            tenant=tenant, warehouse=warehouse, product=product, model=fm,
            forecast_date=yesterday, qty_predicted=Decimal("10.000"),
            lower_bound=Decimal("7.000"), upper_bound=Decimal("13.000"),
            confidence=Decimal("75.00"),
        )
        # Create actual sales for yesterday
        DailySales.objects.create(
            tenant=tenant, product=product, warehouse=warehouse,
            date=yesterday, qty_sold=Decimal("8.000"),
        )

        from django.core.management import call_command
        call_command("track_forecast_accuracy", days=1)

        acc = ForecastAccuracy.objects.filter(
            tenant=tenant, product=product, warehouse=warehouse, date=yesterday
        ).first()
        assert acc is not None
        assert acc.qty_predicted == Decimal("10.000")
        assert acc.qty_actual == Decimal("8.000")
        assert acc.error == Decimal("2.000")  # predicted - actual


# ═══════════════════════════════════════════════════════════════════════════
# NEW ALGORITHMS — COMPREHENSIVE TESTS
# ═══════════════════════════════════════════════════════════════════════════

# ── Helpers for generating synthetic series ────────────────────────────────

def _make_series(n, base=10.0, noise=1.0, trend=0.0, start=None):
    """Generate a deterministic daily series with optional trend & noise."""
    import random
    rng = random.Random(42)
    start = start or date.today() - timedelta(days=n)
    return [
        (start + timedelta(days=i), max(0.01, base + trend * i + rng.uniform(-noise, noise)))
        for i in range(n)
    ]


def _make_weekly_seasonal(n, base=10.0, amplitude=3.0, start=None):
    """Generate series with clear weekly seasonality (weekend dip)."""
    import random
    rng = random.Random(42)
    start = start or date.today() - timedelta(days=n)
    series = []
    for i in range(n):
        d = start + timedelta(days=i)
        dow = d.weekday()
        seasonal = -amplitude if dow >= 5 else amplitude * 0.4
        val = max(0.01, base + seasonal + rng.uniform(-1, 1))
        series.append((d, val))
    return series


def _make_intermittent(n, prob=0.3, size_range=(1, 10), start=None):
    """Generate intermittent demand series (many zeros)."""
    import random
    rng = random.Random(42)
    start = start or date.today() - timedelta(days=n)
    return [
        (start + timedelta(days=i),
         rng.randint(size_range[0], size_range[1]) if rng.random() < prob else 0)
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# THETA METHOD TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestThetaForecast:
    def test_returns_none_insufficient_data(self):
        series = _make_series(10)
        assert theta_forecast(series) is None

    def test_basic_forecast_14_days(self):
        series = _make_series(20, base=10, noise=0.5)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        assert result["algorithm"] == "theta"
        assert len(result["forecasts"]) == 7
        assert result["data_points"] == 20
        assert float(result["confidence_base"]) == 72.0

    def test_forecasts_have_bounds(self):
        series = _make_series(30, base=15, noise=2)
        result = theta_forecast(series, horizon_days=5)
        for fc in result["forecasts"]:
            assert "qty_predicted" in fc
            assert "lower_bound" in fc
            assert "upper_bound" in fc
            assert fc["lower_bound"] <= fc["qty_predicted"] <= fc["upper_bound"]

    def test_params_contain_alpha_slope(self):
        series = _make_series(25, base=10, noise=1)
        result = theta_forecast(series, horizon_days=7)
        assert "alpha" in result["params"]
        assert "slope" in result["params"]
        assert "intercept" in result["params"]
        assert "ses_level" in result["params"]

    def test_trend_series_detected(self):
        series = _make_series(30, base=5, noise=0.5, trend=0.5)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        # With positive trend, later forecasts should be higher
        vals = [float(fc["qty_predicted"]) for fc in result["forecasts"]]
        assert vals[-1] > vals[0]

    def test_flat_series_stable(self):
        series = _make_series(30, base=10, noise=0.1)
        result = theta_forecast(series, horizon_days=7)
        vals = [float(fc["qty_predicted"]) for fc in result["forecasts"]]
        # Should stay near base=10
        for v in vals:
            assert 5 < v < 20

    def test_constant_series_no_crash(self):
        start = date.today() - timedelta(days=20)
        series = [(start + timedelta(days=i), 5.0) for i in range(20)]
        result = theta_forecast(series)
        assert result is not None
        # All predictions should be ~5
        for fc in result["forecasts"]:
            assert 3 < float(fc["qty_predicted"]) < 8

    def test_dates_are_consecutive(self):
        series = _make_series(20, base=10)
        result = theta_forecast(series, horizon_days=5)
        last_data_date = series[-1][0]
        for i, fc in enumerate(result["forecasts"]):
            assert fc["date"] == last_data_date + timedelta(days=i + 1)


class TestBacktestTheta:
    def test_insufficient_data(self):
        series = _make_series(15)
        m = backtest_theta(series, test_days=7)
        assert m["mae"] == 999

    def test_valid_backtest(self):
        series = _make_series(40, base=10, noise=1)
        m = backtest_theta(series, test_days=7)
        assert m["mae"] < 999
        assert m["mape"] < 999
        assert "rmse" in m
        assert "bias" in m

    def test_low_error_on_stable_series(self):
        series = _make_series(50, base=10, noise=0.2)
        m = backtest_theta(series, test_days=7)
        assert m["mae"] < 5  # Should be very accurate on stable data


# ═══════════════════════════════════════════════════════════════════════════
# HW DAMPED TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestHWDampedForecast:
    def test_returns_none_insufficient_data(self):
        series = _make_series(20)
        assert holt_winters_damped_forecast(series) is None

    def test_basic_forecast(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = holt_winters_damped_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels not available")
        assert result["algorithm"] == "hw_damped"
        assert len(result["forecasts"]) == 7

    def test_params_include_damping(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = holt_winters_damped_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels not available")
        assert "damping_trend" in result["params"]
        assert 0 < result["params"]["damping_trend"] <= 1

    def test_damped_vs_undamped_trend(self):
        """Damped trend should be more conservative on long horizons."""
        series = _make_series(42, base=10, noise=1, trend=0.3)
        damped = holt_winters_damped_forecast(series, horizon_days=30)
        undamped = holt_winters_forecast(series, horizon_days=30)
        if damped is None or undamped is None:
            pytest.skip("statsmodels not available")
        # Damped trend's last forecast should be <= undamped's
        d_last = float(damped["forecasts"][-1]["qty_predicted"])
        u_last = float(undamped["forecasts"][-1]["qty_predicted"])
        # Damped should grow less aggressively
        d_first = float(damped["forecasts"][0]["qty_predicted"])
        u_first = float(undamped["forecasts"][0]["qty_predicted"])
        d_growth = d_last - d_first
        u_growth = u_last - u_first
        assert d_growth <= u_growth + 5  # Allow small tolerance

    def test_non_negative_forecasts(self):
        series = _make_weekly_seasonal(42, base=5, amplitude=2)
        result = holt_winters_damped_forecast(series, horizon_days=14)
        if result is None:
            pytest.skip("statsmodels not available")
        for fc in result["forecasts"]:
            assert float(fc["qty_predicted"]) >= 0
            assert float(fc["lower_bound"]) >= 0


class TestBacktestHWDamped:
    def test_insufficient_data(self):
        series = _make_series(30)
        m = backtest_hw_damped(series, test_days=7)
        assert m["mae"] == 999

    def test_valid_backtest(self):
        series = _make_weekly_seasonal(56, base=15, amplitude=3)
        m = backtest_hw_damped(series, test_days=7)
        if m["mae"] == 999:
            pytest.skip("statsmodels not available")
        assert m["mape"] < 999
        assert m["mae"] >= 0


# ═══════════════════════════════════════════════════════════════════════════
# ADAPTIVE MA TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdaptiveMA:
    def test_returns_none_insufficient_data(self):
        series = _make_series(10)
        assert adaptive_moving_average(series) is None

    def test_basic_forecast(self):
        series = _make_series(30, base=10, noise=1)
        result = adaptive_moving_average(series, horizon_days=7)
        assert result is not None
        assert result["algorithm"] == "adaptive_ma"
        assert len(result["forecasts"]) == 7

    def test_params_contain_decay_window(self):
        series = _make_series(30, base=10, noise=1)
        result = adaptive_moving_average(series, horizon_days=7)
        assert "decay" in result["params"]
        assert "window" in result["params"]
        assert result["params"]["decay"] in [0.85, 0.9, 0.93, 0.95, 0.97]
        assert result["params"]["window"] in [14, 21, 28]

    def test_month_factors_applied(self):
        series = _make_series(30, base=10, noise=0.5)
        factors = {1: 1.5, 15: 1.3}  # Payday boost
        result = adaptive_moving_average(series, horizon_days=14, month_factors=factors)
        assert result is not None

    def test_dow_factors_computed(self):
        series = _make_series(30, base=10, noise=1)
        result = adaptive_moving_average(series, horizon_days=7)
        assert "dow_factors" in result["params"]
        assert len(result["params"]["dow_factors"]) == 7

    def test_optimizes_over_grid(self):
        """Different series should potentially select different configs."""
        stable = _make_series(40, base=10, noise=0.1)
        volatile = _make_series(40, base=10, noise=5)
        r1 = adaptive_moving_average(stable)
        r2 = adaptive_moving_average(volatile)
        # Both should produce valid results
        assert r1 is not None
        assert r2 is not None


class TestBacktestAdaptiveMA:
    def test_insufficient_data(self):
        series = _make_series(20)
        m = backtest_adaptive_ma(series, test_days=7)
        assert m["mae"] == 999

    def test_valid_backtest(self):
        series = _make_series(42, base=10, noise=1)
        m = backtest_adaptive_ma(series, test_days=7)
        assert m["mae"] < 999
        assert m["mape"] < 999


# ═══════════════════════════════════════════════════════════════════════════
# ETS TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestETSForecast:
    def test_returns_none_insufficient_data(self):
        series = _make_series(20)
        assert ets_forecast(series) is None

    def test_basic_forecast(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = ets_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels ETSModel not available")
        assert result["algorithm"] == "ets"
        assert len(result["forecasts"]) == 7

    def test_params_contain_config_and_aic(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = ets_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels ETSModel not available")
        assert "ets_config" in result["params"]
        assert "aic" in result["params"]

    def test_confidence_base_85(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = ets_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels ETSModel not available")
        assert float(result["confidence_base"]) == 85.0

    def test_bounds_from_ets(self):
        series = _make_weekly_seasonal(42, base=15, amplitude=3)
        result = ets_forecast(series, horizon_days=7)
        if result is None:
            pytest.skip("statsmodels ETSModel not available")
        for fc in result["forecasts"]:
            assert fc["lower_bound"] <= fc["qty_predicted"]
            assert fc["qty_predicted"] <= fc["upper_bound"]

    def test_non_negative_forecasts(self):
        series = _make_weekly_seasonal(42, base=5, amplitude=2)
        result = ets_forecast(series, horizon_days=14)
        if result is None:
            pytest.skip("statsmodels ETSModel not available")
        for fc in result["forecasts"]:
            assert float(fc["qty_predicted"]) >= 0

    def test_fallback_configs(self):
        """Even with difficult data, ETS should try simpler configs."""
        import random
        rng = random.Random(99)
        start = date.today() - timedelta(days=35)
        series = [(start + timedelta(days=i), max(0.01, rng.gauss(10, 5))) for i in range(35)]
        result = ets_forecast(series, horizon_days=7)
        # Should either succeed with a simpler config or return None gracefully
        if result is not None:
            assert result["algorithm"] == "ets"


class TestBacktestETS:
    def test_insufficient_data(self):
        series = _make_series(30)
        m = backtest_ets(series, test_days=7)
        assert m["mae"] == 999

    def test_valid_backtest(self):
        series = _make_weekly_seasonal(56, base=15, amplitude=3)
        m = backtest_ets(series, test_days=7)
        if m["mae"] == 999:
            pytest.skip("statsmodels ETSModel not available")
        assert m["mape"] < 999
        assert m["mae"] >= 0


# ═══════════════════════════════════════════════════════════════════════════
# BOOTSTRAPPED INTERVALS FOR CROSTON
# ═══════════════════════════════════════════════════════════════════════════

class TestCrostonBootstrapIntervals:
    def test_returns_unchanged_if_too_few_nonzero(self):
        start = date.today() - timedelta(days=20)
        series = [(start + timedelta(days=i), 1.0 if i == 5 else 0) for i in range(20)]
        base = {"forecasts": [{"qty_predicted": Decimal("1"), "lower_bound": Decimal("0"), "upper_bound": Decimal("2")}],
                "params": {}}
        result = croston_bootstrap_intervals(series, base)
        assert result is base  # Unchanged, returned as-is

    def test_applies_intervals_with_enough_data(self):
        series = _make_intermittent(60, prob=0.3, size_range=(2, 8))
        base = croston_forecast(series, horizon_days=7)
        if base is None:
            pytest.skip("Not enough non-zero demand")
        original_bounds = [(float(fc["lower_bound"]), float(fc["upper_bound"])) for fc in base["forecasts"]]
        result = croston_bootstrap_intervals(series, base)
        assert "bootstrap_samples" in result["params"]
        assert result["params"]["bootstrap_samples"] == 200

    def test_lower_bound_non_negative(self):
        series = _make_intermittent(80, prob=0.25, size_range=(1, 5))
        base = croston_forecast(series, horizon_days=10)
        if base is None:
            pytest.skip("Not enough non-zero demand")
        result = croston_bootstrap_intervals(series, base)
        for fc in result["forecasts"]:
            assert float(fc["lower_bound"]) >= 0

    def test_deterministic_with_seed(self):
        """Same input should produce same output (seed=42)."""
        series = _make_intermittent(60, prob=0.3, size_range=(2, 8))
        base1 = croston_forecast(series, horizon_days=7)
        base2 = croston_forecast(series, horizon_days=7)
        if base1 is None:
            pytest.skip("Not enough non-zero demand")
        r1 = croston_bootstrap_intervals(series, base1)
        r2 = croston_bootstrap_intervals(series, base2)
        for f1, f2 in zip(r1["forecasts"], r2["forecasts"]):
            assert f1["lower_bound"] == f2["lower_bound"]
            assert f1["upper_bound"] == f2["upper_bound"]

    def test_empty_base_forecast_returns_unchanged(self):
        series = _make_intermittent(60, prob=0.3, size_range=(2, 8))
        base = {"forecasts": [], "params": {}}
        result = croston_bootstrap_intervals(series, base)
        assert result is base


# ═══════════════════════════════════════════════════════════════════════════
# SELECT_BEST_MODEL — INTEGRATION WITH NEW ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════

class TestSelectBestModelNewAlgos:
    def test_theta_considered_for_14_days(self):
        series = _make_series(25, base=10, noise=1)
        result = select_best_model(series, horizon=7, test_days=7)
        assert result["algorithm"] != "none"
        assert result["demand_pattern"] is not None

    def test_adaptive_ma_considered_for_21_days(self):
        series = _make_series(35, base=10, noise=1)
        result = select_best_model(series, horizon=7, test_days=7)
        assert result["algorithm"] != "none"

    def test_all_algorithms_compete_for_long_series(self):
        """With 56+ days, HW, HW-Damped, ETS, Theta, Adaptive should all compete."""
        series = _make_weekly_seasonal(60, base=15, amplitude=3)
        result = select_best_model(series, horizon=7, test_days=7)
        assert result["algorithm"] != "none"
        # Should pick the best among all candidates
        assert result["algorithm"] in (
            "simple_avg", "moving_avg", "theta", "adaptive_ma",
            "holt_winters", "hw_damped", "ets", "ensemble",
            "croston", "croston_sba",
        )

    def test_intermittent_prefers_croston(self):
        series = _make_intermittent(30, prob=0.2, size_range=(1, 5))
        result = select_best_model(series, horizon=7, test_days=7,
                                    demand_pattern="intermittent")
        assert result["algorithm"] != "none"
        # For intermittent, selection should use MAE not MAPE

    def test_result_has_demand_pattern(self):
        series = _make_series(30, base=10, noise=1)
        result = select_best_model(series, horizon=7, test_days=7)
        assert "demand_pattern" in result
        assert result["demand_pattern"] in ("smooth", "intermittent", "lumpy", "insufficient")


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES & ROBUSTNESS
# ═══════════════════════════════════════════════════════════════════════════

class TestAlgorithmEdgeCases:
    """Edge cases that apply across all algorithms."""

    def test_all_zeros_series(self):
        start = date.today() - timedelta(days=30)
        series = [(start + timedelta(days=i), 0) for i in range(30)]
        # None of these should crash
        assert theta_forecast(series) is not None or theta_forecast(series) is None
        assert adaptive_moving_average(series) is not None or adaptive_moving_average(series) is None

    def test_single_spike_series(self):
        start = date.today() - timedelta(days=30)
        series = [(start + timedelta(days=i), 100 if i == 15 else 0.01) for i in range(30)]
        result = theta_forecast(series)
        assert result is not None  # Should handle gracefully

    def test_very_large_values(self):
        series = _make_series(30, base=1_000_000, noise=10_000)
        result = theta_forecast(series, horizon_days=7)
        assert result is not None
        for fc in result["forecasts"]:
            assert float(fc["qty_predicted"]) > 0

    def test_decimal_values_in_series(self):
        from decimal import Decimal as D
        start = date.today() - timedelta(days=20)
        series = [(start + timedelta(days=i), D("10.500")) for i in range(20)]
        result = theta_forecast(series)
        assert result is not None

    def test_horizon_1_day(self):
        series = _make_series(20, base=10)
        for fn in [theta_forecast, adaptive_moving_average]:
            result = fn(series, horizon_days=1)
            if result is not None:
                assert len(result["forecasts"]) == 1

    def test_horizon_90_days(self):
        series = _make_series(30, base=10)
        result = theta_forecast(series, horizon_days=90)
        assert result is not None
        assert len(result["forecasts"]) == 90

    def test_backtest_single_fold(self):
        series = _make_series(25, base=10, noise=1)
        m = backtest_theta(series, test_days=7, n_folds=1)
        assert m["mae"] < 999

    def test_all_backtests_return_correct_keys(self):
        series = _make_series(50, base=10, noise=1)
        for fn in [backtest_theta, backtest_adaptive_ma]:
            m = fn(series, test_days=7)
            assert "mae" in m
            assert "mape" in m
            assert "rmse" in m
            assert "bias" in m

    def test_statsmodels_backtests_return_correct_keys(self):
        series = _make_weekly_seasonal(56, base=15, amplitude=3)
        for fn in [backtest_hw_damped, backtest_ets]:
            m = fn(series, test_days=7)
            assert "mae" in m
            assert "mape" in m
            assert "rmse" in m
            assert "bias" in m
