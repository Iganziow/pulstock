"""
purge_contaminated_accuracy — F (Mario 31/05/26).

Borra los registros de ForecastAccuracy de INGREDIENTES con fecha anterior a
`Tenant.ingredient_forecast_trusted_from`. Esos registros son ruido: vienen
del período en que las recetas no descontaban el ingrediente (subregistro →
real=0 falso) y de modelos colapsados (pred=0). Si quedan, la corrección de
sesgo (apply_bias_correction) y los KPIs de accuracy se basan en datos sucios.

Solo toca ingredientes de recetas ACTIVAS y solo días anteriores a la fecha
de confianza del tenant. Salvaguardas: --dry-run por defecto, --apply para
persistir, por tenant.
"""
from django.core.management.base import BaseCommand

from core.models import Tenant
from catalog.models import RecipeLine
from forecast.models import ForecastAccuracy


class Command(BaseCommand):
    help = "Borra ForecastAccuracy de ingredientes anterior a ingredient_forecast_trusted_from."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: todos)")
        parser.add_argument("--apply", action="store_true", help="Persistir el borrado (sin esto es dry-run)")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        tenants = (
            Tenant.objects.filter(id=opts["tenant"]) if opts["tenant"]
            else Tenant.objects.all()
        )
        mode = "APPLY" if apply else "DRY-RUN"
        total = 0
        for tenant in tenants:
            trusted = getattr(tenant, "ingredient_forecast_trusted_from", None)
            if not trusted:
                continue
            ingredient_ids = set(
                RecipeLine.objects.filter(
                    tenant=tenant, recipe__is_active=True,
                ).values_list("ingredient_id", flat=True)
            )
            if not ingredient_ids:
                continue
            qs = ForecastAccuracy.objects.filter(
                tenant=tenant, product_id__in=ingredient_ids, date__lt=trusted,
            )
            n = qs.count()
            if n == 0:
                continue
            total += n
            self.stdout.write(
                f"[{mode}] tenant {tenant.id} ({tenant.name}): "
                f"{n} registros de accuracy de ingredientes anteriores a {trusted}"
            )
            if apply:
                qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] TOTAL: {total} registros de accuracy contaminados"
            + (" borrados." if apply else " (dry-run, nada borrado).")
        ))
        if not apply:
            self.stdout.write(self.style.WARNING("Re-corré con --apply para borrar."))
