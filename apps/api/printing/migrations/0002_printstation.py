# Generated for Print Stations feature.
#
# Adds:
#   - PrintStation model (tenant, name, is_default_for_receipts, …)
#   - AgentPrinter.station FK → PrintStation (nullable, SET_NULL)
#
# Compatibility: 100% backwards-compatible. Tenants without stations behave
# exactly as before — printing falls back to "first online agent + default
# printer" via the auto-print endpoint.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
        ("printing", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrintStation",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="Ej: 'Cocina', 'Bar', 'Despacho', 'Caja'", max_length=100)),
                ("is_default_for_receipts", models.BooleanField(default=False, help_text="Esta estación recibe boletas y pre-cuentas (típicamente 'Caja'). Solo una por tenant.")),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="print_stations", to="core.tenant")),
            ],
            options={
                "db_table": "printing_printstation",
                "ordering": ["sort_order", "name"],
                "indexes": [models.Index(fields=["tenant", "is_active"], name="printing_pr_tenant__a8b1cd_idx")],
                "unique_together": {("tenant", "name")},
            },
        ),
        migrations.AddField(
            model_name="agentprinter",
            name="station",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="Estación a la que pertenece esta impresora (cocina, bar, caja…)",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="printers",
                to="printing.printstation",
            ),
        ),
        migrations.AddIndex(
            model_name="agentprinter",
            index=models.Index(fields=["station", "is_active"], name="printing_ag_station_b3c9ef_idx"),
        ),
    ]
