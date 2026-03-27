from django.db import migrations, models
import django.db.models.deletion


def populate_counters(apps, schema_editor):
    """Initialize counters from existing max sale_number per tenant."""
    Sale = apps.get_model("sales", "Sale")
    TenantSaleCounter = apps.get_model("sales", "TenantSaleCounter")
    from django.db.models import Max

    tenant_maxes = (
        Sale.objects
        .filter(sale_number__isnull=False)
        .values("tenant_id")
        .annotate(max_num=Max("sale_number"))
    )
    for row in tenant_maxes:
        TenantSaleCounter.objects.update_or_create(
            tenant_id=row["tenant_id"],
            defaults={"last_number": row["max_num"]},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("sales", "0012_sale_open_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantSaleCounter",
            fields=[
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="sale_counter",
                        serialize=False,
                        to="core.tenant",
                    ),
                ),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "sales_tenantsalecounter",
            },
        ),
        migrations.RunPython(populate_counters, migrations.RunPython.noop),
    ]
