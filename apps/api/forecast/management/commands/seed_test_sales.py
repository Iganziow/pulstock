"""
seed_test_sales
===============
Generates realistic sales data for testing the forecast module.

Creates 30-45 days of simulated sales with:
- Weekly seasonality (Mon-Thu normal, Fri-Sat peak, Sun low)
- Random variation per product
- Proper Sale + SaleLine + StockMove records
- StockItem receives to ensure positive stock

Usage:
    python manage.py seed_test_sales                      # 30 days, all products
    python manage.py seed_test_sales --days 45            # 45 days
    python manage.py seed_test_sales --tenant 1           # specific tenant
    python manage.py seed_test_sales --max-products 20    # limit products
"""
import random
from datetime import date, timedelta, datetime, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, F
from django.utils import timezone

from core.models import Tenant, User, Warehouse
from catalog.models import Product
from inventory.models import StockItem, StockMove
from sales.models import Sale, SaleLine
from stores.models import Store


# Day-of-week demand multipliers (0=Mon ... 6=Sun)
DOW_FACTORS = {
    0: 0.85,   # Lunes: bajo
    1: 0.90,   # Martes
    2: 1.00,   # Miércoles
    3: 1.00,   # Jueves
    4: 1.25,   # Viernes: alto
    5: 1.40,   # Sábado: peak
    6: 0.60,   # Domingo: bajo
}

# Product demand profiles (daily units range)
DEMAND_PROFILES = [
    {"name": "alto",    "min": 5,  "max": 15, "weight": 0.2},
    {"name": "medio",   "min": 2,  "max": 8,  "weight": 0.5},
    {"name": "bajo",    "min": 0,  "max": 3,  "weight": 0.3},
]


class Command(BaseCommand):
    help = "Seed realistic test sales data for forecast module testing"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Number of days of history (default: 30)")
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--max-products", type=int, default=50, help="Max products to generate sales for")
        parser.add_argument("--dry-run", action="store_true", help="Print summary without writing to DB")

    def handle(self, *args, **options):
        days = max(14, options["days"])
        max_prods = options["max_products"]
        dry_run = options["dry_run"]

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        for tenant in tenants:
            self._seed_tenant(tenant, days, max_prods, dry_run)

    @transaction.atomic
    def _seed_tenant(self, tenant, days, max_prods, dry_run):
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Tenant: {tenant.id} — {getattr(tenant, 'name', '')}")
        self.stdout.write(f"{'='*60}")

        # Get user, store, warehouse
        user = User.objects.filter(tenant=tenant).first()
        if not user:
            self.stdout.write(self.style.WARNING("  No users found, skipping"))
            return

        store = Store.objects.filter(tenant=tenant).first()
        if not store:
            self.stdout.write(self.style.WARNING("  No stores found, skipping"))
            return

        warehouse = Warehouse.objects.filter(tenant=tenant, store=store).first()
        if not warehouse:
            warehouse = Warehouse.objects.filter(tenant=tenant).first()
        if not warehouse:
            self.stdout.write(self.style.WARNING("  No warehouses found, skipping"))
            return

        products = list(
            Product.objects.filter(tenant=tenant, is_active=True)
            .order_by("id")[:max_prods]
        )
        if not products:
            self.stdout.write(self.style.WARNING("  No active products found, skipping"))
            return

        self.stdout.write(f"  User: {user.username}")
        self.stdout.write(f"  Store: {store.id} — {store.name}")
        self.stdout.write(f"  Warehouse: {warehouse.id} — {warehouse.name}")
        self.stdout.write(f"  Products: {len(products)}")
        self.stdout.write(f"  Days: {days}")

        # Assign demand profile to each product
        product_profiles = {}
        for p in products:
            r = random.random()
            cumulative = 0
            for profile in DEMAND_PROFILES:
                cumulative += profile["weight"]
                if r <= cumulative:
                    product_profiles[p.id] = profile
                    break

        today = date.today()
        start_date = today - timedelta(days=days)

        total_sales = 0
        total_lines = 0
        total_revenue = Decimal("0")

        # ── STEP 1: Ensure stock exists (big initial receive) ──
        self.stdout.write("\n  📦 Creating initial stock...")
        for p in products:
            profile = product_profiles[p.id]
            # Enough stock for the whole period + buffer
            initial_qty = Decimal(str(profile["max"] * days * 2))
            cost = Decimal(str(p.cost or "500")).quantize(Decimal("0.01"))
            if cost <= 0:
                cost = Decimal("500.00")

            si, created = StockItem.objects.get_or_create(
                tenant=tenant, warehouse=warehouse, product=p,
                defaults={
                    "on_hand": initial_qty,
                    "avg_cost": cost,
                    "stock_value": (initial_qty * cost).quantize(Decimal("0.01")),
                },
            )
            if not created:
                # Add to existing stock
                StockItem.objects.filter(id=si.id).update(
                    on_hand=initial_qty,
                    avg_cost=cost,
                    stock_value=(initial_qty * cost).quantize(Decimal("0.01")),
                )

            # Create receive StockMove for traceability
            StockMove.objects.create(
                tenant=tenant,
                warehouse=warehouse,
                product=p,
                move_type="IN",
                qty=initial_qty,
                unit_cost=cost,
                ref_type="RECEIVE",
                ref_id=None,
                note="Stock inicial para prueba de forecast",
                created_by=user,
                cost_snapshot=cost,
                value_delta=(initial_qty * cost).quantize(Decimal("0.001")),
                reason="",
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n  [DRY RUN] Would generate sales, exiting."))
            return

        # ── STEP 2: Generate daily sales ──
        self.stdout.write("  🛒 Generating sales...")

        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            dow = current_date.weekday()
            dow_factor = DOW_FACTORS[dow]

            # Random hour for the "sale time" (business hours 9-20)
            sale_hour = random.randint(9, 20)
            sale_dt = timezone.make_aware(
                datetime.combine(current_date, time(sale_hour, random.randint(0, 59)))
            )

            # Each product may or may not have a sale today
            day_lines = []
            for p in products:
                profile = product_profiles[p.id]
                base_demand = random.uniform(profile["min"], profile["max"])
                adjusted = base_demand * dow_factor

                # Add some randomness (±30%)
                noise = random.uniform(0.7, 1.3)
                qty_f = adjusted * noise

                # Some days have 0 sales for this product
                if qty_f < 0.5:
                    continue

                qty = Decimal(str(round(qty_f, 0)))
                if qty <= 0:
                    continue

                price = Decimal(str(p.price or "1000")).quantize(Decimal("0.01"))
                if price <= 0:
                    price = Decimal("1000.00")

                cost = Decimal(str(p.cost or "500")).quantize(Decimal("0.01"))
                if cost <= 0:
                    cost = Decimal("500.00")

                day_lines.append({
                    "product": p,
                    "qty": qty,
                    "price": price,
                    "cost": cost,
                })

            if not day_lines:
                continue

            # Create one sale per day with all lines
            sale_total = sum(l["qty"] * l["price"] for l in day_lines)
            sale_cost = sum(l["qty"] * l["cost"] for l in day_lines)

            sale = Sale.objects.create(
                tenant=tenant,
                store=store,
                warehouse=warehouse,
                created_by=user,
                created_at=sale_dt,
                subtotal=sale_total.quantize(Decimal("0.01")),
                total=sale_total.quantize(Decimal("0.01")),
                total_cost=sale_cost.quantize(Decimal("0.001")),
                gross_profit=(sale_total - sale_cost).quantize(Decimal("0.001")),
                status="COMPLETED",
            )

            for l in day_lines:
                line_total = (l["qty"] * l["price"]).quantize(Decimal("0.01"))
                line_cost = (l["qty"] * l["cost"]).quantize(Decimal("0.001"))

                SaleLine.objects.create(
                    sale=sale,
                    tenant=tenant,
                    product=l["product"],
                    qty=l["qty"],
                    unit_price=l["price"],
                    line_total=line_total,
                    unit_cost_snapshot=l["cost"],
                    line_cost=line_cost,
                    line_gross_profit=(line_total - line_cost).quantize(Decimal("0.001")),
                )

                # Create OUT StockMove for the sale
                StockMove.objects.create(
                    tenant=tenant,
                    warehouse=warehouse,
                    product=l["product"],
                    move_type="OUT",
                    qty=l["qty"],
                    ref_type="SALE",
                    ref_id=sale.id,
                    note=f"Sale #{sale.id}",
                    created_by=user,
                    cost_snapshot=l["cost"],
                    value_delta=(-line_cost).quantize(Decimal("0.001")),
                    reason="",
                )

                # Decrement stock
                StockItem.objects.filter(
                    tenant=tenant, warehouse=warehouse, product=l["product"]
                ).update(
                    on_hand=F("on_hand") - l["qty"],
                    stock_value=F("stock_value") - line_cost,
                )

                total_lines += 1

            total_sales += 1
            total_revenue += sale_total

        # ── Summary ──
        self.stdout.write(f"\n  ✅ Created:")
        self.stdout.write(f"     {total_sales} sales")
        self.stdout.write(f"     {total_lines} sale lines")
        self.stdout.write(f"     ${total_revenue:,.0f} revenue total")
        self.stdout.write(f"     Period: {start_date} → {today - timedelta(days=1)}")

        # Show per-product summary
        self.stdout.write(f"\n  📊 Sample product breakdown:")
        sample = random.sample(products, min(5, len(products)))
        for p in sample:
            lines = SaleLine.objects.filter(
                tenant=tenant, product=p,
                sale__created_at__date__gte=start_date,
            )
            total_qty = lines.aggregate(t=Sum("qty"))["t"] or 0
            days_with_sales = lines.values("sale__created_at__date").distinct().count()
            si = StockItem.objects.filter(tenant=tenant, warehouse=warehouse, product=p).first()
            stock = si.on_hand if si else 0
            profile = product_profiles[p.id]
            self.stdout.write(
                f"     {p.name[:30]:30s} | perfil={profile['name']:5s} | "
                f"vendido={total_qty:6.0f} | días={days_with_sales:2d} | stock={stock:6.0f}"
            )

        self.stdout.write(f"\n  🚀 Ahora ejecuta:")
        self.stdout.write(f"     python manage.py aggregate_daily_sales --days {days}")
        self.stdout.write(f"     python manage.py train_forecast_models")
        self.stdout.write(f"     python manage.py generate_purchase_suggestions")