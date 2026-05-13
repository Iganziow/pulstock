"""
recalibrate_confidence
======================
Recalcula confidence_label usando el WAPE REAL de los últimos N días
(no el MAPE del backtest, que era engañoso).

Mario reportó (13/05/26) que el sistema marcaba productos como "medium"
cuando su MAPE real era 129% — completamente desacalibrado. Esa
calibración usaba el MAPE del backtest, una métrica del MOMENTO del
entrenamiento que no refleja cómo le va al modelo en producción.

Ahora usamos el WAPE de los últimos 14 días desde ForecastAccuracy
(comparación real predicho vs vendido). Más honesto y operacional.

Política nueva:
  WAPE < 30%      → high       (predicciones confiables)
  WAPE 30-50%     → medium     (Mario revisa antes de comprar)
  WAPE 50-80%     → low        (referencia visual, no decisión)
  WAPE >= 80%     → very_low   (poco fiable, no usar)
  Sin datos       → low        (default conservador)

Usage:
    python manage.py recalibrate_confidence              # todos los tenants
    python manage.py recalibrate_confidence --tenant 1   # uno específico
    python manage.py recalibrate_confidence --days 7     # ventana corta (default 14)
    python manage.py recalibrate_confidence --dry-run    # ver cambios sin aplicar
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from django.db.models.functions import Abs
from django.utils import timezone

from core.models import Tenant
from forecast.models import ForecastAccuracy, ForecastModel


# Umbrales de WAPE → label. Si querés ajustarlos, hacelo acá.
# Estos son conservadores — un MAPE/WAPE 30% es excelente para retail.
WAPE_THRESHOLDS = [
    (Decimal("30"), "high"),
    (Decimal("50"), "medium"),
    (Decimal("80"), "low"),
]
# Cualquier WAPE >= 80 → very_low.
# Sin data → "low" (default conservador, no asumir alta calidad sin evidencia).
DEFAULT_LABEL_NO_DATA = "low"


def label_from_wape(wape):
    """WAPE (porcentaje 0-∞) → label."""
    if wape is None:
        return DEFAULT_LABEL_NO_DATA
    for threshold, label in WAPE_THRESHOLDS:
        if wape < threshold:
            return label
    return "very_low"


class Command(BaseCommand):
    help = "Recalibrate confidence_label using real WAPE from ForecastAccuracy."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--days", type=int, default=14, help="Days of accuracy history (default: 14)")
        parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")

    def handle(self, *args, **options):
        days = max(3, options["days"])
        cutoff = timezone.now().date() - timedelta(days=days)
        dry_run = options["dry_run"]

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total_updated = 0
        total_unchanged = 0
        changes_by_label = {}

        for tenant in tenants:
            models = ForecastModel.objects.filter(tenant=tenant, is_active=True)
            for fm in models:
                # WAPE real para este (producto, warehouse) en los últimos N días
                wape_data = ForecastAccuracy.objects.filter(
                    tenant=tenant,
                    product_id=fm.product_id,
                    warehouse_id=fm.warehouse_id,
                    date__gte=cutoff,
                    qty_actual__gt=0,
                ).aggregate(
                    sum_abs_error=Sum(Abs("error")),
                    sum_actual=Sum("qty_actual"),
                    n=Count("id"),
                )

                if wape_data["sum_actual"] and wape_data["sum_actual"] > 0:
                    wape = float(wape_data["sum_abs_error"]) / float(wape_data["sum_actual"]) * 100
                    new_reason = (
                        f"WAPE real {wape:.0f}% en últimos {days} días "
                        f"({wape_data['n']} comparaciones)"
                    )
                else:
                    wape = None
                    new_reason = f"Sin comparaciones reales en últimos {days} días — calibración default"

                new_label = label_from_wape(wape)
                old_label = fm.confidence_label

                if new_label != old_label:
                    transition = f"{old_label}→{new_label}"
                    changes_by_label[transition] = changes_by_label.get(transition, 0) + 1
                    if not dry_run:
                        fm.confidence_label = new_label
                        fm.confidence_reason = new_reason
                        fm.save(update_fields=["confidence_label", "confidence_reason"])
                    total_updated += 1
                else:
                    # Aún sin cambio de label, refrescar la reason si tenemos data
                    if wape is not None and not dry_run:
                        fm.confidence_reason = new_reason
                        fm.save(update_fields=["confidence_reason"])
                    total_unchanged += 1

        # Resumen
        verb = "Cambiarían" if dry_run else "Cambiaron"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {total_updated} modelos. {total_unchanged} sin cambio."
        ))
        if changes_by_label:
            self.stdout.write("Transiciones:")
            for transition, count in sorted(changes_by_label.items(), key=lambda x: -x[1]):
                self.stdout.write(f"  {transition}: {count}")
