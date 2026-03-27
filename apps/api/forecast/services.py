"""
forecast.services
=================
Business logic for the forecast module.
Views and management commands delegate here — they handle HTTP / CLI concerns only.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

from django.db import models as db_models
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce
from django.db import transaction
from django.utils import timezone

from core.models import Warehouse
from catalog.models import Product, RecipeLine
from inventory.models import StockItem
from forecast.models import (
    DailySales, ForecastModel, Forecast,
    PurchaseSuggestion, SuggestionLine,
)
from forecast.engine import (
    select_best_model, calculate_days_to_stockout,
    category_prior_forecast, apply_holiday_adjustments,
    clean_series, classify_demand_pattern,
    compute_month_position_factors, detect_trend,
    apply_trend_adjustment, apply_bias_correction,
    apply_empirical_intervals, detect_price_change_impact,
    compute_monthly_seasonality, apply_monthly_seasonality,
    compute_yoy_growth, apply_yoy_adjustment,
    compute_confidence_decay,
)

D0 = Decimal("0.000")
D2 = Decimal("0.01")


def compute_confidence_label(data_points: int, mape: float, demand_pattern: str) -> tuple[str, str]:
    """
    Return (label, reason) for human-readable confidence.

    Rules (cumulative):
    - data_points >= 180 AND mape < 15 → very_high
    - data_points >= 90  AND mape < 25 → high
    - data_points >= 30  AND mape < 40 → medium
    - data_points >= 14  OR  mape < 60 → low
    - else → very_low
    Intermittent/lumpy patterns cap at "high" (MAPE is unreliable for them).
    """
    parts = []
    if data_points >= 180:
        parts.append(f"{data_points // 30} meses de historia")
    elif data_points >= 30:
        parts.append(f"{data_points // 30} mes(es) de historia")
    else:
        parts.append(f"{data_points} días de datos")

    if mape < 999:
        parts.append(f"MAPE {mape:.0f}%")

    cap = "very_high"
    if demand_pattern in ("intermittent", "lumpy"):
        cap = "high"
        parts.append(f"demanda {demand_pattern}")

    if data_points >= 180 and mape < 15:
        label = "very_high"
    elif data_points >= 90 and mape < 25:
        label = "high"
    elif data_points >= 30 and mape < 40:
        label = "medium"
    elif data_points >= 14 or mape < 60:
        label = "low"
    else:
        label = "very_low"

    # Apply cap
    rank = ["very_low", "low", "medium", "high", "very_high"]
    if rank.index(label) > rank.index(cap):
        label = cap

    return label, "; ".join(parts)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_warehouse_ids(tenant_id, store_id, warehouse_id=None):
    """Return list of warehouse IDs for the given store (optionally filtered)."""
    filt = Q(store_id=store_id, tenant_id=tenant_id)
    if warehouse_id:
        filt &= Q(id=int(warehouse_id))
    return list(Warehouse.objects.filter(filt).values_list("id", flat=True))


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD KPIs
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard_kpis(tenant_id, warehouse_ids):
    """Return dict with forecast KPIs for the dashboard."""
    today = date.today()

    forecasts_7d = Forecast.objects.filter(
        tenant_id=tenant_id,
        warehouse_id__in=warehouse_ids,
        forecast_date__gt=today,
        forecast_date__lte=today + timedelta(days=7),
    )

    # Products at risk (stockout <= 7d)
    at_risk_7d = (
        forecasts_7d.filter(days_to_stockout__isnull=False, days_to_stockout__lte=7)
        .values("product_id").distinct().count()
    )
    imminent_3d = (
        forecasts_7d.filter(days_to_stockout__isnull=False, days_to_stockout__lte=3)
        .values("product_id").distinct().count()
    )

    # Value at risk
    at_risk_product_ids = list(
        forecasts_7d.filter(days_to_stockout__isnull=False, days_to_stockout__lte=7)
        .values_list("product_id", flat=True).distinct()
    )
    value_at_risk = D0
    if at_risk_product_ids:
        val = StockItem.objects.filter(
            tenant_id=tenant_id, warehouse_id__in=warehouse_ids,
            product_id__in=at_risk_product_ids,
        ).aggregate(total=Coalesce(Sum("stock_value"), Decimal("0")))
        value_at_risk = val["total"]

    # Model accuracy (from ForecastAccuracy if available, else from model metrics)
    from forecast.models import ForecastAccuracy
    active_models = ForecastModel.objects.filter(
        tenant_id=tenant_id, warehouse_id__in=warehouse_ids, is_active=True
    )
    model_count = active_models.count()

    # Try real accuracy from last 7 days
    recent_accuracy = ForecastAccuracy.objects.filter(
        tenant_id=tenant_id, warehouse_id__in=warehouse_ids,
        date__gte=today - timedelta(days=7),
        was_stockout=False,
        abs_pct_error__isnull=False,
    )
    real_accuracy_count = recent_accuracy.count()
    if real_accuracy_count >= 5:
        from django.db.models import Avg
        avg_mape = round(float(
            recent_accuracy.aggregate(avg=Avg("abs_pct_error"))["avg"] or 0
        ), 1)
    else:
        avg_mape = 0
        if model_count > 0:
            total_mape = 0
            counted = 0
            for fm in active_models:
                mape = (fm.metrics or {}).get("mape")
                if mape is not None:
                    total_mape += float(mape)
                    counted += 1
            avg_mape = round(total_mape / counted, 1) if counted > 0 else 0

    # Pending suggestions
    pending = PurchaseSuggestion.objects.filter(
        tenant_id=tenant_id, warehouse_id__in=warehouse_ids, status="PENDING"
    ).count()

    # Coverage
    products_with_forecast = active_models.values("product_id").distinct().count()
    total_active = Product.objects.filter(tenant_id=tenant_id, is_active=True).count()
    products_without = total_active - products_with_forecast
    coverage_pct = round(products_with_forecast / total_active * 100, 1) if total_active > 0 else 0

    # Margin at risk: sum of avg_daily_profit × days_at_risk for at-risk products
    margin_at_risk = Decimal("0.00")
    if at_risk_product_ids:
        margin_data = get_margin_data(tenant_id, at_risk_product_ids, warehouse_ids)
        # Bulk fetch min days_to_stockout per product (1 query instead of N)
        from django.db.models import Min
        stockout_qs = (
            Forecast.objects.filter(
                tenant_id=tenant_id, product_id__in=at_risk_product_ids,
                warehouse_id__in=warehouse_ids,
                forecast_date__gt=today, days_to_stockout__isnull=False,
            )
            .values("product_id")
            .annotate(min_stockout=Min("days_to_stockout"))
        )
        stockout_map = {row["product_id"]: row["min_stockout"] for row in stockout_qs}
        for pid in at_risk_product_ids:
            daily_profit = margin_data.get(pid, {}).get("avg_daily_profit", Decimal("0"))
            days_out = stockout_map.get(pid, None)
            if days_out is not None and daily_profit > 0:
                margin_at_risk += daily_profit * min(days_out, 7)

    return {
        "at_risk_7d": at_risk_7d,
        "imminent_3d": imminent_3d,
        "value_at_risk": str(value_at_risk.quantize(D2)),
        "margin_at_risk": str(margin_at_risk.quantize(D2)),
        "avg_mape": avg_mape,
        "model_count": model_count,
        "pending_suggestions": pending,
        "products_with_forecast": products_with_forecast,
        "products_without_forecast": products_without,
        "coverage_pct": coverage_pct,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MARGIN DATA
# ══════════════════════════════════════════════════════════════════════════════

def get_margin_data(tenant_id, product_ids, warehouse_ids, days=30):
    """
    Return margin stats per product from last N days of DailySales.
    Returns dict: {product_id: {avg_daily_profit, avg_margin_per_unit, total_profit}}
    """
    today = date.today()
    cutoff = today - timedelta(days=days)

    agg = (
        DailySales.objects.filter(
            tenant_id=tenant_id,
            product_id__in=product_ids,
            warehouse_id__in=warehouse_ids,
            date__gte=cutoff,
        )
        .values("product_id")
        .annotate(
            total_qty=Coalesce(Sum("qty_sold"), D0),
            total_profit=Coalesce(Sum("gross_profit"), Decimal("0.00")),
            day_count=Count("date", distinct=True),
        )
    )

    result = {}
    for row in agg:
        pid = row["product_id"]
        total_qty = row["total_qty"]
        total_profit = row["total_profit"]
        day_count = row["day_count"] or 1

        avg_daily_profit = (total_profit / day_count).quantize(D2)
        avg_margin_per_unit = (total_profit / total_qty).quantize(D2) if total_qty > 0 else Decimal("0.00")

        result[pid] = {
            "avg_daily_profit": avg_daily_profit,
            "avg_margin_per_unit": avg_margin_per_unit,
            "total_profit": total_profit,
        }
    return result


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT FORECAST LIST
# ══════════════════════════════════════════════════════════════════════════════

def get_product_forecasts(tenant_id, warehouse_ids, sort="stockout", page=1, page_size=50):
    """Return paginated list of products with forecast data."""
    today = date.today()

    models_qs = ForecastModel.objects.filter(
        tenant_id=tenant_id, warehouse_id__in=warehouse_ids, is_active=True
    ).select_related("product", "product__category")

    # Demand next 7 days
    demand_7d = dict(
        Forecast.objects.filter(
            tenant_id=tenant_id, warehouse_id__in=warehouse_ids,
            forecast_date__gt=today,
            forecast_date__lte=today + timedelta(days=7),
        )
        .values("product_id", "warehouse_id")
        .annotate(total=Coalesce(Sum("qty_predicted"), D0))
        .values_list("product_id", "total")
    )

    # Days to stockout
    stockout_map = {}
    for fc in (
        Forecast.objects.filter(
            tenant_id=tenant_id, warehouse_id__in=warehouse_ids,
            forecast_date=today + timedelta(days=1),
        ).values("product_id", "warehouse_id", "days_to_stockout")
    ):
        stockout_map[fc["product_id"]] = fc["days_to_stockout"]

    # Current stock
    stock_map = {
        si.product_id: si
        for si in StockItem.objects.filter(
            tenant_id=tenant_id, warehouse_id__in=warehouse_ids,
            product_id__in=[fm.product_id for fm in models_qs],
        )
    }

    # Recipe ingredients
    recipe_ingredient_ids = set(
        RecipeLine.objects.filter(
            tenant_id=tenant_id, recipe__is_active=True,
        ).values_list("ingredient_id", flat=True)
    )

    # Margin data (last 30 days)
    all_product_ids = [fm.product_id for fm in models_qs]
    margin_data = get_margin_data(tenant_id, all_product_ids, warehouse_ids) if all_product_ids else {}

    results = []
    for fm in models_qs:
        pid = fm.product_id
        si = stock_map.get(pid)
        d7 = demand_7d.get(pid, D0)
        days_out = stockout_map.get(pid)
        avg_daily = Decimal(fm.model_params.get("avg_daily", "0") if fm.model_params else "0")
        metrics = fm.metrics or {}
        pm = margin_data.get(pid, {})
        avg_margin = pm.get("avg_margin_per_unit", Decimal("0.00"))
        margin_7d = (avg_margin * d7).quantize(D2) if d7 > 0 else Decimal("0.00")

        results.append({
            "product_id": pid,
            "product_name": fm.product.name,
            "sku": fm.product.sku,
            "category": fm.product.category.name if fm.product.category else None,
            "warehouse_id": fm.warehouse_id,
            "on_hand": str(si.on_hand if si else D0),
            "avg_cost": str(si.avg_cost if si else D0),
            "avg_daily_demand": str(avg_daily),
            "demand_7d": str(d7),
            "days_to_stockout": days_out,
            "algorithm": fm.algorithm,
            "model_version": fm.version,
            "mape": metrics.get("mape"),
            "mae": metrics.get("mae"),
            "data_points": fm.data_points,
            "trained_at": fm.trained_at.isoformat(),
            "demand_pattern": fm.demand_pattern,
            "is_recipe_ingredient": pid in recipe_ingredient_ids,
            "avg_margin": str(avg_margin),
            "margin_7d": str(margin_7d),
        })

    # Sort
    def sort_key(r):
        dto = r["days_to_stockout"]
        if dto is None:
            dto = 9999
        if sort == "stockout":
            return dto
        elif sort == "demand":
            return -float(r["demand_7d"])
        elif sort == "margin":
            return -float(r["margin_7d"])
        else:
            return r["product_name"]

    results.sort(key=sort_key)

    # Paginate
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "results": results[start:end],
        "count": total,
        "page": page,
        "page_size": page_size,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT DETAIL
# ══════════════════════════════════════════════════════════════════════════════

def get_product_detail(tenant_id, product_id, warehouse_ids, history_days=30):
    """Return full time series (history + forecast) for a single product."""
    today = date.today()

    product = Product.objects.filter(tenant_id=tenant_id, id=product_id).first()
    if not product:
        return None

    history = list(
        DailySales.objects.filter(
            tenant_id=tenant_id, product_id=product_id,
            warehouse_id__in=warehouse_ids,
            date__gte=today - timedelta(days=history_days),
        )
        .order_by("date")
        .values("date", "qty_sold", "revenue", "qty_lost", "qty_received")
    )

    forecast = list(
        Forecast.objects.filter(
            tenant_id=tenant_id, product_id=product_id,
            warehouse_id__in=warehouse_ids,
            forecast_date__gt=today,
        )
        .order_by("forecast_date")
        .values("forecast_date", "qty_predicted", "lower_bound", "upper_bound",
                "days_to_stockout", "confidence")
    )

    si = StockItem.objects.filter(
        tenant_id=tenant_id, product_id=product_id, warehouse_id__in=warehouse_ids,
    ).first()

    fm = ForecastModel.objects.filter(
        tenant_id=tenant_id, product_id=product_id,
        warehouse_id__in=warehouse_ids, is_active=True
    ).first()

    # Pending suggestion for this product (if any)
    suggestion_info = None
    sl = (
        SuggestionLine.objects.filter(
            suggestion__tenant_id=tenant_id,
            suggestion__status="PENDING",
            suggestion__warehouse_id__in=warehouse_ids,
            product_id=product_id,
        )
        .select_related("suggestion")
        .first()
    )
    if sl:
        suggestion_info = {
            "suggested_qty": str(sl.suggested_qty),
            "target_days": sl.suggestion.target_days if hasattr(sl.suggestion, "target_days") else 14,
            "estimated_cost": str(sl.estimated_cost),
            "reasoning": sl.reasoning,
            "priority": sl.suggestion.priority,
        }

    # Compute smart target_days for this product (even without pending suggestion)
    if suggestion_info is None and fm and si:
        pm = get_margin_data(tenant_id, [product_id], list(warehouse_ids))
        margin_per_unit = float(pm.get(product_id, {}).get("avg_margin_per_unit", 0))
        avg_daily = float(fm.model_params.get("avg_daily", 0)) if fm.model_params else 0

        # Get medians from all active products for context
        all_pids = list(
            ForecastModel.objects.filter(tenant_id=tenant_id, is_active=True)
            .values_list("product_id", flat=True)
        )
        all_margin = get_margin_data(tenant_id, all_pids, list(warehouse_ids))
        margins = [float(v.get("avg_margin_per_unit", 0)) for v in all_margin.values() if float(v.get("avg_margin_per_unit", 0)) > 0]
        demands = [float(m.model_params.get("avg_daily", 0)) for m in ForecastModel.objects.filter(tenant_id=tenant_id, is_active=True) if m.model_params and float(m.model_params.get("avg_daily", 0)) > 0]

        med_margin = sorted(margins)[len(margins) // 2] if margins else 0
        med_daily = sorted(demands)[len(demands) // 2] if demands else 0

        smart_target = _compute_target_days(margin_per_unit, avg_daily, med_margin, med_daily)
        smart_qty = max(Decimal("0"), Decimal(str(avg_daily * smart_target)) - si.on_hand)

        suggestion_info = {
            "suggested_qty": str(smart_qty.quantize(Decimal("0.001"))),
            "target_days": smart_target,
            "estimated_cost": str((smart_qty * si.avg_cost).quantize(Decimal("0.01"))),
            "reasoning": None,
            "priority": None,
            "is_estimate": True,
        }

    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category.name if product.category else None,
        },
        "stock": {
            "on_hand": str(si.on_hand if si else D0),
            "avg_cost": str(si.avg_cost if si else D0),
            "stock_value": str(si.stock_value if si else D0),
        },
        "model": {
            "algorithm": fm.algorithm if fm else None,
            "version": fm.version if fm else None,
            "metrics": fm.metrics if fm else None,
            "data_points": fm.data_points if fm else 0,
            "trained_at": fm.trained_at.isoformat() if fm else None,
            "params": fm.model_params if fm else None,
            "demand_pattern": fm.demand_pattern if fm else None,
        } if fm else None,
        "suggestion": suggestion_info,
        "history": [
            {
                "date": str(h["date"]),
                "qty_sold": str(h["qty_sold"]),
                "revenue": str(h["revenue"]),
                "qty_lost": str(h["qty_lost"]),
                "qty_received": str(h["qty_received"]),
            }
            for h in history
        ],
        "forecast": [
            {
                "date": str(f["forecast_date"]),
                "qty_predicted": str(f["qty_predicted"]),
                "lower_bound": str(f["lower_bound"]),
                "upper_bound": str(f["upper_bound"]),
                "days_to_stockout": f["days_to_stockout"],
                "confidence": str(f["confidence"]),
            }
            for f in forecast
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# STOCKOUT ALERTS
# ══════════════════════════════════════════════════════════════════════════════

def get_stockout_alerts(tenant_id, warehouse_ids):
    """Return products with imminent stockout, sorted by urgency."""
    today = date.today()

    forecasts = (
        Forecast.objects.filter(
            tenant_id=tenant_id,
            warehouse_id__in=warehouse_ids,
            forecast_date=today + timedelta(days=1),
            days_to_stockout__isnull=False,
            days_to_stockout__lte=14,
        )
        .select_related("product", "product__category")
        .order_by("days_to_stockout")
    )

    stock_map = {
        (si.warehouse_id, si.product_id): si
        for si in StockItem.objects.filter(tenant_id=tenant_id, warehouse_id__in=warehouse_ids)
    }

    alerts = []
    seen = set()

    for fc in forecasts:
        key = (fc.product_id, fc.warehouse_id)
        if key in seen:
            continue
        seen.add(key)

        si = stock_map.get((fc.warehouse_id, fc.product_id))
        days = fc.days_to_stockout

        if days <= 3:
            level = "CRITICAL"
        elif days <= 7:
            level = "HIGH"
        else:
            level = "MEDIUM"

        alerts.append({
            "product_id": fc.product_id,
            "product_name": fc.product.name,
            "sku": fc.product.sku,
            "category": fc.product.category.name if fc.product.category else None,
            "warehouse_id": fc.warehouse_id,
            "on_hand": str(si.on_hand if si else D0),
            "days_to_stockout": days,
            "level": level,
            "qty_predicted_tomorrow": str(fc.qty_predicted),
        })

    return {
        "alerts": alerts,
        "count": len(alerts),
        "critical": sum(1 for a in alerts if a["level"] == "CRITICAL"),
        "high": sum(1 for a in alerts if a["level"] == "HIGH"),
        "medium": sum(1 for a in alerts if a["level"] == "MEDIUM"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_suggestions(tenant_id, status_filter=None, warehouse_id=None):
    """Return list of purchase suggestions."""
    qs = PurchaseSuggestion.objects.filter(tenant_id=tenant_id).order_by("-generated_at")

    if status_filter:
        qs = qs.filter(status=status_filter.upper())
    if warehouse_id:
        qs = qs.filter(warehouse_id=int(warehouse_id))

    results = []
    for s in qs[:50]:
        lines = list(
            SuggestionLine.objects.filter(suggestion=s)
            .select_related("product")
            .order_by("days_to_stockout")
        )
        results.append({
            "id": s.id,
            "warehouse_id": s.warehouse_id,
            "supplier_name": s.supplier_name,
            "status": s.status,
            "priority": s.priority,
            "total_estimated": str(s.total_estimated),
            "generated_at": s.generated_at.isoformat(),
            "approved_at": s.approved_at.isoformat() if s.approved_at else None,
            "purchase_id": s.purchase_id,
            "lines_count": len(lines),
            "lines": [
                {
                    "product_id": l.product_id,
                    "product_name": l.product.name,
                    "current_stock": str(l.current_stock),
                    "avg_daily_demand": str(l.avg_daily_demand),
                    "days_to_stockout": l.days_to_stockout,
                    "suggested_qty": str(l.suggested_qty),
                    "estimated_cost": str(l.estimated_cost),
                    "reasoning": l.reasoning,
                }
                for l in lines
            ],
        })
    return {"results": results, "count": len(results)}


# ══════════════════════════════════════════════════════════════════════════════
# TRAINING PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def _load_holidays_for_horizon(tenant, daily_forecasts):
    """Load holidays that fall within the forecast horizon."""
    from forecast.models import Holiday
    if not daily_forecasts:
        return []
    start = daily_forecasts[0]["date"]
    end = daily_forecasts[-1]["date"]
    return list(
        Holiday.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            date__gte=start - timedelta(days=5),  # include pre-days
            date__lte=end,
        )
    )


def save_forecasts(tenant, product, warehouse_id, fm, daily_forecasts,
                   confidence_base, stock_items):
    """Delete old forecasts, apply holiday adjustments, and bulk-insert."""
    # Apply holiday multipliers before saving
    holidays = _load_holidays_for_horizon(tenant, daily_forecasts)
    if holidays:
        apply_holiday_adjustments(daily_forecasts, holidays)

    # Apply confidence decay for stale models
    confidence_base = compute_confidence_decay(fm.trained_at, confidence_base)

    si = stock_items.get((warehouse_id, product.id))
    current_stock = si.on_hand if si else Decimal("0")
    # Low-confidence models use upper_bound for stockout → alerts fire earlier
    conservative = fm.confidence_label in ("very_low", "low")
    days_out = calculate_days_to_stockout(
        current_stock, daily_forecasts, conservative=conservative,
    )

    today = date.today()
    Forecast.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
        forecast_date__gt=today,
    ).delete()

    objs = []
    for fc in daily_forecasts:
        objs.append(Forecast(
            tenant=tenant,
            product=product,
            warehouse_id=warehouse_id,
            model=fm,
            forecast_date=fc["date"],
            qty_predicted=fc["qty_predicted"],
            lower_bound=fc["lower_bound"],
            upper_bound=fc["upper_bound"],
            days_to_stockout=days_out,
            confidence=confidence_base,
            generated_at=timezone.now(),
        ))
    Forecast.objects.bulk_create(objs)


@transaction.atomic
def train_product_model(tenant, product, warehouse_id, today,
                        min_days, horizon, window, stock_items, stats):
    """Train a forecast model for one product in one warehouse."""
    from forecast.models import ForecastAccuracy

    # Load raw series + stockout dates
    ds_qs = DailySales.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
    ).order_by("date")

    raw_data = list(ds_qs.values_list("date", "qty_sold", "promo_qty"))

    # Build series using organic demand (qty_sold - promo_qty)
    raw_series = []
    promo_dates = set()
    for dt, qty_sold, promo_qty in raw_data:
        promo_qty = promo_qty or Decimal("0")
        if promo_qty > qty_sold:
            logger.warning(
                "promo_qty (%s) > qty_sold (%s) on %s for product %s — clamping",
                promo_qty, qty_sold, dt, product.id,
            )
            promo_qty = qty_sold
        organic = qty_sold - promo_qty
        if promo_qty > 0:
            promo_dates.add(dt)
        raw_series.append((dt, max(organic, Decimal("0"))))

    if len(raw_series) < min_days:
        stats["skipped"] += 1
        return

    # Stockout dates for data cleaning (include promo-only days as pseudo-stockouts)
    stockout_dates = set(
        ds_qs.filter(is_stockout=True).values_list("date", flat=True)
    )
    # Days where ALL sales were promotional → treat as stockout for interpolation
    for dt, qty_sold, promo_qty in raw_data:
        if promo_qty and promo_qty >= qty_sold and qty_sold > 0:
            stockout_dates.add(dt)

    # Holiday dates — exclude from IQR so seasonal spikes survive
    from forecast.models import Holiday
    holiday_dates = set(
        Holiday.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            date__gte=raw_series[0][0],
            date__lte=raw_series[-1][0],
        ).values_list("date", flat=True)
    )

    # Clean series (impute stockout zeros, dampen outliers, preserve holidays)
    cleaned = clean_series(raw_series, stockout_dates=stockout_dates, holiday_dates=holiday_dates)

    # Demand pattern classification
    demand_pattern, adi, cv2 = classify_demand_pattern(raw_series)

    # Month-position factors (payday effect)
    month_factors = compute_month_position_factors(cleaned)

    # Select best model with cleaned data
    best = select_best_model(
        cleaned, window=window, horizon=horizon, test_days=7,
        month_factors=month_factors, demand_pattern=demand_pattern,
        stockout_dates=stockout_dates,
    )

    if best["algorithm"] == "none" or not best["forecasts"]:
        stats["skipped"] += 1
        return

    # Trend detection + adjustment
    trend = detect_trend(cleaned)
    if trend and best["forecasts"]:
        avg_daily = Decimal(best["params"].get("avg_daily", "0"))
        apply_trend_adjustment(best["forecasts"], trend, avg_daily)
        best["params"]["trend"] = trend

    # Bias correction from recent accuracy
    recent_acc = list(
        ForecastAccuracy.objects.filter(
            tenant=tenant, product=product, warehouse_id=warehouse_id,
            date__gte=today - timedelta(days=14),
        ).values("date", "error", "was_stockout")
    )
    if recent_acc and best["forecasts"]:
        avg_daily = Decimal(best["params"].get("avg_daily", "0"))
        correction = apply_bias_correction(best["forecasts"], recent_acc, avg_daily)
        if correction:
            best["params"]["bias_correction"] = correction

    # Monthly seasonality (180+ days)
    monthly_season = compute_monthly_seasonality(cleaned)
    if monthly_season and best["forecasts"]:
        apply_monthly_seasonality(best["forecasts"], monthly_season)
        best["params"]["monthly_seasonality"] = monthly_season

    # Year-over-year growth (365+ days)
    yoy = compute_yoy_growth(cleaned)
    if yoy and best["forecasts"]:
        apply_yoy_adjustment(best["forecasts"], yoy)
        best["params"]["yoy_growth"] = yoy

    # Price elasticity signal (informational, stored in params)
    revenue_series = list(ds_qs.values_list("date", "revenue"))
    price_info = detect_price_change_impact(raw_series, revenue_series)
    if price_info and price_info["is_price_sensitive"]:
        best["params"]["price_sensitivity"] = price_info

    # Compare with existing
    existing = ForecastModel.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
        is_active=True,
    ).first()

    if existing and existing.metrics:
        old_mape = existing.metrics.get("mape", 999)
        new_mape = best["metrics"]["mape"]
        if new_mape > old_mape * 1.1 and old_mape < 900:
            stats["kept"] += 1
            _regen_from_existing(
                tenant, product, warehouse_id, existing,
                today, horizon, window, cleaned, stock_items,
                stockout_dates=stockout_dates,
            )
            return

    # Compute confidence label
    conf_label, conf_reason = compute_confidence_label(
        best["data_points"], best["metrics"].get("mape", 999), demand_pattern,
    )

    # Compute mape_delta tracking
    _prev_mape = None
    _mape_delta = None
    _prev_algorithm = ""
    if existing and existing.metrics:
        _prev_mape = Decimal(str(existing.metrics.get("mape", 0))).quantize(D2)
        new_mape_d = Decimal(str(best["metrics"].get("mape", 0))).quantize(D2)
        _mape_delta = (new_mape_d - _prev_mape).quantize(D2)
        _prev_algorithm = existing.algorithm or ""

    # Save new model
    ForecastModel.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
        is_active=True,
    ).update(is_active=False)

    new_version = (existing.version + 1) if existing else 1

    fm = ForecastModel.objects.create(
        tenant=tenant,
        product=product,
        warehouse_id=warehouse_id,
        algorithm=best["algorithm"],
        version=new_version,
        model_params=best["params"],
        metrics=best["metrics"],
        trained_at=timezone.now(),
        data_points=best["data_points"],
        demand_pattern=demand_pattern,
        is_active=True,
        confidence_label=conf_label,
        confidence_reason=conf_reason,
        prev_mape=_prev_mape,
        mape_delta=_mape_delta,
        prev_algorithm=_prev_algorithm,
    )

    algo = best["algorithm"]
    stats["by_algo"][algo] = stats["by_algo"].get(algo, 0) + 1
    if existing:
        stats["improved"] += 1
    else:
        stats["trained"] += 1

    save_forecasts(tenant, product, warehouse_id, fm,
                   best["forecasts"], best["confidence_base"], stock_items)


@transaction.atomic
def train_sparse_product(tenant, product, warehouse_id, today,
                         horizon, stock_items, category_profiles, stats):
    """Train a category-prior model for a product with < min_days of data."""
    series = list(
        DailySales.objects.filter(
            tenant=tenant, product=product, warehouse_id=warehouse_id,
        ).order_by("date").values_list("date", "qty_sold")
    )

    # Find category profile
    cat_id = product.category_id
    profile = category_profiles.get((cat_id, warehouse_id)) if cat_id else None

    if profile is None:
        # Fallback: try tenant-wide average for this warehouse
        wh_profiles = [p for (c, w), p in category_profiles.items() if w == warehouse_id]
        if not wh_profiles:
            # Last resort: try ANY category profile in the tenant
            wh_profiles = list(category_profiles.values())
        if not wh_profiles:
            # No profiles at all — use a minimal default so new products
            # still get an initial model instead of being silently skipped
            logger.warning(
                "No category profiles for product=%s tenant=%s warehouse=%s — using 1.0 default",
                product.id, tenant.id, warehouse_id,
            )
            cat_avg = Decimal("1.000")  # 1 unit/day as safe minimum
            cat_dow = {}
        else:
            avg_demand = sum(float(p.avg_daily_demand) for p in wh_profiles) / len(wh_profiles)
            cat_avg = Decimal(str(avg_demand)).quantize(Decimal("0.001"))
            cat_dow = {}
    else:
        cat_avg = profile.avg_daily_demand
        cat_dow = profile.dow_factors or {}

    # Boost with recipe-derived demand if this is an ingredient
    recipe_demand = get_ingredient_forecast_boost(
        tenant.id, product.id, [warehouse_id]
    )
    if recipe_demand > 0:
        # Blend: max of category prior and recipe-derived demand
        cat_avg = max(cat_avg, Decimal(str(round(recipe_demand, 3))))

    if cat_avg <= 0:
        stats["skipped"] += 1
        return

    result = category_prior_forecast(series, cat_avg, cat_dow, horizon_days=horizon)

    if not result["forecasts"]:
        stats["skipped"] += 1
        return

    # Deactivate old model
    ForecastModel.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
        is_active=True,
    ).update(is_active=False)

    existing = ForecastModel.objects.filter(
        tenant=tenant, product=product, warehouse_id=warehouse_id,
    ).order_by("-version").first()
    new_version = (existing.version + 1) if existing else 1

    # Confidence label for sparse products
    sp_conf_label, sp_conf_reason = compute_confidence_label(
        result["data_points"], result["metrics"].get("mape", 999), "insufficient",
    )

    # MAPE delta tracking
    sp_prev_mape = None
    sp_mape_delta = None
    sp_prev_algo = ""
    if existing and existing.metrics:
        sp_prev_mape = Decimal(str(existing.metrics.get("mape", 0))).quantize(D2)
        sp_new_mape = Decimal(str(result["metrics"].get("mape", 0))).quantize(D2)
        sp_mape_delta = (sp_new_mape - sp_prev_mape).quantize(D2)
        sp_prev_algo = existing.algorithm or ""

    fm = ForecastModel.objects.create(
        tenant=tenant,
        product=product,
        warehouse_id=warehouse_id,
        algorithm="category_prior",
        version=new_version,
        model_params=result["params"],
        metrics=result["metrics"],
        trained_at=timezone.now(),
        data_points=result["data_points"],
        is_active=True,
        confidence_label=sp_conf_label,
        confidence_reason=sp_conf_reason,
        prev_mape=sp_prev_mape,
        mape_delta=sp_mape_delta,
        prev_algorithm=sp_prev_algo,
    )

    stats["by_algo"]["category_prior"] = stats["by_algo"].get("category_prior", 0) + 1
    stats["trained"] += 1

    save_forecasts(tenant, product, warehouse_id, fm,
                   result["forecasts"], result["confidence_base"], stock_items)


def _regen_from_existing(tenant, product, warehouse_id, fm,
                         today, horizon, window, series, stock_items,
                         stockout_dates=None):
    """Re-generate forecasts using an existing active model."""
    from forecast.engine import (
        weighted_moving_average, generate_daily_forecasts,
        holt_winters_forecast,
    )

    algo = fm.algorithm
    params = fm.model_params or {}

    if algo == "holt_winters":
        hw = holt_winters_forecast(series, horizon_days=horizon, stockout_dates=stockout_dates)
        if hw and hw["forecasts"]:
            forecasts = hw["forecasts"]
            conf = Decimal("80.00")
        else:
            ma = weighted_moving_average(series, window=window)
            forecasts = generate_daily_forecasts(
                ma["avg_daily"], ma["day_of_week_factors"], today, horizon
            )
            conf = Decimal("70.00")
    else:
        avg_daily = Decimal(params.get("avg_daily", "0"))
        dow_raw = params.get("dow_factors", {})
        dow_factors = {int(k): float(v) for k, v in dow_raw.items()}
        forecasts = generate_daily_forecasts(avg_daily, dow_factors, today, horizon)
        conf = Decimal("70.00")

    save_forecasts(tenant, product, warehouse_id, fm, forecasts, conf, stock_items)


# ══════════════════════════════════════════════════════════════════════════════
# PURCHASE SUGGESTION GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def _compute_target_days(margin_per_unit, avg_daily, median_margin, median_daily):
    """Compute reorder coverage days based on margin and rotation.

    High-margin slow-movers deserve more stock (21d).
    Low-margin fast-movers should minimize tied-up capital (10d).
    """
    high_margin = margin_per_unit > median_margin if median_margin > 0 else False
    high_rotation = avg_daily > median_daily if median_daily > 0 else False

    if high_margin and not high_rotation:
        return 21   # worth keeping extra stock
    if high_margin and high_rotation:
        return 14   # standard coverage
    if not high_margin and high_rotation:
        return 10   # minimize capital
    return 7        # low margin, low rotation — minimal stock


@transaction.atomic
def _safety_buffer(confidence_label: str) -> Decimal:
    """Return safety stock multiplier based on model confidence.

    Low-confidence models get a larger buffer so the user doesn't run
    out of stock while the model is still learning.
    """
    return {
        "very_low": Decimal("0.35"),
        "low":      Decimal("0.25"),
        "medium":   Decimal("0.15"),
        "high":     Decimal("0.08"),
        "very_high": Decimal("0.05"),
    }.get(confidence_label, Decimal("0.20"))


def generate_suggestions(tenant, today, threshold, target_days):
    """Generate purchase suggestions for at-risk products. Returns (n_suggestions, n_lines)."""
    from purchases.models import PurchaseLine

    active_models = ForecastModel.objects.filter(tenant=tenant, is_active=True)
    if not active_models.exists():
        return 0, 0

    # Build confidence lookup: (product_id, warehouse_id) → confidence_label
    confidence_map = {
        (m.product_id, m.warehouse_id): m.confidence_label
        for m in active_models.only("product_id", "warehouse_id", "confidence_label")
    }

    # Max coverage window (fetch enough forecast data for all tiers)
    max_target = 21

    # Future demand — fetch for max window, we'll filter per-product later
    future_forecasts_raw = list(
        Forecast.objects.filter(
            tenant=tenant,
            forecast_date__gt=today,
            forecast_date__lte=today + timedelta(days=max_target),
        )
        .values("product_id", "warehouse_id", "forecast_date",
                "qty_predicted", "upper_bound")
    )

    # Build per-product daily forecasts
    daily_forecasts = {}  # (pid, wid) -> [(date, qty, upper), ...]
    for row in future_forecasts_raw:
        key = (row["product_id"], row["warehouse_id"])
        daily_forecasts.setdefault(key, []).append(
            (row["forecast_date"], row["qty_predicted"], row["upper_bound"])
        )

    if not daily_forecasts:
        return 0, 0

    # Stock
    product_ids = set(k[0] for k in daily_forecasts)
    warehouse_ids = set(k[1] for k in daily_forecasts)
    stock_items = {
        (si.warehouse_id, si.product_id): si
        for si in StockItem.objects.filter(tenant=tenant, product_id__in=product_ids)
    }

    # Margin data for smart target_days
    margin_data = get_margin_data(tenant.id, list(product_ids), list(warehouse_ids))

    # Compute medians for relative thresholds
    all_margins = [
        float(m.get("avg_margin_per_unit", 0))
        for m in margin_data.values() if float(m.get("avg_margin_per_unit", 0)) > 0
    ]
    all_daily_demands = []
    for key, forecasts in daily_forecasts.items():
        if forecasts:
            total = sum(float(f[1]) for f in forecasts)  # f[1] = qty_predicted
            all_daily_demands.append(total / len(forecasts))

    median_margin = Decimal(str(sorted(all_margins)[len(all_margins) // 2])) if all_margins else Decimal("0")
    median_daily = sorted(all_daily_demands)[len(all_daily_demands) // 2] if all_daily_demands else 0

    # Days to stockout
    stockout_data = {}
    for key in daily_forecasts:
        pid, wid = key
        fc = (
            Forecast.objects.filter(
                tenant=tenant, product_id=pid, warehouse_id=wid,
                forecast_date__gt=today,
            )
            .order_by("forecast_date")
            .first()
        )
        if fc and fc.days_to_stockout is not None:
            stockout_data[key] = fc.days_to_stockout

    # Find at-risk products
    at_risk_lines = []
    for (pid, wid), forecasts in daily_forecasts.items():
        si = stock_items.get((wid, pid))
        current_stock = si.on_hand if si else Decimal("0")
        avg_cost = si.avg_cost if si else Decimal("0")
        days_out = stockout_data.get((pid, wid))

        # Model confidence determines safety buffer
        conf_label = confidence_map.get((pid, wid), "low")
        is_low_confidence = conf_label in ("very_low", "low")

        # Compute per-product target days based on margin/rotation
        pm = margin_data.get(pid, {})
        margin_per_unit = pm.get("avg_margin_per_unit", Decimal("0"))
        avg_daily_raw = sum(float(f[1]) for f in forecasts) / len(forecasts) if forecasts else 0
        product_target = _compute_target_days(
            float(margin_per_unit), avg_daily_raw, float(median_margin), median_daily
        )

        # Sum demand for this product's target window only
        # For low-confidence models use upper_bound (pessimistic) to avoid stockouts
        cutoff = today + timedelta(days=product_target)
        if is_low_confidence:
            total_demand = sum(
                f[2] for f in forecasts if f[0] <= cutoff  # f[2] = upper_bound
            )
        else:
            total_demand = sum(
                f[1] for f in forecasts if f[0] <= cutoff  # f[1] = qty_predicted
            )
        if not isinstance(total_demand, Decimal):
            total_demand = Decimal(str(total_demand))

        if days_out is None:
            if current_stock >= total_demand:
                continue
            days_out = product_target

        if days_out > threshold:
            continue

        # Base suggested quantity
        base_qty = max(Decimal("0"), total_demand - current_stock)
        if base_qty <= 0:
            continue

        # Safety stock buffer — larger when model is less certain
        buffer_pct = _safety_buffer(conf_label)
        safety_qty = (base_qty * buffer_pct).quantize(Decimal("0.001"))
        suggested_qty = base_qty + safety_qty

        # Minimum 1 unit (never suggest fractional sub-unit orders)
        from math import ceil
        suggested_qty = max(Decimal("1"), Decimal(str(ceil(float(suggested_qty)))))

        avg_daily = (total_demand / Decimal(str(product_target))).quantize(Decimal("0.001"))

        # Adjust priority thresholds: low-confidence models alert earlier
        critical_threshold = 5 if is_low_confidence else 3
        high_threshold = 10 if is_low_confidence else 7

        if days_out <= critical_threshold:
            priority = "CRITICAL"
        elif days_out <= high_threshold:
            priority = "HIGH"
        elif days_out <= 14:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        high_margin = float(margin_per_unit) > float(median_margin) if median_margin > 0 else False
        high_rotation = avg_daily_raw > median_daily if median_daily > 0 else False
        margin_label = "alto" if high_margin else "bajo"
        rotation_label = "alta" if high_rotation else "baja"

        buffer_note = ""
        if buffer_pct > Decimal("0.10"):
            buffer_note = (
                f" Incluye +{int(buffer_pct * 100)}% de seguridad "
                f"(modelo en fase de aprendizaje)."
            )

        at_risk_lines.append({
            "product_id": pid,
            "warehouse_id": wid,
            "current_stock": current_stock,
            "avg_daily_demand": avg_daily,
            "days_to_stockout": days_out,
            "suggested_qty": suggested_qty.quantize(Decimal("0.001")),
            "estimated_cost": (suggested_qty * avg_cost).quantize(Decimal("0.01")),
            "priority": priority,
            "target_days": product_target,
            "reasoning": (
                f"Stock actual: {current_stock}. "
                f"Demanda {product_target}d: {total_demand.quantize(Decimal('0.001'))}. "
                f"Quiebre en ~{days_out} día(s). "
                f"Margen {margin_label}, rotación {rotation_label} → cobertura {product_target} días. "
                f"Pedir {suggested_qty.quantize(Decimal('0.001'))} unidades."
                f"{buffer_note}"
            ),
        })

    if not at_risk_lines:
        return 0, 0

    # Group by warehouse
    by_warehouse = {}
    for line in at_risk_lines:
        by_warehouse.setdefault(line["warehouse_id"], []).append(line)

    # Dismiss old pending
    PurchaseSuggestion.objects.filter(
        tenant=tenant, status="PENDING"
    ).update(status="DISMISSED")

    suggestion_count = 0
    line_count = 0

    for wid, lines in by_warehouse.items():
        priorities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        worst = max(lines, key=lambda l: priorities.index(l["priority"]) * -1)
        overall_priority = worst["priority"]

        supplier = _find_best_supplier(tenant, [l["product_id"] for l in lines])

        total_cost = sum(l["estimated_cost"] for l in lines)

        suggestion = PurchaseSuggestion.objects.create(
            tenant=tenant,
            warehouse_id=wid,
            supplier_name=supplier,
            status="PENDING",
            priority=overall_priority,
            total_estimated=total_cost,
            generated_at=timezone.now(),
        )

        for line in lines:
            SuggestionLine.objects.create(
                suggestion=suggestion,
                product_id=line["product_id"],
                current_stock=line["current_stock"],
                avg_daily_demand=line["avg_daily_demand"],
                days_to_stockout=line["days_to_stockout"],
                suggested_qty=line["suggested_qty"],
                estimated_cost=line["estimated_cost"],
                reasoning=line["reasoning"],
            )
            line_count += 1

        suggestion_count += 1

    return suggestion_count, line_count


def _find_best_supplier(tenant, product_ids):
    """Find the most frequent supplier for a set of products."""
    from purchases.models import PurchaseLine

    result = (
        PurchaseLine.objects.filter(
            tenant=tenant, product_id__in=product_ids,
            purchase__status__in=["CONFIRMED", "RECEIVED"],
        )
        .values("purchase__supplier_name")
        .annotate(count=Sum("qty"))
        .order_by("-count")
        .first()
    )
    if result and result["purchase__supplier_name"]:
        return result["purchase__supplier_name"]
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# RECIPE-DRIVEN DEMAND
# ══════════════════════════════════════════════════════════════════════════════

def compute_ingredient_demand(tenant_id, warehouse_ids):
    """
    For ingredients that are only consumed through recipes (not sold directly),
    derive their forecast from the parent product's forecast × recipe qty.

    Returns dict: {ingredient_id: derived_avg_daily_demand}
    """
    # Find all active recipe lines
    recipe_lines = list(
        RecipeLine.objects.filter(
            tenant_id=tenant_id,
            recipe__is_active=True,
        ).select_related("recipe").values(
            "ingredient_id",
            "recipe__product_id",
            "qty",
        )
    )

    if not recipe_lines:
        return {}

    # Get parent product forecasts (avg_daily from model params)
    parent_ids = set(rl["recipe__product_id"] for rl in recipe_lines)
    parent_demand = {}
    for fm in ForecastModel.objects.filter(
        tenant_id=tenant_id,
        warehouse_id__in=warehouse_ids,
        product_id__in=parent_ids,
        is_active=True,
    ):
        params = fm.model_params or {}
        avg_daily = float(params.get("avg_daily", 0))
        if avg_daily > 0:
            parent_demand[fm.product_id] = avg_daily

    # Derive ingredient demand
    ingredient_demand = {}
    for rl in recipe_lines:
        parent_avg = parent_demand.get(rl["recipe__product_id"], 0)
        if parent_avg <= 0:
            continue
        ingr_id = rl["ingredient_id"]
        derived = parent_avg * float(rl["qty"])
        ingredient_demand[ingr_id] = ingredient_demand.get(ingr_id, 0) + derived

    return ingredient_demand


def get_ingredient_forecast_boost(tenant_id, product_id, warehouse_ids):
    """
    Check if a product is an ingredient and return the derived demand
    from parent recipes. Used to supplement sparse-data forecasts.
    """
    demand = compute_ingredient_demand(tenant_id, warehouse_ids)
    return demand.get(product_id, 0)
