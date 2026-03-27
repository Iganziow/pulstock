"""
Data migration: backfill Product.unit_obj from Product.unit (string).

For each product where unit_obj is NULL and unit is not empty,
looks up the matching Unit record for the tenant and links it.
"""
from django.db import migrations


def backfill_unit_obj(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Unit = apps.get_model("catalog", "Unit")

    # Build a cache: (tenant_id, code) → unit_id
    unit_cache = {}
    for u in Unit.objects.filter(is_active=True).values("id", "tenant_id", "code"):
        key = (u["tenant_id"], u["code"].upper())
        unit_cache[key] = u["id"]

    # Update products without unit_obj
    products = Product.objects.filter(unit_obj__isnull=True).exclude(unit="")
    updated = 0
    for p in products.iterator(chunk_size=500):
        code = (p.unit or "").strip().upper()
        unit_id = unit_cache.get((p.tenant_id, code))
        if unit_id:
            Product.objects.filter(pk=p.pk).update(unit_obj_id=unit_id)
            updated += 1

    if updated:
        print(f"\n  Backfilled unit_obj on {updated} products")


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0009_product_catalog_pro_tenant__48a14c_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_unit_obj, reverse_noop),
    ]
