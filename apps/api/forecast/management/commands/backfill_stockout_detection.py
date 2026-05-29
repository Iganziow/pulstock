"""
backfill_stockout_detection — F1.1 (Mario 29/05/26).

Reconstruye `DailySales.closing_stock` (NULL en ~93% del histórico) desde
los StockMove y marca `is_stockout=True` retroactivamente en los días donde
el producto se quedó sin stock HABIÉNDOLO tenido (se agotó), no en los días
que simplemente no se repuso.

Contexto (roadmap F1 — "Asesino silencioso"): si un producto se quiebra el
día 12, ese día vendió 0. El modelo aprende "vendí poco" cuando la realidad
es demanda CENSURADA por falta de stock → sub-predice → sub-pide → más
quiebres. Marcar esos días deja que `clean_series` interpole la demanda real
(avg del día-de-semana) en vez de aprender el 0 censurado.

Reconstrucción del stock (no hay saldo histórico, solo el delta de cada
StockMove + el saldo vivo StockItem.on_hand):
  closing_stock(D) = on_hand_actual − Σ delta(move con fecha > D)
  delta = +qty (IN) | −qty (OUT) | +qty (ADJ, qty trae su propio signo)
Es decir, anclamos en el saldo conocido de HOY y restamos hacia atrás.

Criterio de stockout (CONSERVADOR para evitar falsos positivos):
  is_stockout = closing ≤ 0  AND  (opening > 0  OR  recibió stock ese día)
donde opening = closing + qty_sold + qty_lost − qty_received.
Así un producto de baja rotación que está en 0 porque NO se repone (sin
demanda) NO se marca (opening = 0, no recibió) — evitamos inflar su demanda.
Un producto que abrió con stock y cerró en 0 SÍ se marca (se agotó).

Salvaguardas:
  - --dry-run por DEFECTO (no escribe; muestra cuántos días marcaría).
  - --apply requerido para persistir.
  - NUNCA toca filas forecast_only=True (histórico Fudo importado sin
    StockMoves — no se puede reconstruir ni se debe sobreescribir).
"""
from collections import defaultdict
from datetime import timedelta, date as date_cls
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Tenant
from catalog.models import Product
from inventory.models import StockItem, StockMove
from forecast.models import DailySales


ZERO = Decimal("0.000")


def _move_delta(move_type, qty):
    """Delta de stock de un movimiento. IN suma, OUT resta, ADJ ya trae signo."""
    q = qty or ZERO
    if move_type == StockMove.OUT:
        return -q
    return q  # IN y ADJ (ADJ con su propio signo)


class Command(BaseCommand):
    help = "Reconstruye closing_stock desde StockMove y marca is_stockout retroactivo (F1.1)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: todos)")
        parser.add_argument("--days", type=int, default=180, help="Días hacia atrás a reconstruir (default 180)")
        parser.add_argument("--apply", action="store_true", help="Persistir cambios (sin esto es dry-run)")

    def handle(self, *args, **opts):
        apply = opts["apply"]
        days = max(1, opts["days"])
        today = date_cls.today()
        start = today - timedelta(days=days)

        tenants = (
            Tenant.objects.filter(id=opts["tenant"]) if opts["tenant"]
            else Tenant.objects.all()
        )

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"[{mode}] backfill_stockout_detection — rango {start} → {today}")

        grand = {"filled_closing": 0, "marked_stockout": 0, "rows": 0, "skipped_forecast_only": 0}

        for tenant in tenants:
            res = self._process_tenant(tenant, start, today, apply)
            for k in grand:
                grand[k] += res[k]
            if res["rows"]:
                self.stdout.write(
                    f"  tenant {tenant.id} ({tenant.name}): "
                    f"{res['rows']} días, closing reconstruido {res['filled_closing']}, "
                    f"stockout marcados {res['marked_stockout']}, "
                    f"forecast_only saltados {res['skipped_forecast_only']}"
                )

        self.stdout.write(self.style.SUCCESS(
            f"[{mode}] TOTAL: {grand['rows']} días procesados · "
            f"closing reconstruido {grand['filled_closing']} · "
            f"stockout marcados {grand['marked_stockout']} · "
            f"forecast_only saltados {grand['skipped_forecast_only']}"
        ))
        if not apply:
            self.stdout.write(self.style.WARNING("Dry-run: nada escrito. Re-corré con --apply para persistir."))

    def _process_tenant(self, tenant, start, today, apply):
        res = {"filled_closing": 0, "marked_stockout": 0, "rows": 0, "skipped_forecast_only": 0}

        # Saldo vivo por (product, warehouse)
        on_hand = {
            (si.product_id, si.warehouse_id): (si.on_hand or ZERO)
            for si in StockItem.objects.filter(tenant=tenant)
        }
        if not on_hand:
            return res

        # Movimientos del rango: delta por (p, w, día). Traemos TODOS los
        # move_type (IN/OUT/ADJ, incluidos SALE_VOID/PURCHASE_VOID que son
        # IN/OUT) para reconstruir el saldo correctamente.
        delta_by_pw_day = defaultdict(lambda: defaultdict(lambda: ZERO))
        moves = (
            StockMove.objects.filter(tenant=tenant, created_at__date__gte=start)
            .values_list("product_id", "warehouse_id", "move_type", "qty", "created_at")
        )
        for pid, wid, mtype, qty, created_at in moves.iterator():
            d = timezone.localtime(created_at).date() if timezone.is_aware(created_at) else created_at.date()
            delta_by_pw_day[(pid, wid)][d] += _move_delta(mtype, qty)

        # DailySales del rango (solo reales, no forecast_only) indexados por (p,w)
        ds_rows = DailySales.objects.filter(
            tenant=tenant, date__gte=start, date__lte=today,
        ).only(
            "id", "product_id", "warehouse_id", "date", "qty_sold",
            "qty_lost", "qty_received", "forecast_only", "closing_stock", "is_stockout",
        )

        updates = []  # (ds_id, closing, is_stockout)
        # Cache de closing reconstruido por (p,w) -> {date: closing}
        closing_cache = {}

        for ds in ds_rows.iterator():
            if ds.forecast_only:
                res["skipped_forecast_only"] += 1
                continue
            key = (ds.product_id, ds.warehouse_id)
            if key not in on_hand:
                continue  # sin StockItem → no se puede reconstruir
            if key not in closing_cache:
                closing_cache[key] = self._reconstruct_closing(
                    on_hand[key], delta_by_pw_day.get(key, {}), start, today,
                )
            closing = closing_cache[key].get(ds.date)
            if closing is None:
                continue

            qty_sold = ds.qty_sold or ZERO
            qty_lost = ds.qty_lost or ZERO
            qty_received = ds.qty_received or ZERO
            opening = closing + qty_sold + qty_lost - qty_received
            is_stockout = (closing <= ZERO) and (opening > ZERO or qty_received > ZERO)

            updates.append((ds.id, closing.quantize(Decimal("0.001")), is_stockout))
            res["rows"] += 1
            res["filled_closing"] += 1
            if is_stockout:
                res["marked_stockout"] += 1

        if apply and updates:
            # Bulk update en chunks
            from django.db import transaction
            with transaction.atomic():
                for ds_id, closing, is_stockout in updates:
                    DailySales.objects.filter(id=ds_id).update(
                        closing_stock=closing, is_stockout=is_stockout,
                    )
        return res

    @staticmethod
    def _reconstruct_closing(on_hand_now, delta_by_day, start, today):
        """closing(D) backward desde on_hand. Itera de hoy hacia atrás:
        closing(today) = on_hand_now (saldo vivo); closing(D-1) = closing(D) − delta(D).
        """
        closing = {}
        # Días del rango, del más reciente al más antiguo
        n = (today - start).days
        days_desc = [today - timedelta(days=i) for i in range(0, n + 1)]
        prev_d = None
        for i, d in enumerate(days_desc):
            if i == 0:
                closing[d] = on_hand_now
            else:
                # closing(d) = closing(prev_d) − delta(prev_d)
                closing[d] = closing[prev_d] - delta_by_day.get(prev_d, ZERO)
            prev_d = d
        return closing
