"""
Idempotency key on OpenOrderLine — Mario reportó que en WiFi inestable,
si el confirm de pendientes se demora y el navegador retransmite, las
líneas se duplican. La key (UUID generado por el frontend en cada intento
de confirm) permite que el backend detecte el retry y devuelva las
líneas ya creadas en vez de insertar nuevas.

Solo afecta la tabla `tables_openorderline`. Es un campo nuevo opcional
con default="" — todas las líneas existentes quedan con string vacío
(comportamiento legacy: sin idempotency, como antes).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tables", "0006_add_floor_plan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="openorderline",
            name="add_lines_batch_key",
            field=models.CharField(blank=True, default="", db_index=True, max_length=64),
        ),
    ]
