"""
Borra PrintJobs terminales (done/failed/cancelled) con completed_at > 30 días.

Uso desde cron (diario 03:30):
    30 3 * * * cd /var/www/pulstock/apps/api && venv/bin/python manage.py cleanup_print_jobs
"""
from django.core.management.base import BaseCommand
from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Borra print jobs terminales >30 días (wrapper de cron)"

    def handle(self, *args, **options):
        # Max age 36h (corre diario 03:30)
        with cron_wrapper("printing.cleanup_jobs", max_age_min=36 * 60):
            from printing.tasks import cleanup_old_jobs
            deleted = cleanup_old_jobs()
            self.stdout.write(self.style.SUCCESS(
                f"OK: {deleted} print jobs borrados"
            ))
