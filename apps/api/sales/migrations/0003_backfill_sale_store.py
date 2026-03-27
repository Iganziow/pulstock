from django.db import migrations


def forwards(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    Warehouse = apps.get_model("core", "Warehouse")
    Store = apps.get_model("stores", "Store")

    # Para cada Sale sin store:
    # - Si la warehouse tiene store_id -> usar ese
    # - Si no, fallback: primer Store del tenant
    qs = Sale.objects.filter(store_id__isnull=True).only("id", "tenant_id", "warehouse_id")

    for s in qs.iterator():
        store_id = None

        if s.warehouse_id:
            wh = Warehouse.objects.filter(id=s.warehouse_id).only("store_id", "tenant_id").first()
            if wh and wh.store_id:
                store_id = wh.store_id

        if not store_id:
            st = Store.objects.filter(tenant_id=s.tenant_id).order_by("id").only("id").first()
            if st:
                store_id = st.id

        if store_id:
            Sale.objects.filter(id=s.id).update(store_id=store_id)


def backwards(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    Sale.objects.update(store_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0002_sale_store"),
        ("core", "0007_remove_warehouse_uniq_warehouse_tenant_store_name_and_more"),
        ("stores", "0002_store_stores_stor_tenant__faf833_idx"),
        # 👆 Si tú ya tienes otra migración más nueva en stores (ej default_warehouse),
        # cámbiala aquí por la última. Pero con estas dependencias ya es suficiente
        # para acceder a Store y Warehouse.
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
