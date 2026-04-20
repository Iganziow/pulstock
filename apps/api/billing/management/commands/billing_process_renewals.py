"""
Procesa renovaciones de suscripciones con período vencido — invoca la misma
lógica que billing.tasks.process_renewals pero desde cron (sin Celery worker).

Uso desde cron (horario):
    0 * * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py billing_process_renewals
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cobra suscripciones con current_period_end vencido (wrapper de cron)"

    def handle(self, *args, **options):
        from billing.tasks import process_renewals
        # .apply() ejecuta sincrónicamente en este proceso (no necesita worker)
        result = process_renewals.apply()
        if result.failed():
            self.stderr.write(self.style.ERROR(f"ERROR: {result.traceback}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"OK: {result.result}"))
