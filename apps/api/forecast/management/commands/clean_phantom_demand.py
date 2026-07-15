"""
clean_phantom_demand
====================
Limpia demanda FANTASMA en DailySales.qty_sold: días donde el consumo de un
producto quedó inflado por un bug de expansión de receta.

Caso detectado (jul-2026): "Carne Mechada" tuvo 3 días (16/22/24-jun) con 115×
el consumo real — el RecipeLine.qty de la receta "Selladita mechada queso"
estuvo en 115 y se corrigió a 1, dejando 460 unidades fantasma que
contaminaban el forecast (el modelo sobre-predecía apuntando a esos picos).

Detección: para cada producto que es INGREDIENTE de alguna receta, un día es
"fantasma" si qty_sold > ABS_MIN y > FACTOR × la mediana de sus días con venta.

Corrección: recalcula qty_sold desde las VENTAS REALES —
    qty_sold = ventas_directas_del_producto
             + Σ (unidades vendidas del producto PADRE × RecipeLine.qty actual)
  todo sobre ventas COMPLETED de tipo VENTA, en la misma bodega y fecha. NO
  toca los StockMoves (auditoría histórica) ni el stock; solo la serie que
  alimenta el forecast. Sólo REDUCE (nunca infla) — seguro por construcción.

Uso:
    python manage.py clean_phantom_demand --tenant 1            # DRY-RUN
    python manage.py clean_phantom_demand --tenant 1 --apply    # escribe
    python manage.py clean_phantom_demand --tenant 1 --product-id 964 --apply
"""
import statistics
from decimal import Decimal
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import Tenant
from catalog.models import RecipeLine
from sales.models import Sale, SaleLine
from forecast.models import DailySales

ABS_MIN = Decimal("15")   # un spike real de cafetería difícilmente supera esto por ingrediente/día
FACTOR = 8                # y además debe ser > 8× la mediana del propio producto
Q3 = Decimal("0.001")


class Command(BaseCommand):
    help = "Limpia demanda fantasma en DailySales por bug de expansión de receta."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Tenant ID (default: todos)")
        parser.add_argument("--product-id", type=int, help="Limitar a un producto")
        parser.add_argument("--apply", action="store_true", help="Aplica (default: dry-run)")

    def handle(self, *args, **opts):
        tenants = Tenant.objects.all()
        if opts["tenant"]:
            tenants = tenants.filter(id=opts["tenant"])
        for tenant in tenants:
            self._fix_tenant(tenant, opts.get("product_id"), opts["apply"])

    def _recipe_parents(self, tenant, ingredient_id):
        """[(parent_product_id, recipe_qty)] de recetas ACTIVAS que usan este
        producto como ingrediente."""
        return [
            (rl.recipe.product_id, Decimal(str(rl.qty)))
            for rl in RecipeLine.objects.filter(
                tenant=tenant, ingredient_id=ingredient_id, recipe__is_active=True,
            ).select_related("recipe")
        ]

    def _sold_units(self, tenant, product_id, warehouse_id, day):
        """Unidades vendidas de un producto en ventas COMPLETED/VENTA, misma
        bodega y fecha (excluye anuladas y consumo interno)."""
        agg = SaleLine.objects.filter(
            tenant=tenant, product_id=product_id,
            sale__status=Sale.STATUS_COMPLETED,
            sale__sale_type=Sale.SALE_TYPE_VENTA,
            sale__warehouse_id=warehouse_id,
            sale__created_at__date=day,
        ).aggregate(q=Sum("qty"))
        return Decimal(str(agg["q"] or 0))

    def _fix_tenant(self, tenant, product_id, apply):
        ingr_ids = set(
            RecipeLine.objects.filter(tenant=tenant, recipe__is_active=True)
            .values_list("ingredient_id", flat=True)
        )
        if product_id:
            ingr_ids &= {product_id}
        if not ingr_ids:
            self.stdout.write(f"[tenant {tenant.id}] sin ingredientes de receta que revisar.")
            return

        # series por (product, warehouse)
        rows_by_key = defaultdict(list)
        for ds in DailySales.objects.filter(tenant=tenant, product_id__in=ingr_ids).select_related("product"):
            rows_by_key[(ds.product_id, ds.warehouse_id)].append(ds)

        fixes = []
        for (pid, wid), rows in rows_by_key.items():
            nz = [float(r.qty_sold) for r in rows if r.qty_sold and r.qty_sold > 0]
            if len(nz) < 3:
                continue
            med = Decimal(str(statistics.median(nz)))
            parents = self._recipe_parents(tenant, pid)
            for r in rows:
                q = r.qty_sold or Decimal("0")
                if q <= ABS_MIN or q <= FACTOR * med:
                    continue
                # recompute desde ventas reales
                corrected = self._sold_units(tenant, pid, wid, r.date)  # directas
                for parent_id, rq in parents:
                    corrected += self._sold_units(tenant, parent_id, wid, r.date) * rq
                corrected = corrected.quantize(Q3)
                if corrected < q:  # solo reducir
                    fixes.append((r, q, corrected, med, r.product.name))

        if not fixes:
            self.stdout.write(f"[tenant {tenant.id}] sin demanda fantasma detectada.")
            return

        phantom_total = sum(float(q - c) for _, q, c, _, _ in fixes)
        for r, q, c, med, nm in sorted(fixes, key=lambda x: -(x[1] - x[2])):
            self.stdout.write(
                f"  {nm[:26]:26} {r.date} wh={r.warehouse_id} "
                f"qty_sold {q}→{c} (mediana normal={med})"
            )

        if apply:
            with transaction.atomic():
                for r, q, c, _, _ in fixes:
                    DailySales.objects.filter(id=r.id).update(qty_sold=c)

        mode = "APLICADO ✅" if apply else "DRY-RUN (no escribió nada)"
        self.stdout.write(self.style.SUCCESS(
            f"\n[tenant {tenant.id}] {mode} — {len(fixes)} filas fantasma, "
            f"{phantom_total:.0f} unidades de demanda fantasma removidas.\n"
            f"  (No se tocaron StockMoves ni stock — solo la serie del forecast.)"
        ))
