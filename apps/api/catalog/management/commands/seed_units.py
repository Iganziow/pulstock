"""
Seed standard units for all (or a specific) tenant.
Idempotent: uses get_or_create on (tenant, code).

Usage:
    python manage.py seed_units              # all tenants
    python manage.py seed_units --tenant_id 2
    python manage.py seed_units --business-type restaurant   # force extras
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from core.models import Tenant
from catalog.models import Unit


# (code, name, family, is_base, base_code, factor)
STANDARD_UNITS = [
    ("GR",   "Gramo",       "MASS",   True,  None, Decimal("1")),
    ("KG",   "Kilogramo",   "MASS",   False, "GR", Decimal("1000")),
    ("ML",   "Mililitro",   "VOLUME", True,  None, Decimal("1")),
    ("LT",   "Litro",       "VOLUME", False, "ML", Decimal("1000")),
    ("CM",   "Centímetro",  "LENGTH", True,  None, Decimal("1")),
    ("MT",   "Metro",       "LENGTH", False, "CM", Decimal("100")),
    ("UN",   "Unidad",      "COUNT",  True,  None, Decimal("1")),
    ("DOC",  "Docena",      "COUNT",  False, "UN", Decimal("12")),
    ("CAJA", "Caja",        "COUNT",  False, "UN", Decimal("1")),
    ("PAQ",  "Paquete",     "COUNT",  False, "UN", Decimal("1")),
]

EXTRAS_BY_BUSINESS_TYPE = {
    "restaurant": [
        ("OZ",   "Onza",        "MASS",   False, "GR", Decimal("28.3495")),
        ("TAZA", "Taza",        "VOLUME", False, "ML", Decimal("250")),
        ("CUCH", "Cucharada",   "VOLUME", False, "ML", Decimal("15")),
        ("PORC", "Porción",     "COUNT",  False, "UN", Decimal("1")),
    ],
    "hardware": [
        ("PLG",  "Pulgada",     "LENGTH", False, "CM", Decimal("2.54")),
        ("M2",   "Metro²",      "LENGTH", False, "CM", Decimal("10000")),
        ("PIE",  "Pie",         "LENGTH", False, "CM", Decimal("30.48")),
        ("GAL",  "Galón",       "VOLUME", False, "ML", Decimal("3785")),
        ("LB",   "Libra",       "MASS",   False, "GR", Decimal("453.592")),
    ],
    "pharmacy": [
        ("MG",   "Miligramo",   "MASS",   False, "GR", Decimal("0.001")),
        ("MCG",  "Microgramo",  "MASS",   False, "GR", Decimal("0.000001")),
        ("CC",   "Centímetro³", "VOLUME", False, "ML", Decimal("1")),
        ("GOT",  "Gota",        "VOLUME", False, "ML", Decimal("0.05")),
    ],
    "wholesale": [
        ("BUL",  "Bulto",       "COUNT",  False, "UN", Decimal("1")),
        ("PAL",  "Pallet",      "COUNT",  False, "UN", Decimal("1")),
        ("TON",  "Tonelada",    "MASS",   False, "GR", Decimal("1000000")),
    ],
}


def _create_units(tenant, unit_list, base_map):
    """Create a list of units, populating base_map. Returns count created."""
    created = 0

    # First pass: base units
    for code, name, family, is_base, _, factor in unit_list:
        if not is_base:
            continue
        obj, was_created = Unit.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={
                "name": name, "family": family, "is_base": True,
                "base_unit": None, "conversion_factor": factor,
            },
        )
        if not was_created:
            if not obj.family or obj.family == "COUNT" and family != "COUNT":
                obj.family = family
                obj.save(update_fields=["family"])
        base_map[code] = obj
        if was_created:
            created += 1

    # Second pass: derived units
    for code, name, family, is_base, base_code, factor in unit_list:
        if is_base:
            continue
        base_obj = base_map.get(base_code)
        obj, was_created = Unit.objects.get_or_create(
            tenant=tenant, code=code,
            defaults={
                "name": name, "family": family, "is_base": False,
                "base_unit": base_obj, "conversion_factor": factor,
            },
        )
        if not was_created and not obj.family:
            obj.family = family
            obj.save(update_fields=["family"])
        if was_created:
            created += 1

    return created


def seed_units_for_tenant(tenant, business_type=None):
    """Create standard + business-type units for a single tenant. Returns count of created."""
    base_map = {}
    created = _create_units(tenant, STANDARD_UNITS, base_map)

    btype = business_type or getattr(tenant, "business_type", None) or "retail"
    extras = EXTRAS_BY_BUSINESS_TYPE.get(btype, [])
    if extras:
        created += _create_units(tenant, extras, base_map)

    return created


class Command(BaseCommand):
    help = "Seed standard units (KG, GR, LT, ML, UN, etc.) for tenants."

    def add_arguments(self, parser):
        parser.add_argument("--tenant_id", type=int, default=None)
        parser.add_argument(
            "--business-type", type=str, default=None,
            help="Force a specific business type (restaurant, hardware, pharmacy, wholesale)",
        )

    def handle(self, *args, **options):
        tid = options["tenant_id"]
        btype = options["business_type"]
        tenants = Tenant.objects.filter(pk=tid) if tid else Tenant.objects.all()

        total = 0
        for tenant in tenants:
            effective_type = btype or getattr(tenant, "business_type", None) or "retail"
            n = seed_units_for_tenant(tenant, business_type=btype)
            total += n
            self.stdout.write(f"  Tenant {tenant.pk} ({tenant.name}) [{effective_type}]: {n} unidades creadas")

        self.stdout.write(self.style.SUCCESS(f"Listo — {total} unidades creadas en total."))
