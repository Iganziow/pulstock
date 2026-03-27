"""
seed_chilean_holidays
=====================
Seeds Chilean national holidays for the given year range.

Usage:
    python manage.py seed_chilean_holidays
    python manage.py seed_chilean_holidays --start-year 2025 --end-year 2028
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from forecast.models import Holiday


# Chilean national holidays (fixed dates).
# Easter is variable — handled separately.
FIXED_HOLIDAYS = [
    {"month": 1, "day": 1, "name": "Año Nuevo", "mult": "1.30", "pre_days": 2, "pre_mult": "1.30"},
    {"month": 5, "day": 1, "name": "Día del Trabajo", "mult": "1.30", "pre_days": 1, "pre_mult": "1.20"},
    {"month": 5, "day": 21, "name": "Glorias Navales", "mult": "1.30", "pre_days": 1, "pre_mult": "1.20"},
    {"month": 6, "day": 20, "name": "Día de los Pueblos Indígenas", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 6, "day": 29, "name": "San Pedro y San Pablo", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 7, "day": 16, "name": "Virgen del Carmen", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 8, "day": 15, "name": "Asunción de la Virgen", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 9, "day": 18, "name": "Fiestas Patrias", "mult": "2.00", "pre_days": 3, "pre_mult": "1.50"},
    {"month": 9, "day": 19, "name": "Glorias del Ejército", "mult": "2.00", "pre_days": 0, "pre_mult": "1.00"},
    {"month": 10, "day": 12, "name": "Encuentro de Dos Mundos", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 10, "day": 31, "name": "Día de las Iglesias Evangélicas", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 11, "day": 1, "name": "Día de Todos los Santos", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 12, "day": 8, "name": "Inmaculada Concepción", "mult": "1.20", "pre_days": 1, "pre_mult": "1.10"},
    {"month": 12, "day": 25, "name": "Navidad", "mult": "1.80", "pre_days": 3, "pre_mult": "1.40"},
]


def _easter_date(year):
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


class Command(BaseCommand):
    help = "Seed Chilean national holidays"

    def add_arguments(self, parser):
        parser.add_argument("--start-year", type=int, default=2025)
        parser.add_argument("--end-year", type=int, default=2028)

    def handle(self, *args, **options):
        start = options["start_year"]
        end = options["end_year"]
        created = 0

        for year in range(start, end + 1):
            # Fixed holidays
            for h in FIXED_HOLIDAYS:
                _, was_created = Holiday.objects.get_or_create(
                    tenant=None,
                    date=date(year, h["month"], h["day"]),
                    defaults={
                        "name": h["name"],
                        "scope": Holiday.SCOPE_NATIONAL,
                        "demand_multiplier": Decimal(h["mult"]),
                        "pre_days": h["pre_days"],
                        "pre_multiplier": Decimal(h["pre_mult"]),
                        "is_recurring": True,
                    },
                )
                if was_created:
                    created += 1

            # Easter-based holidays (Viernes Santo, Sábado Santo)
            easter = _easter_date(year)
            from datetime import timedelta
            good_friday = easter - timedelta(days=2)
            holy_saturday = easter - timedelta(days=1)

            for d, name in [(good_friday, "Viernes Santo"), (holy_saturday, "Sábado Santo")]:
                _, was_created = Holiday.objects.get_or_create(
                    tenant=None,
                    date=d,
                    defaults={
                        "name": name,
                        "scope": Holiday.SCOPE_NATIONAL,
                        "demand_multiplier": Decimal("1.50"),
                        "pre_days": 1,
                        "pre_multiplier": Decimal("1.30"),
                        "is_recurring": False,  # Easter date changes yearly
                    },
                )
                if was_created:
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Done: {created} holidays created"))
