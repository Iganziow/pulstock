"""
recalcular_minimos — el mínimo que se ajusta solo.

Mario pidió que no haya que configurar 252 mínimos a mano. Y tiene razón: hoy
solo 8 productos de 252 lo tienen puesto, y ninguno de los insumos.

Este comando los calcula cada noche desde el consumo real de cada producto: si
algo se pone de moda su mínimo sube solo, y si deja de venderse baja.

Corre después de `aggregate_daily_sales` (necesita la demanda del día anterior)
y antes de la alerta de quiebre de las 08:00.

Uso:
    python manage.py recalcular_minimos
    python manage.py recalcular_minimos --tenant 1 --dry-run
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.cron_utils import cron_wrapper


class Command(BaseCommand):
    help = "Recalcula el minimo sugerido de cada producto desde su consumo real."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        # El dry-run no registra heartbeat: es una consulta, no la corrida real.
        if options["dry_run"]:
            return self._run(options)
        with cron_wrapper("inventory.recalcular_minimos", max_age_min=36 * 60):
            self._run(options)

    def _run(self, options):
        from core.multi_tenant import exigir_todos, por_tenant, tenants_a_procesar
        from inventory.models import StockItem
        from inventory.min_stock import minimo_para

        tenants = tenants_a_procesar(options, command=self)

        total = con_minimo = 0

        def _un_tenant(tenant):
            nonlocal total, con_minimo
            items = (
                StockItem.objects
                .filter(tenant=tenant, product__is_active=True)
                .select_related("product", "warehouse")
            )
            for item in items:
                total += 1
                r = minimo_para(tenant, item.product, item.warehouse)
                nuevo = round(r["minimo"], 3) if r else None
                if nuevo:
                    con_minimo += 1
                if options["dry_run"]:
                    if r:
                        self.stdout.write(
                            "  [dry] %-32s min=%7.1f  (consume %.2f/dia, "
                            "cubre %d dias)"
                            % (item.product.name[:32], nuevo,
                               r["demanda_diaria"], r["dias_cobertura"])
                        )
                    continue
                item.min_stock_auto = nuevo
                item.min_stock_auto_at = timezone.now()
                item.save(update_fields=["min_stock_auto", "min_stock_auto_at"])

        # Mismo contrato que el resto del pipeline: un negocio con datos raros
        # no puede dejar a los demas sin recalcular sus minimos, y la falla
        # tiene que quedar visible igual.
        ok, fallidos = por_tenant(tenants, _un_tenant, command=self)

        self.stdout.write(self.style.SUCCESS(
            "Minimos recalculados: %d de %d productos con consumo reciente."
            % (con_minimo, total)
        ))
        exigir_todos(ok, fallidos, command=self)
