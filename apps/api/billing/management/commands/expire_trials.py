"""
Management command to expire trials that have passed trial_ends_at.
Runs the same logic as billing.tasks.expire_trials but can be invoked
via `python manage.py expire_trials` from cron, so it works even if
Celery is not running.

Usage (from cron, daily):
    cd /var/www/pulstock/apps/api && venv/bin/python manage.py expire_trials
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Expire trials whose trial_ends_at has passed (backup for Celery task)"

    def handle(self, *args, **options):
        from billing.models import Subscription

        now = timezone.now()
        expired_qs = Subscription.objects.filter(
            status=Subscription.Status.TRIALING,
            trial_ends_at__lte=now,
        ).select_related("tenant", "plan")

        count = expired_qs.count()
        if count == 0:
            self.stdout.write("No hay trials vencidos.")
            return

        self.stdout.write(f"Procesando {count} trial(es) vencido(s)...")

        # Try full Celery task flow first (charge + convert or downgrade)
        try:
            from billing.tasks import expire_trials as task_expire
            result = task_expire()
            self.stdout.write(self.style.SUCCESS(
                f"OK via task: {result}"
            ))
        except Exception as e:
            # Fallback: just mark as past_due so middleware blocks access
            self.stdout.write(self.style.WARNING(
                f"Task falló ({e}), usando fallback: marcar como past_due"
            ))
            for sub in expired_qs:
                sub.status = Subscription.Status.PAST_DUE
                sub.save(update_fields=["status"])
                self.stdout.write(f"  tenant={sub.tenant.name} → PAST_DUE")

        # Invalidate subscription cache so middleware picks up immediately
        from django.core.cache import cache
        for sub in Subscription.objects.filter(status=Subscription.Status.PAST_DUE):
            cache.delete(f"sub_access:{sub.tenant_id}")
