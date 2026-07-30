"""
mark_closed_day
===============
Marca una fecha como NO OPERATIVA para el forecast (local cerrado, caída del
sistema, corte de luz, feriado no planificado).

Problema que resuelve
---------------------
El motor rellena con 0 los días sin DailySales al armar la serie
(`forecast/services.py` — "Rellenamos los huecos con 0"). Si el local NO PUDO
vender (no es que vendió poco), ese 0 entra como demanda real y contamina:
  - baja el promedio del día de semana afectado,
  - en intermitentes (Croston/SBA) alarga el intervalo entre demandas
    estimado → el modelo empieza a sub-predecir.

Caso real: 28-jul-2026, Hetzner bloqueó la IP por una factura impaga y el café
no pudo operar en todo el día → quedó registrado como "martes de 0 ventas".

Cómo lo resuelve
----------------
Crea/actualiza la fila DailySales de esa fecha con `is_stockout=True` para cada
(producto, bodega) con historial reciente. El motor arma `stockout_dates` desde
ese flag y `clean_series` IMPUTA el día (mediana del mismo día de semana) en vez
de aprender el cero.

NO toca ventas, stock ni movimientos: solo la serie que alimenta el forecast.
Es idempotente — correrlo dos veces no cambia nada.

Uso:
    python manage.py mark_closed_day --date 2026-07-28 --tenant 1           # DRY-RUN
    python manage.py mark_closed_day --date 2026-07-28 --tenant 1 --apply
    python manage.py mark_closed_day --date 2026-07-28 --tenant 1 --apply --reason "bloqueo Hetzner"
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Tenant
from forecast.models import DailySales

# Ventana hacia atrás para decidir qué (producto, bodega) estaban "vivos".
LOOKBACK_DAYS = 60


class Command(BaseCommand):
    help = "Marca una fecha como día no operativo (cerrado) para que el forecast la interpole."

    def add_arguments(self, parser):
        parser.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
        parser.add_argument("--tenant", type=int, help="Tenant ID (default: todos)")
        parser.add_argument("--apply", action="store_true", help="Aplica (default: dry-run)")
        parser.add_argument("--reason", default="", help="Motivo (solo para el log)")

    def handle(self, *args, **opts):
        try:
            target = datetime.strptime(opts["date"], "%Y-%m-%d").date()
        except ValueError:
            raise CommandError("--date debe ser YYYY-MM-DD")

        tenants = Tenant.objects.all()
        if opts["tenant"]:
            tenants = tenants.filter(id=opts["tenant"])

        for tenant in tenants:
            self._mark(tenant, target, opts["apply"], opts.get("reason") or "")

    def _mark(self, tenant, target, apply, reason):
        # (producto, bodega) con actividad reciente = los que tienen serie viva.
        since = target - timedelta(days=LOOKBACK_DAYS)
        pairs = set(
            DailySales.objects
            .filter(tenant=tenant, date__gte=since, date__lt=target)
            .values_list("product_id", "warehouse_id")
            .distinct()
        )
        if not pairs:
            self.stdout.write(f"[tenant {tenant.id}] sin historial previo a {target} — nada que marcar.")
            return

        existing = {
            (d.product_id, d.warehouse_id): d
            for d in DailySales.objects.filter(tenant=tenant, date=target)
        }

        to_create, to_flag, already = [], [], 0
        for (pid, wid) in pairs:
            row = existing.get((pid, wid))
            if row is None:
                to_create.append(DailySales(
                    tenant=tenant, product_id=pid, warehouse_id=wid, date=target,
                    is_stockout=True,
                ))
            elif not row.is_stockout:
                to_flag.append(row.id)
            else:
                already += 1

        self.stdout.write(
            f"[tenant {tenant.id}] {target} ({target:%A}) — series vivas: {len(pairs)}\n"
            f"  filas a crear (marcadas cerrado): {len(to_create)}\n"
            f"  filas existentes a marcar:        {len(to_flag)}\n"
            f"  ya marcadas (idempotente):        {already}"
        )
        if reason:
            self.stdout.write(f"  motivo: {reason}")

        if not apply:
            self.stdout.write(self.style.WARNING("\n  DRY-RUN — no se escribió nada. Usá --apply."))
            return

        with transaction.atomic():
            if to_create:
                DailySales.objects.bulk_create(to_create, batch_size=500)
            if to_flag:
                DailySales.objects.filter(id__in=to_flag).update(is_stockout=True)

        self.stdout.write(self.style.SUCCESS(
            f"\n  APLICADO ✅ — {len(to_create)} creadas + {len(to_flag)} marcadas. "
            f"El próximo entrenamiento interpolará {target} en vez de aprender 0.\n"
            f"  (No se tocaron ventas, stock ni movimientos.)"
        ))
