"""
backfill_mape_cap
=================
One-shot: capea abs_pct_error existente a 200% en ForecastAccuracy.

Detectado 08/05/26: `ingredient_derived` mostraba MAPE promedio de 64.389%
en producción por la división por cantidades cercanas a cero. El fix
en track_forecast_accuracy.py aplica el cap solo a registros NUEVOS;
este comando aplica retroactivamente el mismo cap a los registros viejos
para que las métricas reportadas sean comparables y consistentes.

USO:
    python manage.py backfill_mape_cap            # dry-run, muestra qué cambiaría
    python manage.py backfill_mape_cap --apply    # aplica el update
    python manage.py backfill_mape_cap --tenant 1 # solo un tenant
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q

from forecast.models import ForecastAccuracy


CAP_PCT = Decimal("200")


class Command(BaseCommand):
    help = "Cap abs_pct_error existente en ForecastAccuracy a 200% (idempotente)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Aplicar el update. Sin esta flag, solo muestra qué cambiaría (dry-run).",
        )
        parser.add_argument(
            "--tenant", type=int, default=None,
            help="Solo este tenant_id (default: todos).",
        )

    def handle(self, *args, **opts):
        qs = ForecastAccuracy.objects.filter(abs_pct_error__gt=CAP_PCT)
        if opts["tenant"]:
            qs = qs.filter(tenant_id=opts["tenant"])

        n_affected = qs.count()
        if n_affected == 0:
            self.stdout.write(self.style.SUCCESS(
                "No hay registros con abs_pct_error > 200%. Nada que hacer."
            ))
            return

        # Stats antes del cambio
        before = qs.aggregate(
            avg=Avg("abs_pct_error"),
            n=Count("id"),
        )

        # Stats globales (con todos los registros) para comparar antes/después
        all_qs = ForecastAccuracy.objects.all()
        if opts["tenant"]:
            all_qs = all_qs.filter(tenant_id=opts["tenant"])
        global_before = all_qs.aggregate(avg=Avg("abs_pct_error"), n=Count("id"))

        self.stdout.write(f"Registros con abs_pct_error > 200%: {n_affected}")
        self.stdout.write(f"  MAPE promedio de esos: {before['avg']:.1f}%")
        self.stdout.write(f"")
        self.stdout.write(f"Población total: {global_before['n']} registros")
        self.stdout.write(f"  MAPE global ANTES del cap: {global_before['avg']:.1f}%")

        # Calcular el MAPE global SIMULADO con el cap aplicado
        # (no podemos usar Avg directo en SQL con la condición — calculamos
        # a mano: suma con valor capeado dividido por cantidad)
        total = Decimal("0")
        for r in all_qs.iterator():
            if r.abs_pct_error is None:
                continue  # MAPE no calculable (qty_actual=0) — ignorado por Avg
            total += min(r.abs_pct_error, CAP_PCT)
        n_with_mape = all_qs.exclude(abs_pct_error__isnull=True).count()
        if n_with_mape > 0:
            new_avg = total / n_with_mape
            self.stdout.write(f"  MAPE global DESPUÉS del cap: {new_avg:.1f}% (simulado)")

        if not opts["apply"]:
            self.stdout.write(self.style.WARNING(
                "\n[dry-run] Para aplicar, vuelve a correr con --apply"
            ))
            return

        # Aplicar el update masivo
        updated = qs.update(abs_pct_error=CAP_PCT)
        self.stdout.write(self.style.SUCCESS(
            f"\n[OK] {updated} registros actualizados a abs_pct_error=200.00"
        ))

        # Re-medir
        after = ForecastAccuracy.objects.exclude(abs_pct_error__isnull=True)
        if opts["tenant"]:
            after = after.filter(tenant_id=opts["tenant"])
        avg_after = after.aggregate(avg=Avg("abs_pct_error"))["avg"]
        self.stdout.write(f"MAPE global tras el cap: {avg_after:.1f}%")
