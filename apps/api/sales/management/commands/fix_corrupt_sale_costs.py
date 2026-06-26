"""
fix_corrupt_sale_costs
======================
Recalcula el costo de ventas con costo CORRUPTO (total_cost > total con
total > 0), causado por el bug de unidades en el costeo del período temprano
(costos inflados ~100×). Para cada línea recalcula:

    unit_cost_snapshot ← costo actual del producto (StockItem.avg_cost de la
                          bodega de la venta; fallback Product.cost)
    line_cost          ← qty × unit_cost_snapshot
    line_gross_profit  ← line_total − line_cost

y re-deriva Sale.total_cost (suma de line_cost) y Sale.gross_profit
(total − total_cost).

Sólo toca ventas con total_cost > total y total > 0 (costo mayor al ingreso =
imposible en una cafetería → corrupción). NO toca CONSUMO_INTERNO (total = 0).

Uso:
    python manage.py fix_corrupt_sale_costs --tenant 1            # DRY-RUN
    python manage.py fix_corrupt_sale_costs --tenant 1 --apply    # escribe
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from core.models import Tenant
from sales.models import Sale
from inventory.models import StockItem

Z = Decimal("0")
Q3 = Decimal("0.001")


class Command(BaseCommand):
    help = "Recalcula costos de ventas corruptas (total_cost > total, total > 0)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Tenant ID (default: todos)")
        parser.add_argument("--apply", action="store_true", help="Aplica los cambios (default: dry-run)")
        parser.add_argument("--sample", type=int, default=10, help="Cuántas ventas mostrar en el detalle")

    def handle(self, *args, **opts):
        tenants = Tenant.objects.all()
        if opts["tenant"]:
            tenants = tenants.filter(id=opts["tenant"])
        for tenant in tenants:
            self._fix_tenant(tenant, opts["apply"], opts["sample"])

    def _unit_cost(self, tenant_id, warehouse_id, product, cache):
        key = (warehouse_id, product.id)
        if key in cache:
            return cache[key]
        avg = (
            StockItem.objects.filter(
                tenant_id=tenant_id, warehouse_id=warehouse_id, product_id=product.id,
            ).values_list("avg_cost", flat=True).first()
        )
        cost = avg if (avg and avg > 0) else None
        if cost is None:
            pc = getattr(product, "cost", None)
            cost = pc if (pc and pc > 0) else Z
        cache[key] = cost
        return cost

    def _fix_tenant(self, tenant, apply, sample):
        corrupt = (
            Sale.objects.filter(tenant=tenant, total_cost__gt=F("total"), total__gt=0)
            .prefetch_related("lines", "lines__product")
            .order_by("created_at")
        )
        n = corrupt.count()
        if not n:
            self.stdout.write(f"[tenant {tenant.id}] sin ventas corruptas.")
            return

        cache = {}
        agg = {"old_cost": Z, "new_cost": Z, "old_prof": Z, "new_prof": Z,
               "zero_lines": 0, "still_loss": 0, "shown": 0}

        def process():
            for sale in corrupt:
                old_cost, old_prof = sale.total_cost, sale.gross_profit
                new_total_cost = Z
                for line in sale.lines.all():
                    uc = self._unit_cost(tenant.id, sale.warehouse_id, line.product, cache)
                    if uc <= 0:
                        agg["zero_lines"] += 1
                    new_line_cost = (line.qty * uc).quantize(Q3)
                    new_total_cost += new_line_cost
                    if apply:
                        line.unit_cost_snapshot = uc
                        line.line_cost = new_line_cost
                        line.line_gross_profit = (line.line_total - new_line_cost)
                        line.save(update_fields=["unit_cost_snapshot", "line_cost", "line_gross_profit"])
                new_prof = sale.total - new_total_cost
                agg["old_cost"] += old_cost; agg["new_cost"] += new_total_cost
                agg["old_prof"] += old_prof; agg["new_prof"] += new_prof
                if new_total_cost > sale.total:
                    agg["still_loss"] += 1
                if apply:
                    sale.total_cost = new_total_cost
                    sale.gross_profit = new_prof
                    sale.save(update_fields=["total_cost", "gross_profit"])
                if agg["shown"] < sample:
                    self.stdout.write(
                        f"  #{sale.id} {sale.created_at:%Y-%m-%d} total={sale.total} "
                        f"costo {old_cost}→{new_total_cost} | util {old_prof}→{new_prof}"
                    )
                    agg["shown"] += 1

        if apply:
            with transaction.atomic():
                process()
        else:
            process()

        mode = "APLICADO ✅" if apply else "DRY-RUN (no escribió nada)"
        self.stdout.write(self.style.SUCCESS(
            f"\n[tenant {tenant.id}] {mode} — {n} ventas\n"
            f"  Costo total:    {agg['old_cost']:.0f} → {agg['new_cost']:.0f}\n"
            f"  Utilidad total: {agg['old_prof']:.0f} → {agg['new_prof']:.0f}\n"
            f"  Líneas sin avg_cost (costo=0): {agg['zero_lines']}\n"
            f"  Ventas que QUEDAN con costo>total tras recalcular: {agg['still_loss']}"
        ))
