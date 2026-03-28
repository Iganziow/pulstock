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
    # biz_mult: multiplicadores por tipo de negocio {retail, restaurant, hardware, wholesale, pharmacy}
    # ── 1 ENERO (irrenunciable — casi todo cerrado) ──
    {"month": 1, "day": 1, "name": "Año Nuevo",
     "mult": "0.20", "pre_days": 3, "pre_mult": "1.50",
     "duration": 1, "post_days": 2, "post_mult": "1.20", "ramp": "linear",
     "biz_mult": {"retail": 0.15, "restaurant": 0.10, "hardware": 0.05, "wholesale": 0.05, "pharmacy": 0.40}},

    # ── 1 MAYO (irrenunciable) ──
    {"month": 5, "day": 1, "name": "Día del Trabajo",
     "mult": "0.20", "pre_days": 1, "pre_mult": "1.20",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"retail": 0.15, "restaurant": 0.10, "hardware": 0.05, "wholesale": 0.05, "pharmacy": 0.40}},

    {"month": 5, "day": 21, "name": "Glorias Navales",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"retail": 1.20, "restaurant": 0.80, "hardware": 0.70}},

    {"month": 6, "day": 20, "name": "Día de los Pueblos Indígenas",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.75, "hardware": 0.70}},

    {"month": 6, "day": 29, "name": "San Pedro y San Pablo",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80, "hardware": 0.70}},

    {"month": 7, "day": 16, "name": "Virgen del Carmen",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80}},

    {"month": 8, "day": 15, "name": "Asunción de la Virgen",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80}},

    # ── FIESTAS PATRIAS (feriado irrenunciable — mayoría cierra) ──
    # La demanda se concentra ANTES (pre_days). El día mismo es bajo o 0.
    # pre_mult alto porque la gente compra para el feriado (asados, bebidas, etc.)
    {"month": 9, "day": 18, "name": "Fiestas Patrias",
     "mult": "0.30", "pre_days": 7, "pre_mult": "1.80",
     "duration": 3, "post_days": 3, "post_mult": "1.30", "ramp": "linear",
     "biz_mult": {
         "retail": 0.20,       # Minimarket: casi todos cerrados, los que abren venden poco
         "restaurant": 0.10,   # Cerrado (irrenunciable)
         "hardware": 0.05,     # Cerrado
         "wholesale": 0.10,    # Cerrado
         "pharmacy": 0.40,     # Turno, demanda baja pero abierta
     }},

    {"month": 10, "day": 12, "name": "Encuentro de Dos Mundos",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80, "hardware": 0.75}},

    {"month": 10, "day": 31, "name": "Halloween",
     "mult": "1.30", "pre_days": 3, "pre_mult": "1.20",
     "duration": 1, "post_days": 1, "post_mult": "0.90", "ramp": "linear",
     "biz_mult": {"retail": 1.50, "restaurant": 1.40, "hardware": 1.00, "pharmacy": 1.10}},

    {"month": 11, "day": 1, "name": "Día de Todos los Santos",
     "mult": "1.10", "pre_days": 1, "pre_mult": "1.05",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80}},

    {"month": 12, "day": 8, "name": "Inmaculada Concepción",
     "mult": "1.15", "pre_days": 1, "pre_mult": "1.10",
     "duration": 1, "post_days": 0, "post_mult": "1.00", "ramp": "instant",
     "biz_mult": {"restaurant": 0.80}},

    # ── NAVIDAD (irrenunciable — cerrado, demanda pre-navidad altísima) ──
    {"month": 12, "day": 25, "name": "Navidad",
     "mult": "0.15", "pre_days": 14, "pre_mult": "1.80",
     "duration": 1, "post_days": 3, "post_mult": "0.70", "ramp": "linear",
     "biz_mult": {"retail": 0.10, "restaurant": 0.10, "hardware": 0.05, "wholesale": 0.05, "pharmacy": 0.35}},

    # ── Nochevieja ──
    {"month": 12, "day": 31, "name": "Nochevieja",
     "mult": "1.60", "pre_days": 3, "pre_mult": "1.30",
     "duration": 1, "post_days": 2, "post_mult": "0.70", "ramp": "linear",
     "biz_mult": {"retail": 2.00, "restaurant": 1.80, "hardware": 0.50, "wholesale": 1.30, "pharmacy": 0.80}},
]

# Eventos comerciales (no feriados legales pero afectan demanda)
COMMERCIAL_EVENTS = [
    {"month": 5, "day": 10, "name": "Día de la Madre",
     "mult": "1.50", "pre_days": 7, "pre_mult": "1.30",
     "duration": 1, "post_days": 2, "post_mult": "0.80", "ramp": "linear",
     "biz_mult": {"retail": 1.60, "restaurant": 1.80, "hardware": 1.00, "pharmacy": 1.20}},

    {"month": 6, "day": 18, "name": "Día del Padre",
     "mult": "1.30", "pre_days": 5, "pre_mult": "1.20",
     "duration": 1, "post_days": 1, "post_mult": "0.85", "ramp": "linear",
     "biz_mult": {"retail": 1.30, "restaurant": 1.50, "hardware": 1.40, "pharmacy": 1.10}},

    {"month": 11, "day": 28, "name": "Black Friday / CyberMonday",
     "mult": "1.80", "pre_days": 7, "pre_mult": "1.30",
     "duration": 4, "post_days": 7, "post_mult": "0.75", "ramp": "linear",
     "biz_mult": {"retail": 2.20, "restaurant": 1.20, "hardware": 2.00, "wholesale": 1.80, "pharmacy": 1.30}},

    {"month": 3, "day": 1, "name": "Vuelta a Clases",
     "mult": "1.30", "pre_days": 7, "pre_mult": "1.15",
     "duration": 7, "post_days": 3, "post_mult": "0.90", "ramp": "plateau",
     "biz_mult": {"retail": 1.40, "restaurant": 1.10, "hardware": 1.00, "pharmacy": 1.20}},

    {"month": 2, "day": 14, "name": "San Valentín",
     "mult": "1.40", "pre_days": 5, "pre_mult": "1.25",
     "duration": 1, "post_days": 1, "post_mult": "0.85", "ramp": "linear",
     "biz_mult": {"retail": 1.40, "restaurant": 2.00, "hardware": 1.00, "pharmacy": 1.10}},
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
                "business_multipliers": h.get("biz_mult", {}),
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
                (good_friday, "Viernes Santo", "0.25"),      # Feriado irrenunciable — casi todo cerrado
                (holy_saturday, "Sábado Santo", "0.40"),     # No irrenunciable pero muchos cierran
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
