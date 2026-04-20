"""
Envía recordatorios de pago (3 y 1 días antes del vencimiento).

Uso desde cron (diario 09:00):
    0 9 * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py billing_send_reminders
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Envía emails de recordatorio de pago (wrapper de cron)"

    def handle(self, *args, **options):
        from billing.tasks import send_payment_reminders
        result = send_payment_reminders.apply()
        if result.failed():
            self.stderr.write(self.style.ERROR(f"ERROR: {result.traceback}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"OK: {result.result}"))
