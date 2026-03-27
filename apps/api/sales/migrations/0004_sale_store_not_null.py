from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0003_backfill_sale_store"),
    ]

    operations = [
        # Safety net (por si llega a existir algún NULL, lo corrige)
        migrations.RunSQL(
            sql="""
                UPDATE sales_sale
                SET store_id = (
                    SELECT s2.id
                    FROM stores_store s2
                    WHERE s2.tenant_id = sales_sale.tenant_id
                    ORDER BY s2.id
                    LIMIT 1
                )
                WHERE store_id IS NULL;
            """,
            reverse_sql="-- no-op",
        ),
        migrations.AlterField(
            model_name="sale",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales",
                to="stores.store",
                null=False,
            ),
        ),
    ]
