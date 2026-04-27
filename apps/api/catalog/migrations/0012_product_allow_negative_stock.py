# Generated for allow_negative_stock feature.
#
# El toggle "Permitir vender sin stock" del frontend del catálogo era un
# placebo — el frontend lo enviaba al backend y el backend lo descartaba
# silenciosamente porque el campo no existía. Con esta migración el feature
# funciona: cuando el dueño activa el toggle en un producto, el sistema le
# permite vender aunque el stock esté en 0 o negativo (caso típico: tengo
# bombones físicos pero no actualicé el sistema).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0011_print_station_fks"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="allow_negative_stock",
            field=models.BooleanField(
                default=False,
                help_text="Si está activo, se puede vender este producto aunque no haya stock.",
            ),
        ),
    ]
