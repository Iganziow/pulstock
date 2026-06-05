"""
backfill_recipe_line_costs — recalcula line_cost / line_gross_profit de los
SaleLine de productos-receta usando el conversor de unidades correcto.

Motivo (03/06/26): SaleLines viejos (import de Fudo / antes del fix de
conversión de unidades) grabaron el costo SIN convertir (gramos tratados como
kg) → costo ~1000× inflado → el reporte ABC mostraba márgenes de -1900%.
El código actual (create_sale → compute_recipe_costs) ya convierte bien; esto
re-grava las líneas históricas con la MISMA función para que el ABC muestre
márgenes reales.

Caveat: usa el costo ACTUAL de los ingredientes (el avg_cost histórico exacto
al momento de cada venta se perdió). Es una aproximación, pero infinitamente
mejor que el costo fantasma inflado.

Salvaguardas: --dry-run por defecto, --apply para persistir, por tenant.
Hacer backup de la BD antes de --apply.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max

from catalog.models import Recipe, Product
from inventory.models import StockItem
from sales.models import SaleLine
from sales.recipes import compute_recipe_costs

Q3 = Decimal("0.000")


class Command(BaseCommand):
    help = "Recalcula line_cost/line_gross_profit de SaleLines de productos-receta (conversor correcto)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True)
        parser.add_argument("--apply", action="store_true", help="Persistir (sin esto es dry-run)")

    def handle(self, *args, **opts):
        tid = opts["tenant"]
        apply = opts["apply"]
        mode = "APPLY" if apply else "DRY-RUN"

        # 1. Todas las recetas activas (estructura que espera compute_recipe_costs).
        all_recipes = {
            r.product_id: r
            for r in Recipe.objects.filter(tenant_id=tid, is_active=True)
            .prefetch_related("lines__unit", "lines__ingredient__unit_obj")
        }
        if not all_recipes:
            self.stdout.write(self.style.WARNING("Sin recetas activas para este tenant."))
            return

        # 2. Costo unitario de ingredientes (avg_cost del stock; fallback Product.cost).
        prod_cost = {p.id: (p.cost or Decimal("0")) for p in Product.objects.filter(tenant_id=tid).only("id", "cost")}
        avg = {
            row["product_id"]: (row["c"] or Decimal("0"))
            for row in StockItem.objects.filter(tenant_id=tid).values("product_id").annotate(c=Max("avg_cost"))
        }

        def _eff(pid):
            a = avg.get(pid, Decimal("0")) or Decimal("0")
            if a > 0:
                return a
            return Decimal(str(prod_cost.get(pid, Decimal("0")) or 0))

        ingredient_avg_cost = {
            pid: _eff(pid).quantize(Q3) for pid in set(list(avg) + list(prod_cost))
        }

        # 3. Costo unitario por producto-receta (MISMA función que create_sale).
        agg = {pid: {} for pid in all_recipes}
        unit_cost = compute_recipe_costs(agg, all_recipes, ingredient_avg_cost, tenant_id=tid)

        # 4. Recalcular cada SaleLine de productos-receta.
        lines = SaleLine.objects.filter(tenant_id=tid, product_id__in=list(all_recipes.keys()))
        changed, total_old, total_new = 0, Decimal("0"), Decimal("0")
        updates, samples = [], []
        for ln in lines.select_related("product").only(
            "id", "product_id", "product__name", "qty", "line_total", "line_cost", "line_gross_profit"
        ):
            uc = unit_cost.get(ln.product_id)
            if uc is None:
                continue
            new_cost = (uc * (ln.qty or Decimal("0"))).quantize(Q3)
            new_gross = (ln.line_total - new_cost).quantize(Q3)
            if new_cost != ln.line_cost:
                changed += 1
                total_old += ln.line_cost
                total_new += new_cost
                if len(samples) < 12 and ln.line_cost > new_cost:
                    samples.append((ln.product.name, ln.qty, ln.line_total, ln.line_cost, new_cost))
                ln.line_cost = new_cost
                ln.line_gross_profit = new_gross
                updates.append(ln)

        self.stdout.write(f"[{mode}] tenant {tid}: {lines.count()} líneas de productos-receta, "
                          f"{changed} a recalcular.")
        self.stdout.write(f"[{mode}] costo viejo total: {total_old:.0f}  ->  nuevo: {total_new:.0f}  "
                          f"(libera {total_old - total_new:.0f} de costo fantasma)")
        for name, qty, lt, old, new in sorted(samples, key=lambda x: x[3] - x[4], reverse=True):
            self.stdout.write(f"    [{name}] qty={qty} ingreso={lt} costo {old:.0f} -> {new:.0f}")

        if apply:
            SaleLine.objects.bulk_update(updates, ["line_cost", "line_gross_profit"], batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"[APPLY] {changed} SaleLines actualizadas."))
        else:
            self.stdout.write(self.style.WARNING("Dry-run: nada cambiado. Re-corré con --apply (con backup)."))
