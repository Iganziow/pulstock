# -*- coding: utf-8 -*-
"""
desmarcar_quiebres_sin_movimiento — saca la marca de quiebre de los dias en que
el producto vendio sin mover su propio stock.

Por que existe
--------------
Hasta el 13/09/26 la deteccion de quiebre reconstruia la apertura del dia como
"cierre + vendido". Un producto que se prepara al momento (un latte: se
descuentan sus ingredientes) o que vende sin control de stock (el Te) tiene su
StockItem en 0 para siempre, asi que CUALQUIER dia que vendia abria "con
stock", cerraba en 0 y quedaba marcado como quiebre. Medido en produccion:
696 de 697 dias de venta de productos con receta, y 109 de otros productos.

Todas las metricas excluyen los dias de quiebre, porque en un quiebre real la
venta esta censurada. Asi se descartaban justamente los dias en que el
producto vendio: el WAPE real, la etiqueta de confianza, la calibracion de
bandas y la correccion de sesgo de esos productos se calculaban sin sus ventas.

La deteccion ya esta corregida para lo que viene (aggregate_daily_sales y
backfill_stockout_detection). Este comando arregla lo historico sin re-correr
el backfill completo, que recalcula TODAS las filas y borraria los dias
cerrados marcados a mano con mark_closed_day.

Que hace
--------
Solo DESMARCA, nunca marca. Toma las filas con is_stockout, venta > 0 y cierre
conocido; reconstruye la apertura desde el kardex de ese dia (cierre menos la
variacion neta) y conserva la marca solo si el producto cerro en 0 habiendo
tenido stock al abrir o habiendo recibido ese dia: la misma regla que el
backfill. Las filas sin venta (dias cerrados, quiebres con la venta censurada
en cero) no se tocan. Despues sincroniza ForecastAccuracy.was_stockout de esos
mismos dias, que se copio de la marca al puntuar.

Uso
---
  python manage.py desmarcar_quiebres_sin_movimiento --tenant 1            # dry-run
  python manage.py desmarcar_quiebres_sin_movimiento --tenant 1 --apply
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Recipe
from core.models import Tenant
from forecast.models import DailySales, ForecastAccuracy
from inventory.models import StockMove

ZERO = Decimal("0.000")
LOTE = 500


def _delta(move_type, qty):
    """IN suma, OUT resta, ADJ ya trae su signo (igual que el backfill)."""
    q = qty or ZERO
    return -q if move_type == StockMove.OUT else q


class Command(BaseCommand):
    help = "Desmarca como quiebre los dias con venta en que el producto no movio su propio stock."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: todos)")
        parser.add_argument("--apply", action="store_true", help="Escribir. Sin esto es dry-run.")

    def handle(self, *args, **o):
        tenants = Tenant.objects.all()
        if o.get("tenant"):
            tenants = tenants.filter(id=o["tenant"])
        aplicar = bool(o.get("apply"))
        modo = "APPLY" if aplicar else "DRY-RUN"

        for tenant in tenants:
            r = self._tenant(tenant, aplicar)
            if not r["revisadas"]:
                continue
            self.stdout.write(
                "[%s] %s: %d dias marcados como quiebre con venta | se desmarcan %d (%d de productos "
                "con receta) | siguen como quiebre %d | mediciones que se sincronizan %d"
                % (modo, tenant.name, r["revisadas"], r["desmarcar"], r["con_receta"],
                   r["siguen"], r["mediciones"]))
            for nombre, n in r["por_producto"][:10]:
                self.stdout.write("    %-34s %4d dias" % (nombre[:34], n))

        if not aplicar:
            self.stdout.write(self.style.WARNING("Dry-run: nada escrito. Re-corre con --apply para persistir."))

    def _tenant(self, tenant, aplicar):
        filas = list(
            DailySales.objects.filter(
                tenant=tenant, is_stockout=True, qty_sold__gt=0,
                closing_stock__isnull=False, forecast_only=False,
            ).values_list("id", "product_id", "warehouse_id", "date", "closing_stock", "product__name")
        )
        res = {"revisadas": len(filas), "desmarcar": 0, "con_receta": 0, "siguen": 0,
               "mediciones": 0, "por_producto": []}
        if not filas:
            return res

        productos = {f[1] for f in filas}
        desde = min(f[3] for f in filas) - timedelta(days=1)
        delta = defaultdict(lambda: ZERO)
        entradas = defaultdict(lambda: ZERO)
        movimientos = (
            StockMove.objects.filter(tenant=tenant, product_id__in=productos, created_at__date__gte=desde)
            .values_list("product_id", "warehouse_id", "move_type", "qty", "created_at")
        )
        for pid, wid, tipo, qty, creado in movimientos.iterator():
            dia = timezone.localtime(creado).date() if timezone.is_aware(creado) else creado.date()
            v = _delta(tipo, qty)
            delta[(pid, wid, dia)] += v
            if v > ZERO:
                entradas[(pid, wid, dia)] += v

        con_receta = set(
            Recipe.objects.filter(tenant=tenant, is_active=True, product_id__in=productos)
            .values_list("product_id", flat=True)
        )

        a_desmarcar = []
        por_producto = defaultdict(int)
        for ds_id, pid, wid, dia, cierre, nombre in filas:
            k = (pid, wid, dia)
            apertura = cierre - delta[k]
            if cierre <= ZERO and (apertura > ZERO or entradas[k] > ZERO):
                res["siguen"] += 1
                continue
            a_desmarcar.append((ds_id, pid, wid, dia))
            por_producto[nombre] += 1
            if pid in con_receta:
                res["con_receta"] += 1

        res["desmarcar"] = len(a_desmarcar)
        res["por_producto"] = sorted(por_producto.items(), key=lambda kv: -kv[1])

        claves = {(pid, wid, dia) for _, pid, wid, dia in a_desmarcar}
        mediciones = [
            acc_id for acc_id, pid, wid, dia in
            ForecastAccuracy.objects.filter(
                tenant=tenant, was_stockout=True, product_id__in={c[0] for c in claves},
            ).values_list("id", "product_id", "warehouse_id", "date")
            if (pid, wid, dia) in claves
        ]
        res["mediciones"] = len(mediciones)

        if aplicar and a_desmarcar:
            ids = [f[0] for f in a_desmarcar]
            with transaction.atomic():
                for i in range(0, len(ids), LOTE):
                    DailySales.objects.filter(id__in=ids[i:i + LOTE]).update(is_stockout=False)
                for i in range(0, len(mediciones), LOTE):
                    ForecastAccuracy.objects.filter(id__in=mediciones[i:i + LOTE]).update(was_stockout=False)
        return res
