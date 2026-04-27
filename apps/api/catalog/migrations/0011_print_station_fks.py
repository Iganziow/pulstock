# Generated for Print Stations feature.
#
# Adds:
#   - Category.default_print_station FK → printing.PrintStation (nullable, SET_NULL)
#   - Product.print_station_override FK → printing.PrintStation (nullable, SET_NULL)
#
# 100% backwards-compatible: existing data is left intact. SET_NULL means
# eliminar una estación NO borra categorías/productos — solo deja sus
# referencias en NULL (los items caen al fallback de impresión).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_backfill_product_unit_obj"),
        ("printing", "0002_printstation"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="default_print_station",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="Estación de impresión donde sale la comanda por defecto (cocina, bar, etc.)",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_categories",
                to="printing.printstation",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="print_station_override",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="Override estación de impresión para este producto (deja null para heredar de la categoría)",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="override_products",
                to="printing.printstation",
            ),
        ),
    ]
