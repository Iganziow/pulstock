"""
recalc_stock_value
==================
Resetea el invariante de valorización: stock_value = on_hand × avg_cost.

Contexto (jul 2026): stock_value se mantenía por deltas acumulados y drifteó
en 49 ítems de prod (algunos NEGATIVOS, ej. "Gretel 85 gr" en -4.880) por el
bug de la venta con fallback Product.cost sobre avg_cost=0 y por voids tras
cambios de costo. El código ya se corrigió para recalcular el invariante en
cada escritura (ver stock_value_expr en inventory/models.py); este command
limpia la data histórica que quedó desincronizada.

Sólo toca ítems donde |stock_value − on_hand×avg_cost| > 0.001. No modifica
on_hand ni avg_cost (fuentes de verdad); stock_value es el campo derivado.

Uso:
    python manage.py recalc_stock_value --tenant 1            # DRY-RUN
    python manage.py recalc_stock_value --tenant 1 --apply    # escribe
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Tenant
from inventory.models import StockItem

Q3 = Decimal("0.001")


class Command(BaseCommand):
    help = "Resetea stock_value = on_hand × avg_cost en los ítems drifteados."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Tenant ID (default: todos)")
        parser.add_argument("--apply", action="store_true", help="Aplica los cambios (default: dry-run)")
        parser.add_argument("--sample", type=int, default=15, help="Cuántos ítems mostrar en el detalle")

    def handle(self, *args, **opts):
        tenants = Tenant.objects.all()
        if opts["tenant"]:
            tenants = tenants.filter(id=opts["tenant"])
        for tenant in tenants:
            self._fix_tenant(tenant, opts["apply"], opts["sample"])

    def _fix_tenant(self, tenant, apply, sample):
        qs = StockItem.objects.filter(tenant=tenant).select_related("product")
        drifted = []
        old_total = Decimal("0")
        new_total = Decimal("0")
        for si in qs:
            stored = si.stock_value or Decimal("0")
            expected = ((si.on_hand or Decimal("0")) * (si.avg_cost or Decimal("0"))).quantize(Q3)
            old_total += stored
            new_total += expected
            if abs(stored - expected) > Q3:
                drifted.append((si, stored, expected))

        if not drifted:
            self.stdout.write(f"[tenant {tenant.id}] sin drift — invariante OK en {qs.count()} ítems.")
            return

        negatives = sum(1 for _, stored, _ in drifted if stored < 0)
        drifted.sort(key=lambda t: abs(t[1] - t[2]), reverse=True)
        for si, stored, expected in drifted[:sample]:
            self.stdout.write(
                f"  {si.product.name[:32]:32} wh={si.warehouse_id} "
                f"on_hand={si.on_hand} avg={si.avg_cost} "
                f"stock_value {stored} → {expected}"
            )
        if len(drifted) > sample:
            self.stdout.write(f"  … y {len(drifted) - sample} más")

        if apply:
            with transaction.atomic():
                for si, _, expected in drifted:
                    StockItem.objects.filter(id=si.id).update(stock_value=expected)

        mode = "APLICADO ✅" if apply else "DRY-RUN (no escribió nada)"
        self.stdout.write(self.style.SUCCESS(
            f"\n[tenant {tenant.id}] {mode} — {len(drifted)} ítems drifteados de {qs.count()} "
            f"({negatives} con valor negativo)\n"
            f"  Stock valorizado total: {old_total:.0f} → {new_total:.0f}"
        ))
