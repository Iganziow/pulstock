"""
generate_purchase_suggestions
=============================
Nightly cron (04:00): creates purchase suggestions for products at risk of stockout.
Orchestrates the pipeline — business logic lives in forecast.services.

Usage:
    python manage.py generate_purchase_suggestions
    python manage.py generate_purchase_suggestions --tenant 1
    python manage.py generate_purchase_suggestions --threshold 14
    python manage.py generate_purchase_suggestions --target-days 14
"""
from datetime import date

from django.core.management.base import BaseCommand

from core.models import Tenant
from forecast.services import generate_suggestions


class Command(BaseCommand):
    help = "Generate purchase suggestions based on forecast data"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--threshold", type=int, default=14, help="Alert if stockout within N days (default: 14)")
        parser.add_argument("--target-days", type=int, default=14, help="Order enough to cover N days (default: 14)")

    def handle(self, *args, **options):
        threshold = max(1, options["threshold"])
        target_days = max(1, options["target_days"])
        today = date.today()

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total_suggestions = 0
        total_lines = 0

        for tenant in tenants:
            s, l = generate_suggestions(tenant, today, threshold, target_days)
            total_suggestions += s
            total_lines += l

        self.stdout.write(self.style.SUCCESS(
            f"Done: {total_suggestions} suggestions with {total_lines} product lines"
        ))
