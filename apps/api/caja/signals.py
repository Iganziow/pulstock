"""
caja/signals.py
===============
Auto-seeder de categorías default cuando se crea un Tenant nuevo.

Mismo set de DEFAULT_CATEGORIES que la migration 0004_add_movement_category_fk.
Si querés cambiarlas, actualizá AMBOS lugares (o refactor para que ambos
importen de un único módulo).
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# Match con migration 0004 — si cambia uno, cambiar el otro.
DEFAULT_CATEGORIES = [
    # Egresos
    ("SUPPLIER",     "Pago a proveedor",                "OUT", 1),
    ("SALARY",       "Sueldo",                          "OUT", 2),
    ("SERVICE",      "Servicio (luz/agua/internet)",    "OUT", 3),
    ("OWNER_DRAW",   "Retiro del dueño",                "OUT", 4),
    ("REFUND",       "Devolución a cliente",            "OUT", 5),
    ("OTHER_OUT",    "Otro egreso",                     "OUT", 6),
    # Ingresos
    ("CAPITAL",      "Aporte de capital",               "IN",  1),
    ("EXTRA_INCOME", "Recaudación adicional",           "IN",  2),
    ("LOAN",         "Préstamo",                        "IN",  3),
    ("OTHER_IN",     "Otro ingreso",                    "IN",  4),
]


@receiver(post_save, sender="core.Tenant")
def seed_default_categories_for_new_tenant(sender, instance, created, **kwargs):
    """Cuando se crea un Tenant, popular sus categorías default."""
    if not created:
        return
    # Import lazy para evitar circular imports
    from .models import MovementCategory

    try:
        # Idempotente: si ya hay alguna categoría, no duplicar
        if MovementCategory.objects.filter(tenant=instance).exists():
            return

        cats = [
            MovementCategory(
                tenant=instance, code=code, label=label, type=type_,
                is_default_template=True, is_active=True, order=order,
            )
            for code, label, type_, order in DEFAULT_CATEGORIES
        ]
        MovementCategory.objects.bulk_create(cats)
        logger.info(
            "Seeded %d default movement categories for tenant=%s",
            len(cats), instance.id,
        )
    except Exception:
        # NO romper la creación del tenant si falla el seed
        logger.exception(
            "Failed to seed default categories for tenant=%s — continue anyway",
            instance.id,
        )
