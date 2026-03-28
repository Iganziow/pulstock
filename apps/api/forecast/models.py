from decimal import Decimal
from django.db import models
from django.utils import timezone
from core.models import Tenant, Warehouse


# ======================================================
# DAILY SALES — Materialized daily demand per product
# ======================================================
class DailySales(models.Model):
    """
    Pre-aggregated daily sales/losses/receipts per product per warehouse.
    Populated nightly by `aggregate_daily_sales` management command.
    This is the input for all forecast models.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="daily_sales")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="daily_sales")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="daily_sales")
    date = models.DateField()

    qty_sold = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    qty_lost = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    qty_received = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))

    # ── Promociones (para excluir del forecast) ──
    promo_qty = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0.000"),
        help_text="Qty vendida bajo promoción (subconjunto de qty_sold)",
    )
    promo_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Revenue de ventas promocionales (subconjunto de revenue)",
    )

    # Stockout detection (Phase 1)
    closing_stock = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
        help_text="Stock al cierre del día (para detectar quiebres)"
    )
    is_stockout = models.BooleanField(
        default=False,
        help_text="Probable quiebre de stock (qty_sold~0 con stock agotado)"
    )

    # Importación de datos históricos sin afectar stock
    forecast_only = models.BooleanField(
        default=False,
        help_text=(
            "True = importado desde histórico externo (Excel/CSV). "
            "El motor de forecast lo usa normalmente, pero aggregate_daily_sales "
            "nunca lo sobreescribe y NO genera transacciones de stock."
        ),
    )

    class Meta:
        unique_together = [("tenant", "product", "warehouse", "date")]
        indexes = [
            models.Index(fields=["tenant", "product", "date"]),
            models.Index(fields=["tenant", "warehouse", "date"]),
            models.Index(fields=["tenant", "date"]),
        ]

    def __str__(self):
        return f"DailySales {self.product_id} @ {self.warehouse_id} on {self.date}: sold={self.qty_sold}"


# ======================================================
# FORECAST MODEL — Trained model per product
# ======================================================
class ForecastModel(models.Model):
    ALGORITHM_CHOICES = [
        ("simple_avg", "Promedio Simple"),
        ("moving_avg", "Media Móvil Ponderada"),
        ("adaptive_ma", "Media Móvil Adaptativa"),
        ("holt_winters", "Holt-Winters"),
        ("hw_damped", "Holt-Winters Amortiguado"),
        ("theta", "Método Theta"),
        ("ets", "ETS (Suavizamiento Exponencial)"),
        ("category_prior", "Prior de Categoría"),
        ("croston", "Croston (Demanda Intermitente)"),
        ("croston_sba", "Croston SBA"),
        ("ensemble", "Ensemble"),
        ("ingredient_derived", "Derivado de Receta"),
    ]

    DEMAND_PATTERN_CHOICES = [
        ("smooth", "Regular"),
        ("intermittent", "Intermitente"),
        ("lumpy", "Irregular"),
        ("insufficient", "Datos insuficientes"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="forecast_models")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="forecast_models")
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, null=True, blank=True,
        related_name="forecast_models",
        help_text="null = modelo global del producto"
    )

    algorithm = models.CharField(max_length=30, choices=ALGORITHM_CHOICES, default="moving_avg")
    version = models.IntegerField(default=1)
    model_params = models.JSONField(
        default=dict, blank=True,
        help_text="Parámetros del modelo (pesos, coeficientes, etc.)"
    )
    metrics = models.JSONField(
        default=dict, blank=True,
        help_text="MAE, MAPE, RMSE del último backtest"
    )
    trained_at = models.DateTimeField(default=timezone.now)
    data_points = models.IntegerField(default=0, help_text="Cantidad de días de datos usados")
    demand_pattern = models.CharField(
        max_length=16, choices=DEMAND_PATTERN_CHOICES, default="smooth",
        help_text="Patrón de demanda detectado"
    )
    is_active = models.BooleanField(default=True)

    # ── Confidence label (human-readable) ──
    CONFIDENCE_LABEL_CHOICES = [
        ("very_high", "Muy alta"),
        ("high", "Alta"),
        ("medium", "Media"),
        ("low", "Baja"),
        ("very_low", "Muy baja"),
    ]
    confidence_label = models.CharField(
        max_length=12, choices=CONFIDENCE_LABEL_CHOICES, default="low",
        help_text="Etiqueta interpretable de confianza del modelo"
    )
    confidence_reason = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Razón de la confianza (ej: '6 meses de historia, MAPE 8%')"
    )

    # ── MAPE delta tracking (version-over-version) ──
    prev_mape = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="MAPE del modelo anterior (versión previa)"
    )
    mape_delta = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Cambio en MAPE vs versión anterior (negativo = mejora)"
    )
    prev_algorithm = models.CharField(
        max_length=30, blank=True, default="",
        help_text="Algoritmo del modelo anterior"
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product", "is_active"]),
            models.Index(fields=["tenant", "product", "warehouse", "is_active"]),
        ]

    def __str__(self):
        return f"ForecastModel {self.algorithm} v{self.version} for product={self.product_id} active={self.is_active}"


# ======================================================
# FORECAST — Day-by-day predictions
# ======================================================
class Forecast(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="forecasts")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="forecasts")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="forecasts")
    model = models.ForeignKey(ForecastModel, on_delete=models.CASCADE, related_name="forecasts")

    forecast_date = models.DateField()
    qty_predicted = models.DecimalField(max_digits=12, decimal_places=3)
    lower_bound = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    upper_bound = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))

    days_to_stockout = models.IntegerField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))

    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("tenant", "product", "warehouse", "forecast_date")]
        indexes = [
            models.Index(fields=["tenant", "warehouse", "forecast_date"]),
            models.Index(fields=["tenant", "product", "forecast_date"]),
        ]

    def __str__(self):
        return f"Forecast {self.product_id} @ {self.warehouse_id} for {self.forecast_date}: {self.qty_predicted}"


# ======================================================
# PURCHASE SUGGESTION — Auto-generated order suggestions
# ======================================================
class PurchaseSuggestion(models.Model):
    PRIORITY_CHOICES = [
        ("CRITICAL", "Crítico (< 3 días)"),
        ("HIGH", "Alto (3-7 días)"),
        ("MEDIUM", "Medio (7-14 días)"),
        ("LOW", "Bajo (> 14 días)"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pendiente"),
        ("APPROVED", "Aprobada"),
        ("DISMISSED", "Descartada"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="purchase_suggestions")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="purchase_suggestions")
    supplier_name = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="MEDIUM")

    generated_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "core.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_suggestions"
    )
    purchase = models.ForeignKey(
        "purchases.Purchase", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="from_suggestion"
    )

    total_estimated = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "status", "priority"]),
            models.Index(fields=["tenant", "warehouse", "status"]),
        ]

    def __str__(self):
        return f"Suggestion {self.id} [{self.status}] {self.priority} for wh={self.warehouse_id}"


class SuggestionLine(models.Model):
    suggestion = models.ForeignKey(PurchaseSuggestion, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="suggestion_lines")

    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    avg_daily_demand = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    days_to_stockout = models.IntegerField(default=0)
    suggested_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    margin_at_risk = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Margen bruto en riesgo por quiebre de stock"
    )
    reasoning = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["suggestion", "product"]),
        ]

    def __str__(self):
        return f"SuggestionLine {self.product_id}: suggest={self.suggested_qty} (stockout in {self.days_to_stockout}d)"


# ======================================================
# CATEGORY DEMAND PROFILE — Per-category demand averages
# ======================================================
class CategoryDemandProfile(models.Model):
    """
    Average demand per product within a category, computed nightly.
    Used as a Bayesian prior for sparse-data products.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="category_profiles")
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="demand_profiles"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="category_profiles")

    avg_daily_demand = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    product_count = models.IntegerField(default=0, help_text="Productos con datos de venta")
    data_days = models.IntegerField(default=0, help_text="Días de datos usados")
    dow_factors = models.JSONField(default=dict, blank=True, help_text="Factores día-de-semana")
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "category", "warehouse")]
        indexes = [
            models.Index(fields=["tenant", "warehouse"]),
        ]

    def __str__(self):
        return f"CategoryProfile cat={self.category_id} wh={self.warehouse_id} avg={self.avg_daily_demand}"


# ======================================================
# HOLIDAY — Chilean holidays and custom events
# ======================================================
class Holiday(models.Model):
    SCOPE_NATIONAL = "NATIONAL"
    SCOPE_CUSTOM = "CUSTOM"
    SCOPE_CHOICES = [
        (SCOPE_NATIONAL, "Nacional"),
        (SCOPE_CUSTOM, "Personalizado"),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, null=True, blank=True,
        related_name="holidays",
        help_text="null = feriado nacional compartido"
    )
    name = models.CharField(max_length=120)
    date = models.DateField()
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default=SCOPE_NATIONAL)
    demand_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.50"),
        help_text="Factor de demanda en el día del feriado (1.50 = +50%)"
    )
    pre_days = models.IntegerField(
        default=1,
        help_text="Días antes del feriado con demanda elevada"
    )
    pre_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.20"),
        help_text="Factor de demanda en días previos al feriado"
    )
    # Extended holiday modeling — multi-day events + post-event demand dip
    duration_days = models.IntegerField(
        default=1,
        help_text="Duración del evento en días (Fiestas Patrias=3, Navidad=1)"
    )
    post_days = models.IntegerField(
        default=0,
        help_text="Días posteriores con demanda alterada (post-event dip)"
    )
    post_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.85"),
        help_text="Factor post-evento (0.85 = -15% demanda tras el evento)"
    )
    RAMP_TYPE_CHOICES = [
        ("instant", "Instantáneo"),
        ("linear", "Gradual (rampa)"),
        ("plateau", "Meseta"),
    ]
    ramp_type = models.CharField(
        max_length=10, choices=RAMP_TYPE_CHOICES, default="instant",
        help_text="Forma de la rampa de demanda pre-evento"
    )

    is_recurring = models.BooleanField(default=True, help_text="Se repite cada año")
    learned_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Multiplicador aprendido de datos históricos"
    )
    last_actual_date = models.DateField(
        null=True, blank=True,
        help_text="Última fecha en que se midió el impacto real"
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"Holiday {self.name} ({self.date}) x{self.demand_multiplier}"


# ======================================================
# FORECAST ACCURACY — Daily actual-vs-predicted tracking
# ======================================================
class ForecastAccuracy(models.Model):
    """
    Comparación diaria: lo que se predijo vs lo que realmente pasó.
    Poblado por track_forecast_accuracy command después de aggregate_daily_sales.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="forecast_accuracy")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="forecast_accuracy")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="forecast_accuracy")
    date = models.DateField()

    qty_predicted = models.DecimalField(max_digits=12, decimal_places=3)
    qty_actual = models.DecimalField(max_digits=12, decimal_places=3)
    error = models.DecimalField(max_digits=12, decimal_places=3, help_text="predicted - actual")
    abs_pct_error = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="|error| / actual × 100"
    )
    algorithm = models.CharField(max_length=30)
    was_stockout = models.BooleanField(default=False)

    class Meta:
        unique_together = [("tenant", "product", "warehouse", "date")]
        indexes = [
            models.Index(fields=["tenant", "date"]),
            models.Index(fields=["tenant", "algorithm", "date"]),
        ]

    def __str__(self):
        return f"Accuracy {self.product_id} @ {self.date}: pred={self.qty_predicted} actual={self.qty_actual}"


# ======================================================
# SUGGESTION OUTCOME — Feedback loop: suggested vs actual
# ======================================================
class SuggestionOutcome(models.Model):
    """
    Tracks how well a purchase suggestion performed after the
    merchandise arrived. Compares suggested_qty vs purchased_qty,
    estimated_cost vs actual_cost, and predicted_days vs actual_days_lasted.
    Populated by evaluate_suggestion_outcomes task.
    """
    suggestion = models.OneToOneField(
        PurchaseSuggestion, on_delete=models.CASCADE, related_name="outcome"
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="suggestion_outcomes")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="suggestion_outcomes"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="suggestion_outcomes")

    # What we suggested vs what actually happened
    suggested_qty = models.DecimalField(max_digits=12, decimal_places=3)
    purchased_qty = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # How long the purchased stock lasted
    predicted_days = models.IntegerField(
        help_text="Días que se estimó duraría el stock con la qty sugerida"
    )
    actual_days_lasted = models.IntegerField(
        null=True, blank=True,
        help_text="Días reales que duró el stock después de recibir la compra"
    )

    # Computed metrics
    qty_error_pct = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="(purchased - suggested) / suggested × 100"
    )
    days_error_pct = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="(actual_days - predicted_days) / predicted_days × 100"
    )

    # Safety stock adjustment signal
    safety_stock_adjustment = models.DecimalField(
        max_digits=8, decimal_places=3, default=Decimal("0.000"),
        help_text="Ajuste recomendado de safety stock (+/- unidades/día)"
    )

    evaluated_at = models.DateTimeField(default=timezone.now)
    purchase_received_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Cuándo se recibió la mercadería de la compra vinculada"
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "warehouse", "evaluated_at"]),
        ]

    def __str__(self):
        return (
            f"Outcome suggestion={self.suggestion_id} product={self.product_id}: "
            f"suggested={self.suggested_qty} purchased={self.purchased_qty} "
            f"predicted={self.predicted_days}d actual={self.actual_days_lasted}d"
        )