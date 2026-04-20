"""
Procesa renovaciones de suscripciones con período vencido.
Runs hourly via cron.
"""
from django.core.management.base import BaseCommand
from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Cobra suscripciones con current_period_end vencido (wrapper de cron)"

    def handle(self, *args, **options):
        with cron_wrapper("billing.process_renewals", max_age_min=90):
            from billing.tasks import process_renewals
            result = process_renewals.apply()
            if result.failed():
                self.stderr.write(self.style.ERROR(f"ERROR: {result.traceback}"))
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(f"OK: {result.result}"))
