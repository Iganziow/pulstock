"""
Reintenta pagos fallidos que cayeron en Flow.cl.

Uso desde cron (horario, minuto 15):
    15 * * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py billing_retry_payments
"""
from django.core.management.base import BaseCommand
from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Reintenta cobros fallidos en Flow.cl (wrapper de cron)"

    def handle(self, *args, **options):
        with cron_wrapper("billing.retry_payments", max_age_min=90):
            from billing.tasks import retry_failed_payments
            result = retry_failed_payments.apply()
            if result.failed():
                self.stderr.write(self.style.ERROR(f"ERROR: {result.traceback}"))
                raise SystemExit(1)
            self.stdout.write(self.style.SUCCESS(f"OK: {result.result}"))
