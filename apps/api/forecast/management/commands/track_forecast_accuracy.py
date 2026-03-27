"""
track_forecast_accuracy
=======================
Runs after aggregate_daily_sales. Compares yesterday's forecast vs actual sales.

Usage:
    python manage.py track_forecast_accuracy              # yesterday
    python manage.py track_forecast_accuracy --date 2026-02-20
    python manage.py track_forecast_accuracy --days 7     # backfill
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import Tenant
from forecast.models import DailySales, Forecast, ForecastAccuracy, Holiday


class Command(BaseCommand):
    help = "Track forecast accuracy: compare predicted vs actual for completed days"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="Specific date YYYY-MM-DD")
        parser.add_argument("--days", type=int, default=1, help="Days to backfill")
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")

    def handle(self, *args, **options):
        if options["date"]:
            days_to_process = [date.fromisoformat(options["date"])]
        else:
            num_days = max(1, options["days"])
            today = date.today()
            days_to_process = [today - timedelta(days=i) for i in range(1, num_days + 1)]

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total = 0
        for tenant in tenants:
            for d in days_to_process:
                total += self._track_day(tenant, d)

        self.stdout.write(self.style.SUCCESS(f"Tracked {total} accuracy records"))

    def _track_day(self, tenant, target_date):
        """Compare forecasts vs actuals for one tenant on one day."""
        # Get all forecasts that were made for this date
        forecasts = Forecast.objects.filter(
            tenant=tenant,
            forecast_date=target_date,
        ).select_related("model")

        if not forecasts.exists():
            return 0

        # Get actual sales for this date
        actuals = {
            (ds.product_id, ds.warehouse_id): ds
            for ds in DailySales.objects.filter(
                tenant=tenant, date=target_date,
            )
        }

        created = 0
        for fc in forecasts:
            key = (fc.product_id, fc.warehouse_id)
            ds = actuals.get(key)

            qty_actual = ds.qty_sold if ds else Decimal("0.000")
            qty_predicted = fc.qty_predicted
            error = qty_predicted - qty_actual
            was_stockout = ds.is_stockout if ds else False

            abs_pct = None
            if qty_actual > 0:
                abs_pct = (abs(error) / qty_actual * 100).quantize(Decimal("0.01"))

            _, was_created = ForecastAccuracy.objects.update_or_create(
                tenant=tenant,
                product_id=fc.product_id,
                warehouse_id=fc.warehouse_id,
                date=target_date,
                defaults={
                    "qty_predicted": qty_predicted,
                    "qty_actual": qty_actual,
                    "error": error,
                    "abs_pct_error": abs_pct,
                    "algorithm": fc.model.algorithm if fc.model else "",
                    "was_stockout": was_stockout,
                },
            )
            if was_created:
                created += 1

        # Learn holiday multipliers from actual data
        self._learn_holiday_multipliers(tenant, target_date, actuals)

        return created

    def _learn_holiday_multipliers(self, tenant, target_date, actuals_map):
        """If target_date was a holiday, compute actual multiplier from data."""
        from django.db.models import Q

        holidays = Holiday.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True),
            date=target_date,
        )

        if not holidays.exists():
            return

        # Get average daily demand for the week before the holiday
        week_before_start = target_date - timedelta(days=14)
        week_before_end = target_date - timedelta(days=1)

        avg_demand = {}
        for ds in DailySales.objects.filter(
            tenant=tenant,
            date__gte=week_before_start,
            date__lte=week_before_end,
            is_stockout=False,
        ).values("product_id", "warehouse_id"):
            key = (ds["product_id"], ds["warehouse_id"])
            avg_demand.setdefault(key, [])

        # Need to re-query with qty
        baseline_qs = (
            DailySales.objects.filter(
                tenant=tenant,
                date__gte=week_before_start,
                date__lte=week_before_end,
                is_stockout=False,
            )
        )
        from django.db.models import Avg
        baseline = baseline_qs.aggregate(avg_qty=Avg("qty_sold"))
        baseline_avg = float(baseline["avg_qty"] or 0)

        if baseline_avg <= 0:
            return

        # Actual demand on holiday
        holiday_total = sum(
            float(ds.qty_sold) for ds in actuals_map.values()
        )
        n_products = len(actuals_map) or 1
        holiday_avg = holiday_total / n_products

        learned = round(holiday_avg / baseline_avg, 2) if baseline_avg > 0 else 1.0
        # Clamp to reasonable range
        learned = max(0.5, min(3.0, learned))

        for h in holidays:
            h.learned_multiplier = Decimal(str(learned))
            h.last_actual_date = target_date
            h.save(update_fields=["learned_multiplier", "last_actual_date"])
