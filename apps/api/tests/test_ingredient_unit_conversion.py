"""
Tests del fix de conversión de unidades en train_ingredient_product
y compute_ingredient_demand.

BUG DETECTADO 08/05/26
======================
Cuando una receta usa GR pero el ingrediente está en KG (ej: receta de
Mokaccino dice "28 GR de Jamón sachet" pero Jamón.unit_obj=KG), el
sistema descuenta correctamente 0.028 KG (vía sales/recipes._convert_line_qty),
pero la predicción `ingredient_derived` sumaba 28 directo —
generando una sobre-predicción 1000x que disparaba MAPE > 200%.

Fix: aplicar el mismo `_convert_line_qty` en train_ingredient_product
y compute_ingredient_demand para que predicción y realidad estén en
la misma unidad.
"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from django.utils import timezone

from catalog.models import Product, Recipe, RecipeLine, Unit
from core.models import Warehouse
from forecast.models import Forecast, ForecastModel
from forecast.services import compute_ingredient_demand, train_ingredient_product


@pytest.fixture
def units(db, tenant):
    """Crea unidades GR y KG con conversion_factor real."""
    gr, _ = Unit.objects.get_or_create(
        tenant=tenant, code="GR",
        defaults={
            "name": "Gramo", "family": "weight",
            "conversion_factor": Decimal("1"),  # base = gramo
            "is_base": True,
        },
    )
    kg, _ = Unit.objects.get_or_create(
        tenant=tenant, code="KG",
        defaults={
            "name": "Kilogramo", "family": "weight",
            "conversion_factor": Decimal("1000"),  # 1 KG = 1000 GR
            "is_base": False,
        },
    )
    return {"GR": gr, "KG": kg}


@pytest.fixture
def warehouse_e2e(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="W-E2E")


@pytest.fixture
def parent_product(db, tenant):
    """Producto vendido (Mokaccino)."""
    return Product.objects.create(
        tenant=tenant, name="Mokaccino", price=Decimal("4500"),
        is_active=True, unit="UN",
    )


@pytest.fixture
def ingredient_in_kg(db, tenant, units):
    """
    Ingrediente con unit_obj = KG. Casa real de Mario:
    Jamón sachet, Salsa caramelo. La receta los usa en GR pero el
    producto está registrado como KG.
    """
    p = Product.objects.create(
        tenant=tenant, name="Jamón sachet", price=Decimal("0"),
        is_active=True, unit="KG",
        unit_obj=units["KG"],
    )
    return p


@pytest.fixture
def recipe_with_unit_mismatch(db, tenant, parent_product, ingredient_in_kg, units):
    """
    Receta que pide 28 GR de Jamón (que está en KG).
    sales/recipes.py convierte a 0.028 KG al vender.
    forecast/services.py debe convertir igual al predecir.
    """
    recipe = Recipe.objects.create(
        tenant=tenant, product=parent_product, is_active=True,
    )
    RecipeLine.objects.create(
        tenant=tenant, recipe=recipe,
        ingredient=ingredient_in_kg,
        qty=Decimal("28.0"),
        unit=units["GR"],  # ← receta en GR
    )
    return recipe


# ── Tests de compute_ingredient_demand ─────────────────────────────────────


@pytest.mark.django_db
class TestComputeIngredientDemand:
    """Función usada como `ingredient_forecast_boost` (alimenta otros forecasts)."""

    def test_converts_recipe_qty_to_ingredient_unit(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """Si receta dice 28 GR pero ingrediente está en KG, la demanda
        derivada debe estar en KG (0.028 × parent_avg)."""
        # Parent vende 10/día en promedio
        ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={"avg_daily": "10"},  # 10 unidades de Mokaccino/día
            data_points=30, demand_pattern="smooth",
            confidence_label="medium",
        )

        demand = compute_ingredient_demand(tenant.id, [warehouse_e2e.id])
        # 10 mokaccinos × 28 GR / 1000 = 0.28 KG
        assert ingredient_in_kg.id in demand
        assert demand[ingredient_in_kg.id] == pytest.approx(0.28, rel=1e-4), (
            f"Esperaba 0.28 KG (10 mokaccinos × 0.028 KG c/u). "
            f"Obtuve {demand[ingredient_in_kg.id]}. Si está en 280, "
            f"la conversión de unidades NO se está aplicando."
        )

    def test_no_conversion_when_units_match(
        self, tenant, warehouse_e2e, parent_product, units,
    ):
        """Si receta y unit_obj coinciden, la qty pasa tal cual."""
        ingredient = Product.objects.create(
            tenant=tenant, name="Cacao", price=Decimal("0"),
            is_active=True, unit="GR", unit_obj=units["GR"],
        )
        recipe = Recipe.objects.create(
            tenant=tenant, product=parent_product, is_active=True,
        )
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=ingredient,
            qty=Decimal("5"), unit=units["GR"],
        )
        ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={"avg_daily": "10"},
            data_points=30, demand_pattern="smooth",
            confidence_label="medium",
        )

        demand = compute_ingredient_demand(tenant.id, [warehouse_e2e.id])
        # 10 × 5 GR = 50 GR (sin conversión, ambos en GR)
        assert demand[ingredient.id] == pytest.approx(50.0, rel=1e-4)


# ── Tests de train_ingredient_product ─────────────────────────────────────


@pytest.mark.django_db
class TestTrainIngredientProduct:
    """Función que genera Forecast diario para ingredientes derivados."""

    def test_forecast_qty_in_ingredient_unit_not_recipe_unit(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """El Forecast generado debe estar en la unidad del ingrediente
        (KG), no de la receta (GR). Tiene que coincidir con cómo
        sales/recipes.py descuenta el stock al vender."""
        today = date.today()

        # Crear forecasts diarios del PADRE (Mokaccino) que la función lee
        for i in range(1, 8):
            d = today + timedelta(days=i)
            Forecast.objects.create(
                tenant=tenant, product=parent_product,
                warehouse=warehouse_e2e,
                model=ForecastModel.objects.create(
                    tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                    algorithm="moving_avg", version=i, is_active=False,
                    model_params={}, data_points=30,
                    demand_pattern="smooth", confidence_label="medium",
                ),
                forecast_date=d,
                qty_predicted=Decimal("10"),  # 10 mokaccinos/día
                confidence=Decimal("65"),
            )

        from inventory.models import StockItem
        stock_item = StockItem.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            on_hand=Decimal("5.000"), avg_cost=Decimal("100.00"),
        )

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id,
            today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
            stats=stats,
        )

        assert stats["trained"] == 1, f"No se entrenó. stats={stats}"

        # Forecast debe estar en KG: 10 mokaccinos × 0.028 KG = 0.28 KG/día
        forecasts = Forecast.objects.filter(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
        ).order_by("forecast_date")
        assert forecasts.count() == 7

        for f in forecasts:
            assert f.qty_predicted == pytest.approx(Decimal("0.28"), abs=Decimal("0.001")), (
                f"Forecast del día {f.forecast_date} = {f.qty_predicted}. "
                f"Esperaba 0.280 KG. Si está en 280 (sin convertir), el bug "
                f"de conversión de unidades NO está arreglado."
            )


# ── Tests de Fase 1: candidato paralelo (make_active=False) ───────────────


@pytest.mark.django_db
class TestIngredientDerivedParallelCandidate:
    """
    Fase 1: cuando un ingrediente con receta activa ya tiene un modelo organic
    entrenado, train_ingredient_product(make_active=False) lo entrena en
    paralelo SIN desactivar el organic y SIN duplicar predicciones.

    Esto deja la base para Fase 2 (backtest + selección por WAPE).
    """

    def _setup(self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
               recipe_with_unit_mismatch):
        from inventory.models import StockItem
        today = date.today()

        # Forecast diario del padre que la función lee
        parent_model = ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={}, data_points=30,
            demand_pattern="smooth", confidence_label="medium",
        )
        for i in range(1, 8):
            Forecast.objects.create(
                tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                model=parent_model,
                forecast_date=today + timedelta(days=i),
                qty_predicted=Decimal("10"), confidence=Decimal("65"),
            )

        stock_item = StockItem.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            on_hand=Decimal("5.000"), avg_cost=Decimal("100.00"),
        )

        # Simulamos un organic activo previo en el ingrediente.
        organic_active = ForecastModel.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            algorithm="theta", version=1, is_active=True,
            model_params={}, data_points=60,
            metrics={"mae": 0.1, "wape": 12.0, "mape": 15.0},
            demand_pattern="smooth", confidence_label="high",
            confidence_reason="2 meses; WAPE 12%",
        )

        return today, stock_item, organic_active

    def test_make_active_false_keeps_organic_active(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """make_active=False NO debe desactivar el organic activo previo."""
        today, stock_item, organic = self._setup(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
        )

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
            stats=stats, make_active=False,
        )

        organic.refresh_from_db()
        assert organic.is_active is True, (
            "El modelo organic NO debe desactivarse cuando se entrena el "
            "derived como candidato paralelo."
        )

        derived = ForecastModel.objects.get(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
        )
        assert derived.is_active is False
        assert "CANDIDATO" in derived.confidence_reason

    def test_make_active_false_does_not_write_forecasts(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """El candidato no debe escribir Forecast rows (duplicaría predicciones)."""
        today, stock_item, organic = self._setup(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
        )

        n_fc_before = Forecast.objects.filter(
            tenant=tenant, product=ingredient_in_kg,
        ).count()

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
            stats=stats, make_active=False,
        )

        n_fc_after = Forecast.objects.filter(
            tenant=tenant, product=ingredient_in_kg,
        ).count()
        assert n_fc_after == n_fc_before, (
            f"Candidato derived escribió {n_fc_after - n_fc_before} Forecast "
            f"rows. No debe — duplica predicciones del producto."
        )

    def test_repeated_train_does_not_accumulate_candidates(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """Cada noche entrena, pero sólo debe haber 1 derived candidato por
        (product, warehouse) — los anteriores inactivos se borran."""
        today, stock_item, _ = self._setup(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
        )

        for _ in range(3):
            stats = {"trained": 0, "skipped": 0, "by_algo": {}}
            train_ingredient_product(
                tenant=tenant, product=ingredient_in_kg,
                warehouse_id=warehouse_e2e.id, today=today, horizon=7,
                stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
                stats=stats, make_active=False,
            )

        n_candidates = ForecastModel.objects.filter(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
            is_active=False,
        ).count()
        assert n_candidates == 1, (
            f"Después de 3 trains debe haber 1 derived candidato, hay {n_candidates}"
        )

    def test_make_active_true_preserves_legacy_behavior(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """make_active=True (default) mantiene el comportamiento histórico:
        desactiva el modelo activo previo y se vuelve EL activo."""
        today, stock_item, organic = self._setup(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
        )

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock_item},
            stats=stats,  # make_active=True por default
        )

        organic.refresh_from_db()
        assert organic.is_active is False, (
            "make_active=True (default) DEBE desactivar el organic anterior "
            "— este es el comportamiento legacy que mantenemos para el caso "
            "sparse-data (n_days < min_days)."
        )

        derived = ForecastModel.objects.get(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
        )
        assert derived.is_active is True


# ── Tests de Fase 2: backtest historico + swap automatico ────────────────


@pytest.mark.django_db
class TestIngredientDerivedBacktestAndSwap:
    """
    Fase 2.2 + 2.3:
    - El derived calcula WAPE genuino a partir de DailySales historicos
      de los padres x recipe_multipliers vs DailySales reales del ingrediente.
    - Si WAPE derived < WAPE organic * 0.85 Y WAPE derived < 80%, swap
      automatico: derived pasa a activo, organic queda inactivo.
    """
    from forecast.models import DailySales as _DS  # noqa

    def _setup_full_history(self, tenant, warehouse_e2e, parent_product,
                            ingredient_in_kg, recipe_with_unit_mismatch,
                            parent_qty_per_day=10, actual_per_day_kg="0.28"):
        """
        Setup completo con:
        - 30 dias de DailySales del padre (parent_qty_per_day mokaccinos/dia)
        - 30 dias de DailySales del ingrediente (actual_per_day_kg)
        - 7 dias de Forecast futuros del padre
        Receta: 28 GR / mokaccino -> 0.028 KG. Si parent=10/dia -> deberia
        derivar 0.28 KG/dia (que es lo que pasamos como actual_per_day_kg
        por default, dando WAPE ~0).
        """
        from inventory.models import StockItem
        from forecast.models import DailySales
        today = date.today()

        # ForecastModel del padre + 7 Forecasts futuros
        parent_model = ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={}, data_points=30,
            demand_pattern="smooth", confidence_label="medium",
        )
        for i in range(1, 8):
            Forecast.objects.create(
                tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                model=parent_model,
                forecast_date=today + timedelta(days=i),
                qty_predicted=Decimal(str(parent_qty_per_day)),
                confidence=Decimal("65"),
            )

        # DailySales historicos: 30 dias del padre y del ingrediente
        for i in range(1, 31):
            d = today - timedelta(days=i)
            DailySales.objects.create(
                tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                date=d, qty_sold=Decimal(str(parent_qty_per_day)),
                revenue=Decimal("0"),
            )
            DailySales.objects.create(
                tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
                date=d, qty_sold=Decimal(str(actual_per_day_kg)),
                revenue=Decimal("0"),
            )

        stock_item = StockItem.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            on_hand=Decimal("5.000"), avg_cost=Decimal("100.00"),
        )

        return today, stock_item

    def test_backtest_writes_real_wape(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """El derived debe guardar WAPE genuino del backtest, no 0 hardcoded."""
        today, stock = self._setup_full_history(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
            parent_qty_per_day=10,
            actual_per_day_kg="0.28",  # match perfecto: 10 * 0.028 = 0.28
        )
        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock},
            stats=stats, make_active=False,
        )

        derived = ForecastModel.objects.get(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
        )
        assert "wape" in derived.metrics
        # Con match perfecto (real = 0.28 = pred) WAPE debe ser ~0
        assert derived.metrics["wape"] <= 1.0, (
            f"WAPE backtest esperado ~0 (match perfecto), got {derived.metrics['wape']}"
        )
        # backtest_days debe estar en model_params
        assert derived.model_params.get("backtest_days") == 30

    def test_swap_when_derived_clearly_better(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """derived WAPE 0% vs organic WAPE 80% -> swap (margen 15% cumplido)."""
        today, stock = self._setup_full_history(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
            parent_qty_per_day=10, actual_per_day_kg="0.28",
        )
        # Organic activo con WAPE alto
        organic = ForecastModel.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            algorithm="theta", version=1, is_active=True,
            model_params={}, data_points=30,
            metrics={"wape": 80.0, "mae": 0.5},
            demand_pattern="smooth", confidence_label="low",
        )

        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock},
            stats=stats, make_active=False,
        )

        organic.refresh_from_db()
        assert organic.is_active is False, "Organic debe haberse desactivado"

        derived = ForecastModel.objects.get(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
        )
        assert derived.is_active is True, "Derived debe haberse activado por swap"
        assert "gana al organic" in derived.confidence_reason

        # Forecasts del derived deben existir; del organic no
        n_fc_derived = Forecast.objects.filter(model=derived).count()
        n_fc_organic = Forecast.objects.filter(
            model=organic, forecast_date__gt=today,
        ).count()
        assert n_fc_derived > 0, "Derived activo debe tener Forecast rows"
        assert n_fc_organic == 0, "Forecasts futuros del organic deben borrarse"

        assert stats.get("swapped_to_derived") == 1

    def test_no_swap_when_derived_above_safety_threshold(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """derived WAPE 100% (sobre 80% threshold) NO debe swappear aunque
        sea mejor que el organic (proteccion: no activar modelos malos)."""
        # Real = 0.10 KG/dia, derived predice 0.28 -> WAPE = |0.18|/0.10 = 180%
        today, stock = self._setup_full_history(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
            parent_qty_per_day=10, actual_per_day_kg="0.10",
        )
        organic = ForecastModel.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            algorithm="theta", version=1, is_active=True,
            model_params={}, data_points=30,
            metrics={"wape": 500.0, "mae": 1.0},  # peor que derived
            demand_pattern="smooth", confidence_label="low",
        )
        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock},
            stats=stats, make_active=False,
        )
        organic.refresh_from_db()
        assert organic.is_active is True, (
            "Organic debe seguir activo: aunque derived es 'menos malo', "
            "ambos > 80% threshold, no se promueve."
        )
        assert stats.get("swapped_to_derived", 0) == 0

    def test_no_swap_marginal_improvement(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """derived 50%, organic 55% -> no swap (50 > 55*0.85=46.75)."""
        # Real = 0.42, pred = 0.28 -> |0.14|/0.42 = 33% WAPE
        today, stock = self._setup_full_history(
            tenant, warehouse_e2e, parent_product, ingredient_in_kg,
            recipe_with_unit_mismatch,
            parent_qty_per_day=10, actual_per_day_kg="0.42",
        )
        organic = ForecastModel.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            algorithm="theta", version=1, is_active=True,
            model_params={}, data_points=30,
            metrics={"wape": 36.0},  # apenas mejor que derived 33%
            demand_pattern="smooth", confidence_label="medium",
        )
        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock},
            stats=stats, make_active=False,
        )
        organic.refresh_from_db()
        assert organic.is_active is True, (
            "Mejora marginal (33% vs 36%) NO debe swappear — protege contra "
            "flicker noche-a-noche por ruido del backtest."
        )

    def test_no_backtest_no_swap(
        self, tenant, warehouse_e2e, parent_product, ingredient_in_kg,
        recipe_with_unit_mismatch,
    ):
        """Sin DailySales historicas del padre el backtest no tiene base
        -> WAPE 999 -> NO swap."""
        from inventory.models import StockItem
        today = date.today()
        # Sin DailySales del padre ni del ingrediente -> no hay backtest
        parent_model = ForecastModel.objects.create(
            tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
            algorithm="moving_avg", version=1, is_active=True,
            model_params={}, data_points=30, demand_pattern="smooth",
            confidence_label="medium",
        )
        for i in range(1, 8):
            Forecast.objects.create(
                tenant=tenant, product=parent_product, warehouse=warehouse_e2e,
                model=parent_model, forecast_date=today + timedelta(days=i),
                qty_predicted=Decimal("10"), confidence=Decimal("65"),
            )
        stock = StockItem.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            on_hand=Decimal("5"), avg_cost=Decimal("100"),
        )
        organic = ForecastModel.objects.create(
            tenant=tenant, product=ingredient_in_kg, warehouse=warehouse_e2e,
            algorithm="theta", version=1, is_active=True,
            model_params={}, data_points=30,
            metrics={"wape": 999.0}, demand_pattern="smooth",
            confidence_label="low",
        )
        stats = {"trained": 0, "skipped": 0, "by_algo": {}}
        train_ingredient_product(
            tenant=tenant, product=ingredient_in_kg,
            warehouse_id=warehouse_e2e.id, today=today, horizon=7,
            stock_items={(ingredient_in_kg.id, warehouse_e2e.id): stock},
            stats=stats, make_active=False,
        )
        organic.refresh_from_db()
        assert organic.is_active is True, (
            "Sin backtest valido (sin DailySales) el derived no puede competir."
        )
        derived = ForecastModel.objects.get(
            tenant=tenant, product=ingredient_in_kg,
            warehouse=warehouse_e2e, algorithm="ingredient_derived",
        )
        assert derived.metrics.get("wape") == 999
