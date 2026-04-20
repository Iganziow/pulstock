"""
Suspende suscripciones past_due cuyo período venció hace más de N días.

Uso desde cron (horario, minuto 30):
    30 * * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py billing_suspend_overdue
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Suspende suscripciones con pago vencido (wrapper de cron)"

    def handle(self, *args, **options):
        from billing.tasks import suspend_overdue_subscriptions
        result = suspend_overdue_subscriptions.apply()
        if result.failed():
            self.stderr.write(self.style.ERROR(f"ERROR: {result.traceback}"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"OK: {result.result}"))
