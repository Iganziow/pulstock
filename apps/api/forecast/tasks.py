"""
forecast/tasks.py
=================
Celery tasks for the nightly forecast pipeline.

Pipeline order (each task depends on the previous):
  1. aggregate_daily_sales     — 02:00  Materialise SaleLines → DailySales
  2. compute_category_profiles — 02:30  Bayesian priors for sparse products
  3. track_forecast_accuracy   — 02:45  Compare yesterday's predictions vs actuals
  4. train_forecast_models     — 03:00  Retrain models (auto-selects best algorithm)
  5. generate_suggestions      — 04:00  Create PurchaseSuggestions for at-risk SKUs
  6. evaluate_suggestion_outcomes — 05:00  Close the loop: suggested vs purchased vs actual
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

try:
    from celery import shared_task
except ImportError:
    def shared_task(func=None, **kwargs):
        if func is not None:
            return func
        return lambda f: f

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# TASK 1: Aggregate daily sales
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.aggregate_daily_sales",
             soft_time_limit=300, time_limit=360)
def aggregate_daily_sales(days: int = 1, tenant_id: int | None = None):
    """Delegates to the management command logic."""
    from django.core.management import call_command

    args = ["aggregate_daily_sales", "--days", str(days)]
    if tenant_id:
        args += ["--tenant", str(tenant_id)]
    call_command(*args)
    logger.info("aggregate_daily_sales: done (days=%d)", days)


# ─────────────────────────────────────────────────────────────
# TASK 2: Compute category profiles (Bayesian priors)
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.compute_category_profiles",
             soft_time_limit=300, time_limit=360)
def compute_category_profiles(tenant_id: int | None = None):
    from django.core.management import call_command

    args = ["compute_category_profiles"]
    if tenant_id:
        args += ["--tenant", str(tenant_id)]
    call_command(*args)
    logger.info("compute_category_profiles: done")


# ─────────────────────────────────────────────────────────────
# TASK 3: Track forecast accuracy
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.track_forecast_accuracy",
             soft_time_limit=300, time_limit=360)
def track_forecast_accuracy(days: int = 1, tenant_id: int | None = None):
    from django.core.management import call_command

    args = ["track_forecast_accuracy", "--days", str(days)]
    if tenant_id:
        args += ["--tenant", str(tenant_id)]
    call_command(*args)
    logger.info("track_forecast_accuracy: done (days=%d)", days)


# ─────────────────────────────────────────────────────────────
# TASK 4: Train forecast models
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.train_forecast_models",
             soft_time_limit=600, time_limit=660)
def train_forecast_models(tenant_id: int | None = None):
    from django.core.management import call_command

    args = ["train_forecast_models"]
    if tenant_id:
        args += ["--tenant", str(tenant_id)]
    call_command(*args)
    logger.info("train_forecast_models: done")


# ─────────────────────────────────────────────────────────────
# TASK 5: Generate purchase suggestions
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.generate_purchase_suggestions",
             soft_time_limit=300, time_limit=360)
def generate_purchase_suggestions(tenant_id: int | None = None):
    from django.core.management import call_command

    args = ["generate_purchase_suggestions"]
    if tenant_id:
        args += ["--tenant", str(tenant_id)]
    call_command(*args)
    logger.info("generate_purchase_suggestions: done")


# ─────────────────────────────────────────────────────────────
# TASK 6: Evaluate suggestion outcomes (feedback loop)
# ─────────────────────────────────────────────────────────────
@shared_task(name="forecast.tasks.evaluate_suggestion_outcomes",
             soft_time_limit=300, time_limit=360)
def evaluate_suggestion_outcomes():
    """
    For each APPROVED suggestion that has a linked Purchase in POSTED status,
    compute the outcome: suggested_qty vs purchased_qty, predicted_days vs
    actual_days_lasted, and derive a safety_stock_adjustment.

    A suggestion is ready for evaluation when:
    - It's APPROVED and has a linked Purchase
    - The Purchase is POSTED (merchandise received)
    - No SuggestionOutcome exists yet
    - At least 7 days have passed since the purchase was posted
      (so we have enough consumption data to measure)
    """
    from purchases.models import Purchase
    from inventory.models import StockItem
    from forecast.models import (
        PurchaseSuggestion, SuggestionLine, SuggestionOutcome,
        DailySales, ForecastModel,
    )
    from core.models import Tenant

    now = timezone.now()
    min_age = now - timedelta(days=7)  # wait 7 days before evaluating

    # Find approved suggestions with posted purchases, not yet evaluated
    suggestions = (
        PurchaseSuggestion.objects
        .filter(
            status="APPROVED",
            purchase__isnull=False,
            purchase__status=Purchase.STATUS_POSTED,
            purchase__created_at__lte=min_age,
        )
        .exclude(outcome__isnull=False)  # not yet evaluated
        .select_related("purchase", "tenant")
    )

    evaluated = 0
    for suggestion in suggestions:
        purchase = suggestion.purchase
        tenant = suggestion.tenant
        wid = suggestion.warehouse_id

        # Get all suggestion lines
        slines = list(
            SuggestionLine.objects
            .filter(suggestion=suggestion)
            .values("product_id", "suggested_qty", "estimated_cost",
                    "avg_daily_demand", "days_to_stockout")
        )

        if not slines:
            continue

        # Get actual purchased quantities per product from the linked Purchase
        from purchases.models import PurchaseLine
        purchased_map = dict(
            PurchaseLine.objects
            .filter(purchase=purchase)
            .values_list("product_id", "qty")
        )
        purchased_cost_map = dict(
            PurchaseLine.objects
            .filter(purchase=purchase)
            .values_list("product_id", "line_total_cost")
        )

        purchase_date = purchase.created_at.date()

        for sline in slines:
            pid = sline["product_id"]
            suggested_qty = sline["suggested_qty"]
            avg_daily = sline["avg_daily_demand"]
            estimated_cost = sline["estimated_cost"]
            predicted_days_out = sline["days_to_stockout"]

            purchased_qty = purchased_map.get(pid)
            actual_cost = purchased_cost_map.get(pid)

            # Compute predicted_days: how many days we expected the
            # purchased (or suggested) qty to last
            effective_qty = purchased_qty if purchased_qty is not None else suggested_qty
            if effective_qty is None:
                continue
            if avg_daily and avg_daily > 0:
                predicted_days = int(Decimal(str(effective_qty)) / Decimal(str(avg_daily)))
            else:
                predicted_days = predicted_days_out or 14

            # Compute actual_days_lasted: days from purchase until
            # stock hit zero (or up to today if still in stock)
            actual_days = _compute_actual_days_lasted(
                tenant.id, pid, wid, purchase_date, now.date()
            )

            # Compute error percentages
            qty_error_pct = None
            if suggested_qty and suggested_qty > 0 and purchased_qty is not None:
                qty_error_pct = (
                    (purchased_qty - suggested_qty) / suggested_qty * 100
                ).quantize(Decimal("0.01"))

            days_error_pct = None
            if predicted_days and predicted_days > 0 and actual_days is not None:
                days_error_pct = Decimal(
                    str((actual_days - predicted_days) / predicted_days * 100)
                ).quantize(Decimal("0.01"))

            # Compute safety stock adjustment
            # If stock ran out faster than predicted → increase safety stock
            # If stock lasted longer → decrease (gently)
            adjustment = _compute_safety_adjustment(
                avg_daily, predicted_days, actual_days
            )

            SuggestionOutcome.objects.create(
                suggestion=suggestion,
                tenant=tenant,
                product_id=pid,
                warehouse_id=wid,
                suggested_qty=suggested_qty,
                purchased_qty=purchased_qty,
                estimated_cost=estimated_cost,
                actual_cost=actual_cost,
                predicted_days=predicted_days,
                actual_days_lasted=actual_days,
                qty_error_pct=qty_error_pct,
                days_error_pct=days_error_pct,
                safety_stock_adjustment=adjustment,
                evaluated_at=now,
                purchase_received_at=purchase.created_at,
            )
            evaluated += 1

            # Apply adjustment to model params (bias_correction)
            _apply_safety_adjustment(tenant.id, pid, wid, adjustment)

    logger.info("evaluate_suggestion_outcomes: %d outcomes created", evaluated)
    return {"evaluated": evaluated}


def _compute_actual_days_lasted(
    tenant_id: int, product_id: int, warehouse_id: int,
    purchase_date: date, today: date
) -> int | None:
    """
    Count days from purchase_date until the product hit zero stock,
    using DailySales data. If stock is still > 0, returns days so far.
    """
    from forecast.models import DailySales

    daily = list(
        DailySales.objects
        .filter(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            date__gte=purchase_date,
            date__lte=today,
        )
        .order_by("date")
        .values_list("date", "closing_stock", "is_stockout")
    )

    if not daily:
        return None

    for ds_date, closing, stockout in daily:
        if stockout or (closing is not None and closing <= 0):
            return (ds_date - purchase_date).days

    # Stock never hit zero — return days elapsed so far
    return (today - purchase_date).days


def _compute_safety_adjustment(
    avg_daily: Decimal, predicted_days: int, actual_days: int | None
) -> Decimal:
    """
    Compute how much to adjust safety stock (units/day).

    If stock ran out faster than predicted → positive adjustment (need more buffer).
    If stock lasted longer → small negative adjustment (reduce buffer gently).
    Damped to avoid overreaction: adjustments are capped at ±20% of avg_daily.
    """
    if actual_days is None or not avg_daily or avg_daily <= 0:
        return Decimal("0.000")

    if predicted_days <= 0:
        return Decimal("0.000")

    ratio = Decimal(str(actual_days)) / Decimal(str(predicted_days))  # < 1 means ran out faster

    if ratio < Decimal("0.7"):
        # Significantly underestimated demand — increase safety stock
        adj = avg_daily * Decimal("0.15")  # +15% of daily demand
    elif ratio < Decimal("0.9"):
        # Slightly underestimated
        adj = avg_daily * Decimal("0.08")  # +8%
    elif ratio > Decimal("1.3"):
        # Overestimated — gently reduce
        adj = avg_daily * Decimal("-0.05")  # -5%
    elif ratio > Decimal("1.1"):
        adj = avg_daily * Decimal("-0.02")  # -2%
    else:
        adj = Decimal("0")  # Within tolerance

    # Cap at ±20% of avg_daily
    cap = avg_daily * Decimal("0.20")
    adj = max(-cap, min(cap, adj))

    return Decimal(str(adj)).quantize(Decimal("0.001"))


def _apply_safety_adjustment(
    tenant_id: int, product_id: int, warehouse_id: int, adjustment: Decimal
):
    """
    Apply the safety stock adjustment to the active ForecastModel's bias_correction.
    This feeds into the next training cycle's predictions.
    """
    if adjustment == 0:
        return

    from forecast.models import ForecastModel

    fm = (
        ForecastModel.objects
        .filter(
            tenant_id=tenant_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            is_active=True,
        )
        .first()
    )
    if not fm:
        return

    params = fm.model_params or {}
    current_bias = Decimal(str(params.get("bias_correction", 0)))
    # Blend: 70% existing bias + 30% new adjustment signal
    new_bias = (current_bias * Decimal("0.7") + adjustment * Decimal("0.3")).quantize(Decimal("0.001"))
    params["bias_correction"] = str(new_bias)
    params["last_safety_adjustment"] = str(adjustment)
    params["safety_adjusted_at"] = timezone.now().isoformat()
    fm.model_params = params
    fm.save(update_fields=["model_params"])
