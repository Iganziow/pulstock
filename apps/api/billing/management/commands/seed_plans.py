"""
billing/management/commands/seed_plans.py
==========================================
Crea los planes base en la base de datos.
Idempotente: no duplica si ya existen.
Desactiva planes obsoletos (free, multi_local).

Uso:
  python manage.py seed_plans
"""

from django.core.management.base import BaseCommand
from billing.models import Plan


PLANS = [
    {
        "key":           Plan.PlanKey.INICIO,
        "name":          "Plan Inicio",
        "price_clp":     19_000,
        "trial_days":    0,
        "max_products":  120,
        "max_stores":    1,
        "max_users":     10,
        "max_registers": 1,
        "has_forecast":  False,
        "has_abc":       False,
        "has_reports":   False,
        "has_transfers": False,
    },
    {
        "key":           Plan.PlanKey.CRECIMIENTO,
        "name":          "Plan Crecimiento",
        "price_clp":     25_990,
        "trial_days":    0,
        "max_products":  400,
        "max_stores":    2,
        "max_users":     15,
        "max_registers": 2,
        "has_forecast":  True,
        "has_abc":       True,
        "has_reports":   True,
        "has_transfers": False,
    },
    {
        "key":           Plan.PlanKey.PRO,
        "name":          "Plan Pro",
        "price_clp":     59_990,
        "trial_days":    7,
        "max_products":  1000,
        "max_stores":    5,
        "max_users":     -1,
        "max_registers": 5,
        "has_forecast":  True,
        "has_abc":       True,
        "has_reports":   True,
        "has_transfers": True,
    },
]

# Planes obsoletos que se desactivan
DEPRECATED_KEYS = ["free", "multi_local"]


class Command(BaseCommand):
    help = "Crea o actualiza los planes de suscripción en la base de datos."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for plan_data in PLANS:
            key = plan_data.pop("key")
            plan_data["is_active"] = True
            plan, created = Plan.objects.update_or_create(
                key=key,
                defaults=plan_data,
            )
            plan_data["key"] = key

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Creado: {plan}"))
            else:
                updated_count += 1
                self.stdout.write(f"  ↺ Actualizado: {plan}")

        # Desactivar planes obsoletos
        deprecated = Plan.objects.filter(key__in=DEPRECATED_KEYS, is_active=True).update(is_active=False)
        if deprecated:
            self.stdout.write(self.style.WARNING(f"  ⚠ {deprecated} plan(es) obsoleto(s) desactivado(s)"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nPlanes: {created_count} creados, {updated_count} actualizados."
            )
        )
