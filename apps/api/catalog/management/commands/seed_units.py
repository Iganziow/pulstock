"""
Seed standard units for all (or a specific) tenant.
Idempotent: uses get_or_create on (tenant, code).

Usage:
    python manage.py seed_units              # all tenants
    python manage.py seed_units --tenant_id 2
"""
from django.core.management.base import BaseCommand
from core.models import Tenant
from catalog.models import Unit


# (code, name, family, is_base, base_code, factor)
STANDARD_UNITS = [
    ("GR",   "Gramo",       "MASS",   True,  None, 1),
    ("KG",   "Kilogramo",   "MASS",   False, "GR", 1000),
    ("ML",   "Mililitro",   "VOLUME", True,  None, 1),
    ("LT",   "Litro",       "VOLUME", False, "ML", 1000),
    ("CM",   "Centímetro",  "LENGTH", True,  None, 1),
    ("MT",   "Metro",       "LENGTH", False, "CM", 100),
    ("UN",   "Unidad",      "COUNT",  True,  None, 1),
    ("DOC",  "Docena",      "COUNT",  False, "UN", 12),
    ("CAJA", "Caja",        "COUNT",  False, "UN", 1),
    ("PAQ",  "Paquete",     "COUNT",  False, "UN", 1),
]


def seed_units_for_tenant(tenant):
    """Create standard units for a single tenant. Returns count of created."""
    created = 0
    base_map = {}  # code -> Unit instance

    # First pass: create base units
    for code, name, family, is_base, _, factor in STANDARD_UNITS:
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
            # Update family if missing
            if not obj.family or obj.family == "COUNT" and family != "COUNT":
                obj.family = family
                obj.save(update_fields=["family"])
        base_map[code] = obj
        if was_created:
            created += 1

    # Second pass: derived units
    for code, name, family, is_base, base_code, factor in STANDARD_UNITS:
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


class Command(BaseCommand):
    help = "Seed standard units (KG, GR, LT, ML, UN, etc.) for tenants."

    def add_arguments(self, parser):
        parser.add_argument("--tenant_id", type=int, default=None)

    def handle(self, *args, **options):
        tid = options["tenant_id"]
        tenants = Tenant.objects.filter(pk=tid) if tid else Tenant.objects.all()

        total = 0
        for tenant in tenants:
            n = seed_units_for_tenant(tenant)
            total += n
            self.stdout.write(f"  Tenant {tenant.pk} ({tenant.name}): {n} unidades creadas")

        self.stdout.write(self.style.SUCCESS(f"Listo — {total} unidades creadas en total."))
