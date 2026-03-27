from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("forecast", "0006_dailysales_promo_qty_dailysales_promo_revenue"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailysales",
            name="forecast_only",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True = importado desde histórico externo (Excel/CSV). "
                    "El motor de forecast lo usa normalmente, pero aggregate_daily_sales "
                    "nunca lo sobreescribe y NO genera transacciones de stock."
                ),
            ),
        ),
    ]
