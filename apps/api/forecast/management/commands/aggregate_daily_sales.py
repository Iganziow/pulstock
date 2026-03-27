"""
aggregate_daily_sales
=====================
Nightly cron (02:00): aggregates SaleLines and StockMoves into DailySales.

Usage:
    python manage.py aggregate_daily_sales              # yesterday
    python manage.py aggregate_daily_sales --date 2026-02-20
    python manage.py aggregate_daily_sales --days 30    # backfill last 30 days
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from core.models import Tenant
from inventory.models import StockMove, StockItem
from sales.models import SaleLine
from catalog.models import RecipeLine
from forecast.models import DailySales


class Command(BaseCommand):
    help = "Aggregate daily sales, losses and receipts into DailySales table"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="Specific date YYYY-MM-DD (default: yesterday)")
        parser.add_argument("--days", type=int, default=1, help="Number of days to backfill (default: 1 = yesterday)")
        parser.add_argument("--tenant", type=int, help="Specific tenant ID (default: all)")

    def handle(self, *args, **options):
        target_date = None
        if options["date"]:
            target_date = date.fromisoformat(options["date"])
            days_to_process = [target_date]
        else:
            num_days = max(1, options["days"])
            today = date.today()
            days_to_process = [today - timedelta(days=i) for i in range(1, num_days + 1)]

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total_created = 0
        total_updated = 0

        for tenant in tenants:
            for d in days_to_process:
                created, updated = self._aggregate_day(tenant, d)
                total_created += created
                total_updated += updated

        self.stdout.write(self.style.SUCCESS(
            f"Done: {total_created} created, {total_updated} updated across {len(days_to_process)} day(s)"
        ))

    def _aggregate_day(self, tenant, target_date):
        """Aggregate all sales, losses, and receipts for one tenant on one day."""
        created = 0
        updated = 0

        # ── Sales: SaleLine grouped by product + warehouse ──
        sale_agg = (
            SaleLine.objects.filter(
                tenant=tenant,
                sale__created_at__date=target_date,
            )
            .values("product_id", "sale__warehouse_id")
            .annotate(
                total_qty=Coalesce(Sum("qty"), Decimal("0.000")),
                total_revenue=Coalesce(Sum("line_total"), Decimal("0.00")),
                total_cost=Coalesce(Sum("line_cost"), Decimal("0.00")),
            )
        )

        # Build a map: (product_id, warehouse_id) -> {qty_sold, revenue}
        sales_map = {}
        for row in sale_agg:
            key = (row["product_id"], row["sale__warehouse_id"])
            revenue = row["total_revenue"] or Decimal("0.00")
            cost = row["total_cost"] or Decimal("0.00")
            sales_map[key] = {
                "qty_sold": row["total_qty"] or Decimal("0.000"),
                "revenue": revenue,
                "total_cost": cost,
                "gross_profit": revenue - cost,
            }

        # ── Promotional sales: SaleLines with promotion set ──
        promo_agg = (
            SaleLine.objects.filter(
                tenant=tenant,
                sale__created_at__date=target_date,
                promotion__isnull=False,
            )
            .values("product_id", "sale__warehouse_id")
            .annotate(
                promo_qty=Coalesce(Sum("qty"), Decimal("0.000")),
                promo_revenue=Coalesce(Sum("line_total"), Decimal("0.00")),
            )
        )
        promo_map = {}
        for row in promo_agg:
            key = (row["product_id"], row["sale__warehouse_id"])
            promo_map[key] = {
                "promo_qty": row["promo_qty"] or Decimal("0.000"),
                "promo_revenue": row["promo_revenue"] or Decimal("0.00"),
            }

        # ── Losses: StockMoves OUT with ref_type=ISSUE ──
        loss_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="OUT",
                ref_type="ISSUE",
            )
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        loss_map = {}
        for row in loss_agg:
            key = (row["product_id"], row["warehouse_id"])
            loss_map[key] = row["total_qty"] or Decimal("0.000")

        # ── Receipts: StockMoves IN with ref_type=RECEIVE ──
        recv_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="IN",
                ref_type="RECEIVE",
            )
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        recv_map = {}
        for row in recv_agg:
            key = (row["product_id"], row["warehouse_id"])
            recv_map[key] = row["total_qty"] or Decimal("0.000")

        # ── Merge all keys ──
        all_keys = set(sales_map.keys()) | set(loss_map.keys()) | set(recv_map.keys())

        for product_id, warehouse_id in all_keys:
            sale_data = sales_map.get((product_id, warehouse_id), {})
            qty_sold = sale_data.get("qty_sold", Decimal("0.000"))
            revenue = sale_data.get("revenue", Decimal("0.00"))
            total_cost = sale_data.get("total_cost", Decimal("0.00"))
            gross_profit = sale_data.get("gross_profit", Decimal("0.00"))
            qty_lost = loss_map.get((product_id, warehouse_id), Decimal("0.000"))
            qty_received = recv_map.get((product_id, warehouse_id), Decimal("0.000"))
            promo_data = promo_map.get((product_id, warehouse_id), {})

            obj, was_created = DailySales.objects.update_or_create(
                tenant=tenant,
                product_id=product_id,
                warehouse_id=warehouse_id,
                date=target_date,
                defaults={
                    "qty_sold": qty_sold,
                    "revenue": revenue,
                    "total_cost": total_cost,
                    "gross_profit": gross_profit,
                    "qty_lost": qty_lost,
                    "qty_received": qty_received,
                    "promo_qty": promo_data.get("promo_qty", Decimal("0.000")),
                    "promo_revenue": promo_data.get("promo_revenue", Decimal("0.00")),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # ── Closing stock + stockout detection ──
        # Snapshot stock at end of day for all products with activity.
        # If this is yesterday's aggregation, use current StockItem.on_hand as proxy.
        # For backfills, closing_stock is approximated.
        from datetime import date as date_cls
        today = date_cls.today()
        is_recent = (today - target_date).days <= 2

        if is_recent:
            stock_qs = StockItem.objects.filter(
                tenant=tenant,
                product_id__in={pid for (pid, _) in all_keys},
            ).values("product_id", "warehouse_id", "on_hand")
            stock_snapshot = {
                (r["product_id"], r["warehouse_id"]): r["on_hand"]
                for r in stock_qs
            }

            for product_id, warehouse_id in all_keys:
                closing = stock_snapshot.get((product_id, warehouse_id))
                if closing is None:
                    continue
                qty_sold = sales_map.get((product_id, warehouse_id), {}).get(
                    "qty_sold", Decimal("0.000")
                )
                # Stockout heuristic: stock is zero AND qty_sold was near-zero
                is_stockout = (
                    closing <= Decimal("0.000") and qty_sold <= Decimal("0.500")
                )
                DailySales.objects.filter(
                    tenant=tenant,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    date=target_date,
                ).update(closing_stock=closing, is_stockout=is_stockout)

        # ── PASO 2: ingredientes puros de recetas ──────────────────────────────
        # Productos que son ingredientes en recetas activas pero que NO se venden
        # directamente (no aparecen en SaleLine). Su consumo queda en StockMove OUT
        # con ref_type="SALE", generado por la expansión de receta en create_sale().

        ingredient_ids = set(
            RecipeLine.objects.filter(
                tenant=tenant,
                recipe__is_active=True,
            ).values_list("ingredient_id", flat=True)
        )

        # Warehouses que tuvieron actividad de venta ese día (para distribuir correctamente)
        sale_warehouses = set(wh for (_, wh) in all_keys)

        # Para cada ingrediente puro (no vendido directamente), agregar por bodega
        direct_sold_ids = {pid for (pid, _) in sales_map}
        pure_ingredient_ids = ingredient_ids - direct_sold_ids

        if pure_ingredient_ids:
            ingredient_agg = (
                StockMove.objects.filter(
                    tenant=tenant,
                    created_at__date=target_date,
                    move_type="OUT",
                    ref_type="SALE",
                    product_id__in=pure_ingredient_ids,
                )
                .values("product_id", "warehouse_id")
                .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
            )
            for row in ingredient_agg:
                pid = row["product_id"]
                wh_id = row["warehouse_id"]
                qty = row["total_qty"] or Decimal("0.000")
                if qty <= 0:
                    continue
                obj, was_created = DailySales.objects.update_or_create(
                    tenant=tenant,
                    product_id=pid,
                    warehouse_id=wh_id,
                    date=target_date,
                    defaults={
                        "qty_sold": qty,
                        "revenue": Decimal("0.00"),
                        "qty_lost": Decimal("0.000"),
                        "qty_received": Decimal("0.000"),
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        return created, updated
