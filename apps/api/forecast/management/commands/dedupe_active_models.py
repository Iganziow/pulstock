"""
dedupe_active_models — BUGFIX 01/06/26 (Mario).

Invariante: debe haber 1 solo ForecastModel activo por (tenant, product,
warehouse). Un bug en el swap derived/organic (Fase 2.3) dejaba activos los
derivados de noches anteriores → se acumulaban (ej. 15 "Leche entera" activas).

Este command repara los datos: por cada (tenant, product, warehouse) con >1
modelo activo, conserva el MEJOR (menor WAPE; desempate por más reciente) y
desactiva el resto. NO toca Forecast rows (las consultas usan el modelo
activo correcto tras la limpieza; el próximo entrenamiento las regenera).

Salvaguardas: --dry-run por defecto, --apply para persistir, por tenant.
"""
from django.core.management.base import BaseCommand
from django.db.models import Count

from core.models import Tenant
from forecast.models import ForecastModel


def _wape(m):
    try:
        w = float((m.metrics or {}).get("wape", 999))
    except (TypeError, ValueError):
        w = 999.0
    return w if w < 998 else 999.0


class Command(BaseCommand):
    help = "Deja 1 ForecastModel activo por (product, warehouse), desactiva duplicados."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None)
        parser.add_argument("--apply", action="store_true", help="Persistir (sin esto es dry-run)")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        tenants = (
            Tenant.objects.filter(id=opts["tenant"]) if opts["tenant"]
            else Tenant.objects.all()
        )
        mode = "APPLY" if apply else "DRY-RUN"
        total_deactivated = 0

        for tenant in tenants:
            dups = (
                ForecastModel.objects.filter(tenant=tenant, is_active=True)
                .values("product_id", "warehouse_id")
                .annotate(n=Count("id")).filter(n__gt=1)
            )
            for d in dups:
                models = list(ForecastModel.objects.filter(
                    tenant=tenant, product_id=d["product_id"],
                    warehouse_id=d["warehouse_id"], is_active=True,
                ))
                # Mejor = menor WAPE; desempate por trained_at más reciente.
                models.sort(key=lambda m: (_wape(m), -(m.trained_at.timestamp() if m.trained_at else 0)))
                keep = models[0]
                to_deactivate = models[1:]
                total_deactivated += len(to_deactivate)
                self.stdout.write(
                    f"[{mode}] tenant {tenant.id} prod {d['product_id']} wh {d['warehouse_id']}: "
                    f"{len(models)} activos → conservar {keep.algorithm} (WAPE {_wape(keep):.0f}), "
                    f"desactivar {len(to_deactivate)}"
                )
                if apply:
                    ForecastModel.objects.filter(
                        id__in=[m.id for m in to_deactivate],
                    ).update(is_active=False)

        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] TOTAL desactivados: {total_deactivated}"
            + ("" if apply else " (dry-run, nada cambiado)")
        ))
        if not apply:
            self.stdout.write(self.style.WARNING("Re-corré con --apply para persistir."))
