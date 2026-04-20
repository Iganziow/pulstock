"""
Borra PrintJobs terminales (done/failed/cancelled) con completed_at > 30 días.

Uso desde cron (diario 03:30):
    30 3 * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py cleanup_print_jobs
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Borra print jobs terminales >30 días (wrapper de cron)"

    def handle(self, *args, **options):
        from printing.tasks import cleanup_old_jobs
        deleted = cleanup_old_jobs()
        self.stdout.write(self.style.SUCCESS(
            f"OK: {deleted} print jobs borrados"
        ))
