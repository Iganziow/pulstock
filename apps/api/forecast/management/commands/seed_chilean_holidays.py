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
# Chilean national holidays with extended forecast modeling.
# Fields: month, day, name, mult (demand_multiplier), pre_days, pre_mult,
#         duration (duration_days), post_days, post_mult, ramp (ramp_type)
FIXED_HOLIDAYS = [
    # ── Feriados nacionales fuertes ──
    {"month": 1, "day": 1, "name": "Año Nuevo",
     "mult": "1.30", "pre_days": 3, "pre_mult": "1.40",
     "duration": 1, "post_days": 3, "post_mult": "0.75", "ramp": "linear"},

    {"month": 5, "day": 1, "name": "Día del Trabajo",
     "mult": "1.30", "pre_days": 1, "pre_mult": "1.20",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 5, "day": 21, "name": "Glorias Navales",
     "mult": "1.20", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 6, "day": 20, "name": "Día de los Pueblos Indígenas",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 6, "day": 29, "name": "San Pedro y San Pablo",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 7, "day": 16, "name": "Virgen del Carmen",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 8, "day": 15, "name": "Asunción de la Virgen",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    # ── FIESTAS PATRIAS (evento más importante del año) ──
    {"month": 9, "day": 18, "name": "Fiestas Patrias",
     "mult": "2.50", "pre_days": 7, "pre_mult": "1.60",
     "duration": 3, "post_days": 5, "post_mult": "0.70", "ramp": "linear"},

    {"month": 10, "day": 12, "name": "Encuentro de Dos Mundos",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 10, "day": 31, "name": "Día de las Iglesias Evangélicas / Halloween",
     "mult": "1.30", "pre_days": 3, "pre_mult": "1.20",
     "duration": 1, "post_days": 1, "post_mult": "0.90", "ramp": "linear"},

    {"month": 11, "day": 1, "name": "Día de Todos los Santos",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    {"month": 12, "day": 8, "name": "Inmaculada Concepción",
     "mult": "1.20", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant"},

    # ── NAVIDAD (segundo evento más importante) ──
    {"month": 12, "day": 25, "name": "Navidad",
     "mult": "2.00", "pre_days": 14, "pre_mult": "1.50",
     "duration": 2, "post_days": 5, "post_mult": "0.65", "ramp": "linear"},

    # ── Nochevieja / Año Nuevo Eve ──
    {"month": 12, "day": 31, "name": "Nochevieja",
     "mult": "1.80", "pre_days": 3, "pre_mult": "1.40",
     "duration": 1, "post_days": 2, "post_mult": "0.70", "ramp": "linear"},
]

# Eventos comerciales (no feriados legales pero afectan demanda)
COMMERCIAL_EVENTS = [
    # Día de la Madre (segundo domingo de mayo — usamos mayo 10 como aprox)
    {"month": 5, "day": 10, "name": "Día de la Madre",
     "mult": "1.60", "pre_days": 7, "pre_mult": "1.30",
     "duration": 1, "post_days": 2, "post_mult": "0.80", "ramp": "linear"},

    # Día del Padre (tercer domingo de junio — usamos junio 18 como aprox)
    {"month": 6, "day": 18, "name": "Día del Padre",
     "mult": "1.40", "pre_days": 5, "pre_mult": "1.20",
     "duration": 1, "post_days": 1, "post_mult": "0.85", "ramp": "linear"},

    # Black Friday (último viernes de noviembre — usamos nov 28 como aprox)
    {"month": 11, "day": 28, "name": "Black Friday / CyberMonday",
     "mult": "1.80", "pre_days": 7, "pre_mult": "1.30",
     "duration": 4, "post_days": 7, "post_mult": "0.75", "ramp": "linear"},

    # Vuelta a clases (primera semana de marzo)
    {"month": 3, "day": 1, "name": "Vuelta a Clases",
     "mult": "1.30", "pre_days": 7, "pre_mult": "1.15",
     "duration": 7, "post_days": 3, "post_mult": "0.90", "ramp": "plateau"},

    # San Valentín
    {"month": 2, "day": 14, "name": "San Valentín",
     "mult": "1.50", "pre_days": 5, "pre_mult": "1.25",
     "duration": 1, "post_days": 1, "post_mult": "0.85", "ramp": "linear"},
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

    def _create_holiday(self, h, year, scope="NATIONAL", recurring=True):
        """Create or update a single holiday entry."""
        _, was_created = Holiday.objects.update_or_create(
            tenant=None,
            date=date(year, h["month"], h["day"]),
            defaults={
                "name": h["name"],
                "scope": scope,
                "demand_multiplier": Decimal(h["mult"]),
                "pre_days": h["pre_days"],
                "pre_multiplier": Decimal(h["pre_mult"]),
                "duration_days": h.get("duration", 1),
                "post_days": h.get("post_days", 0),
                "post_multiplier": Decimal(h.get("post_mult", "1.00")),
                "ramp_type": h.get("ramp", "instant"),
                "is_recurring": recurring,
            },
        )
        return 1 if was_created else 0

    def handle(self, *args, **options):
        from datetime import timedelta

        start = options["start_year"]
        end = options["end_year"]
        created = updated = 0

        for year in range(start, end + 1):
            # National holidays
            for h in FIXED_HOLIDAYS:
                created += self._create_holiday(h, year)

            # Commercial events
            for h in COMMERCIAL_EVENTS:
                created += self._create_holiday(h, year, scope="CUSTOM")

            # Easter-based holidays (Viernes Santo, Sábado Santo)
            easter = _easter_date(year)
            good_friday = easter - timedelta(days=2)
            holy_saturday = easter - timedelta(days=1)

            for d, name, mult in [
                (good_friday, "Viernes Santo", "0.60"),      # Demanda BAJA (no laboral)
                (holy_saturday, "Sábado Santo", "0.70"),     # Demanda baja
            ]:
                _, was_created = Holiday.objects.update_or_create(
                    tenant=None,
                    date=d,
                    defaults={
                        "name": name,
                        "scope": Holiday.SCOPE_NATIONAL,
                        "demand_multiplier": Decimal(mult),
                        "pre_days": 2,
                        "pre_multiplier": Decimal("1.20"),
                        "duration_days": 1,
                        "post_days": 1,
                        "post_multiplier": Decimal("0.85"),
                        "ramp_type": "instant",
                        "is_recurring": False,
                    },
                )
                if was_created:
                    created += 1

        total = Holiday.objects.filter(tenant__isnull=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"Done: {created} created. Total holidays: {total} ({start}-{end})"
        ))
