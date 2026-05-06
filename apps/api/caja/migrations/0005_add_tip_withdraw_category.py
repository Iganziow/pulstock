# Migración para agregar la categoría de "Retiro de propinas" a tenants
# existentes. Mario reportó (06/05/26) que cuando alguien del equipo retira
# sus propinas en efectivo, la caja queda descuadrada porque las propinas
# en cash YA estaban sumadas al expected_cash. Sin una categoría dedicada,
# el dueño tenía que registrarlo como "Otro egreso" o "Retiro del dueño",
# mezclándolo con gastos reales del negocio.
#
# Esta migración:
#   1. Agrega la categoría TIP_WITHDRAW a TODOS los tenants existentes.
#   2. Es idempotente: si el tenant ya tiene esa categoría (creada después
#      de manera manual o porque la migración corrió previamente), la
#      respeta y no duplica.
#
# Para tenants nuevos, la categoría se crea automáticamente por el signal
# de signals.py (DEFAULT_CATEGORIES).

from django.db import migrations


def add_tip_withdraw_category(apps, schema_editor):
    Tenant = apps.get_model("core", "Tenant")
    MovementCategory = apps.get_model("caja", "MovementCategory")

    new_cats = []
    for tenant in Tenant.objects.all():
        already_exists = MovementCategory.objects.filter(
            tenant=tenant, code="TIP_WITHDRAW"
        ).exists()
        if already_exists:
            continue
        new_cats.append(MovementCategory(
            tenant=tenant,
            code="TIP_WITHDRAW",
            label="Retiro de propinas",
            type="OUT",
            is_default_template=True,
            is_active=True,
            order=5,  # entre OWNER_DRAW (4) y REFUND (que pasa a 6)
        ))
    if new_cats:
        MovementCategory.objects.bulk_create(new_cats)


def remove_tip_withdraw_category(apps, schema_editor):
    """Reverse: eliminar la categoría TIP_WITHDRAW de todos los tenants.

    NOTA: si hubieran movimientos asociados, NO se borran (CashMovement.category_fk
    usa SET_NULL). El historial queda intacto, solo desaparece la categoría
    del listado.
    """
    MovementCategory = apps.get_model("caja", "MovementCategory")
    MovementCategory.objects.filter(code="TIP_WITHDRAW").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("caja", "0004_add_movement_category_fk"),
    ]

    operations = [
        migrations.RunPython(add_tip_withdraw_category, remove_tip_withdraw_category),
    ]
