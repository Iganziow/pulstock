"""
aggregate_daily_sales
=====================
Nightly cron (02:00): aggregates SaleLines and StockMoves into DailySales.

Usage:
    python manage.py aggregate_daily_sales              # yesterday
    python manage.py aggregate_daily_sales --date 2026-02-20
    python manage.py aggregate_daily_sales --days 30    # backfill last 30 days
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
import logging

from core.heartbeat import with_heartbeat
from core.multi_tenant import exigir_todos, por_tenant, tenants_a_procesar
from django.db.models import Sum
from django.db.models.functions import Coalesce

from core.models import Tenant
from inventory.models import StockMove, StockItem
from sales.models import SaleLine, Sale
from forecast.models import DailySales

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Aggregate daily sales, losses and receipts into DailySales table"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="Specific date YYYY-MM-DD (default: yesterday)")
        parser.add_argument("--days", type=int, default=1, help="Number of days to backfill (default: 1 = yesterday)")
        parser.add_argument("--tenant", type=int, help="Specific tenant ID (default: all)")

    @with_heartbeat("aggregate_daily_sales")
    def handle(self, *args, **options):
        target_date = None
        if options["date"]:
            target_date = date.fromisoformat(options["date"])
            days_to_process = [target_date]
        else:
            num_days = max(1, options["days"])
            today = date.today()
            days_to_process = [today - timedelta(days=i) for i in range(1, num_days + 1)]

        tenants = tenants_a_procesar(options, command=self)

        total_created = 0
        total_updated = 0

        def _un_tenant(tenant):
            nonlocal total_created, total_updated
            for d in days_to_process:
                created, updated = self._aggregate_day(tenant, d)
                total_created += created
                total_updated += updated

        # Aislado por negocio: sin esto, la excepcion del primer tenant deja a
        # todos los siguientes sin demanda agregada, y en silencio.
        ok, fallidos = por_tenant(tenants, _un_tenant, command=self)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {total_created} created, {total_updated} updated across {len(days_to_process)} day(s)"
        ))
        exigir_todos(ok, fallidos, command=self)

    def _consumo_teorico(self, tenant, target_date):
        """{(product_id, warehouse_id): qty} que las ventas COMPLETED/VENTA del
        dia debieron descontar segun las recetas activas, con la misma
        expansion que create_sale. Incluye los productos sin receta vendidos
        directo (expand_recipes los deja pasar con su cantidad). Si la
        configuracion de recetas esta rota (ciclo, receta activa sin lineas),
        se avisa y se vuelve al comportamiento anterior para esa bodega."""
        from collections import defaultdict
        from sales.recipes import expand_recipes

        por_bodega = defaultdict(lambda: defaultdict(lambda: Decimal("0.000")))
        for pid, wh, qty in SaleLine.objects.filter(
            tenant=tenant,
            sale__created_at__date=target_date,
            sale__sale_type="VENTA",
            sale__status=Sale.STATUS_COMPLETED,
        ).values_list("product_id", "sale__warehouse_id", "qty"):
            por_bodega[wh][pid] += qty or Decimal("0.000")

        teorico = {}
        for wh, agg in por_bodega.items():
            try:
                expanded, _ = expand_recipes(
                    {pid: {"qty": q, "unit_price": Decimal("0")} for pid, q in agg.items() if q > 0},
                    tenant.id,
                )
            except Exception as exc:
                logger.warning(
                    "aggregate_daily_sales: no se pudo expandir las recetas de "
                    "tenant %s bodega %s el %s (%s); qty_sold usa solo el kardex.",
                    tenant.id, wh, target_date, exc,
                )
                continue
            for pid, data in expanded.items():
                if data["qty"] > 0:
                    teorico[(pid, wh)] = data["qty"]
        return teorico

    def _aggregate_day(self, tenant, target_date):
        """Aggregate all sales, losses, and receipts for one tenant on one day."""
        created = 0
        updated = 0

        # F-VOID (19/06/26): ventas ANULADAS (status=VOID) NO son demanda.
        # Sus StockMove OUT/SALE y SaleLines seguían contándose → inflaban
        # qty_sold/revenue del forecast (auditoría: 22 voids = 3.330 u fuga).
        # Excluimos sus ids acá. OJO: una venta anulada DESPUÉS del día en que
        # se hizo requiere re-agregar ese día (backfill) para limpiarse.
        voided_ids = list(
            Sale.objects.filter(tenant=tenant, status=Sale.STATUS_VOID)
            .values_list("id", flat=True)
        )

        # ── Sales: SaleLine grouped by product + warehouse ──
        # Solo usamos SaleLine para revenue / total_cost / gross_profit:
        # esos son atributos del producto VENDIDO directamente (Latte vainilla,
        # Cappuccino, etc.), no de los ingredientes que se descuentan vía receta.
        # Para qty_sold usamos StockMove (ver más abajo).
        # F28: solo VENTA real (excluir CONSUMO_INTERNO). El consumo interno
        # no genera ingreso ni demanda → no debe sumar a revenue ni servir de
        # fallback de qty_sold.
        sale_agg = (
            SaleLine.objects.filter(
                tenant=tenant,
                sale__created_at__date=target_date,
                sale__sale_type="VENTA",
                sale__status=Sale.STATUS_COMPLETED,  # F-VOID: excluir anuladas
            )
            .values("product_id", "sale__warehouse_id")
            .annotate(
                total_qty=Coalesce(Sum("qty"), Decimal("0.000")),
                total_revenue=Coalesce(Sum("line_total"), Decimal("0.00")),
                total_cost=Coalesce(Sum("line_cost"), Decimal("0.00")),
            )
        )

        # Build a map: (product_id, warehouse_id) -> {qty_sold, revenue}
        sales_map = {}
        for row in sale_agg:
            key = (row["product_id"], row["sale__warehouse_id"])
            revenue = row["total_revenue"] or Decimal("0.00")
            cost = row["total_cost"] or Decimal("0.00")
            sales_map[key] = {
                "qty_sold_direct": row["total_qty"] or Decimal("0.000"),
                "revenue": revenue,
                "total_cost": cost,
                "gross_profit": revenue - cost,
            }

        # ── Demanda real: StockMove OUT con ref_type=SALE ──────────────────
        # Este es el descuento físico de stock que generó la venta. Incluye:
        # 1) ventas directas (Cappuccino, etc.)
        # 2) ingredientes consumidos vía expansión de receta (recursiva).
        #
        # Antes: qty_sold se tomaba de SaleLine. Si la "Leche entera" se vendía
        # directa Y se consumía como ingrediente de cafés, qty_sold solo
        # contaba la venta directa → el forecast subestimaba la demanda real
        # de leche. El PASO 2 (más abajo) trataba de cubrir el caso "puro
        # ingrediente" pero excluía explícitamente los productos vendidos
        # directos → bug.
        #
        # Fix: usar StockMove como fuente única de verdad para qty_sold.
        # Cubre los 3 casos (puro directo, puro ingrediente, mixto).
        # OFFLINE entra junto con SALE porque ES una venta: la que ocurrio
        # mientras el sistema estaba caido y Mario declaro despues. Si no se
        # contara, la demanda de ese dia quedaria en cero, el modelo aprenderia
        # que se vende menos de lo real y la sugerencia pediria de menos — y el
        # error se acumularia en cada corte de luz.
        stockmove_sale_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="OUT",
                ref_type__in=("SALE", "OFFLINE"),
            )
            .exclude(ref_id__in=voided_ids)  # F-VOID: demanda sin ventas anuladas
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        consumed_map = {
            (row["product_id"], row["warehouse_id"]): row["total_qty"] or Decimal("0.000")
            for row in stockmove_sale_agg
        }

        # ── Consumo TEORICO por receta (05/09/26) ──────────────────────────
        # El StockMove es el kardex, pero NO siempre es la demanda: un
        # ingrediente con allow_negative_stock=True y stock en cero deja pasar
        # la venta del padre con descuento CLAMPEADO a 0 y sin movimiento
        # (create_sale, paso 8). La venta ocurrio, el jamon se uso (del stock
        # que el sistema no conocia), y no quedo registro en ninguna parte.
        # Medido en Marbrava, 30 dias: Jamon granel 274 g movidos contra
        # 1.050 g por receta (24 de 32 Selladitas sin descuento), Helado
        # vainilla 400 contra 1.400, Chantilly 310 contra 370. El modelo
        # directo aprendia esa demanda censurada y la sugerencia pedia un
        # tercio de lo que se usa.
        #
        # Aca se expanden las ventas del dia con la MISMA funcion que usa la
        # venta (expand_recipes: recetas anidadas, conversion de unidades) y
        # qty_sold toma el MAYOR entre lo movido y lo teorico. Si la receta se
        # edito despues de la venta, una re-agregacion usa la receta de hoy:
        # aceptable, la agregacion nocturna es de ayer.
        teorico_map = self._consumo_teorico(tenant, target_date)

        # ── F28: consumo INTERNO (regalos/muestras/staff) ──────────────────
        # Descuenta stock igual que una venta, pero NO es demanda → se agrega
        # aparte (qty_sold_internal) y NO entra en qty_sold del forecast.
        internal_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="OUT",
                ref_type="INTERNAL",
            )
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        internal_map = {
            (row["product_id"], row["warehouse_id"]): row["total_qty"] or Decimal("0.000")
            for row in internal_agg
        }

        # ── Promotional sales: SaleLines with promotion set ──
        promo_agg = (
            SaleLine.objects.filter(
                tenant=tenant,
                sale__created_at__date=target_date,
                promotion__isnull=False,
            )
            .values("product_id", "sale__warehouse_id")
            .annotate(
                promo_qty=Coalesce(Sum("qty"), Decimal("0.000")),
                promo_revenue=Coalesce(Sum("line_total"), Decimal("0.00")),
            )
        )
        promo_map = {}
        for row in promo_agg:
            key = (row["product_id"], row["sale__warehouse_id"])
            promo_map[key] = {
                "promo_qty": row["promo_qty"] or Decimal("0.000"),
                "promo_revenue": row["promo_revenue"] or Decimal("0.00"),
            }

        # ── Losses: StockMoves OUT with ref_type=ISSUE ──
        loss_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="OUT",
                ref_type="ISSUE",
            )
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        loss_map = {}
        for row in loss_agg:
            key = (row["product_id"], row["warehouse_id"])
            loss_map[key] = row["total_qty"] or Decimal("0.000")

        # ── Receipts: StockMoves IN with ref_type=RECEIVE ──
        recv_agg = (
            StockMove.objects.filter(
                tenant=tenant,
                created_at__date=target_date,
                move_type="IN",
                ref_type="RECEIVE",
            )
            .values("product_id", "warehouse_id")
            .annotate(total_qty=Coalesce(Sum("qty"), Decimal("0.000")))
        )
        recv_map = {}
        for row in recv_agg:
            key = (row["product_id"], row["warehouse_id"])
            recv_map[key] = row["total_qty"] or Decimal("0.000")

        # ── Merge all keys ──
        # Incluimos consumed_map para que ingredientes consumidos vía recetas
        # (que NO aparecen en SaleLine) también generen su DailySales.
        all_keys = (
            set(sales_map.keys())
            | set(loss_map.keys())
            | set(recv_map.keys())
            | set(consumed_map.keys())
            | set(internal_map.keys())
            | set(teorico_map.keys())
        )

        for product_id, warehouse_id in all_keys:
            sale_data = sales_map.get((product_id, warehouse_id), {})
            # qty_sold = demanda total (directa + via recetas), desde StockMove.
            # Fallback a SaleLine.qty solo si NO hubo StockMove (caso raro:
            # venta de producto sin descuento de stock — p. ej. servicio o
            # producto con allow_negative=True y stock=0 que después del fix
            # del PR #87 ya no genera StockMove). Mantenemos el fallback para
            # no perder esa demanda en el forecast.
            consumed_qty = consumed_map.get((product_id, warehouse_id), Decimal("0.000"))
            direct_qty = sale_data.get("qty_sold_direct", Decimal("0.000"))
            teorico_qty = teorico_map.get((product_id, warehouse_id), Decimal("0.000"))
            # Demanda = lo que se descontó o lo que la receta dice que se usó,
            # el mayor (ver "Consumo TEORICO" arriba). Un producto CON receta
            # vendido directo no está en ninguno de los dos (es virtual):
            # conserva la venta directa.
            qty_sold = max(consumed_qty, teorico_qty)
            if qty_sold <= 0:
                qty_sold = direct_qty
            revenue = sale_data.get("revenue", Decimal("0.00"))
            total_cost = sale_data.get("total_cost", Decimal("0.00"))
            gross_profit = sale_data.get("gross_profit", Decimal("0.00"))
            qty_lost = loss_map.get((product_id, warehouse_id), Decimal("0.000"))
            qty_received = recv_map.get((product_id, warehouse_id), Decimal("0.000"))
            qty_sold_internal = internal_map.get((product_id, warehouse_id), Decimal("0.000"))
            promo_data = promo_map.get((product_id, warehouse_id), {})

            # Nunca sobreescribir registros importados como histórico externo
            if DailySales.objects.filter(
                tenant=tenant, product_id=product_id,
                warehouse_id=warehouse_id, date=target_date,
                forecast_only=True,
            ).exists():
                continue

            obj, was_created = DailySales.objects.update_or_create(
                tenant=tenant,
                product_id=product_id,
                warehouse_id=warehouse_id,
                date=target_date,
                defaults={
                    "qty_sold": qty_sold,
                    "revenue": revenue,
                    "total_cost": total_cost,
                    "gross_profit": gross_profit,
                    "qty_lost": qty_lost,
                    "qty_received": qty_received,
                    "qty_sold_internal": qty_sold_internal,
                    "promo_qty": promo_data.get("promo_qty", Decimal("0.000")),
                    "promo_revenue": promo_data.get("promo_revenue", Decimal("0.00")),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        # ── Closing stock + stockout detection ──
        # Snapshot stock at end of day for all products with activity.
        # If this is yesterday's aggregation, use current StockItem.on_hand as proxy.
        # For backfills, closing_stock is approximated.
        from datetime import date as date_cls
        today = date_cls.today()
        is_recent = (today - target_date).days <= 2

        if is_recent:
            stock_qs = StockItem.objects.filter(
                tenant=tenant,
                product_id__in={pid for (pid, _) in all_keys},
            ).values("product_id", "warehouse_id", "on_hand")
            stock_snapshot = {
                (r["product_id"], r["warehouse_id"]): r["on_hand"]
                for r in stock_qs
            }

            for product_id, warehouse_id in all_keys:
                closing = stock_snapshot.get((product_id, warehouse_id))
                if closing is None:
                    continue
                # F1.2 (Mario 29/05/26): qty_sold REAL = demanda total (directa
                # + vía recetas), desde StockMove. Antes se leía
                # sales_map[...]["qty_sold"] pero la clave es "qty_sold_direct"
                # → siempre 0, y la detección de stockout quedaba determinada
                # solo por closing<=0 (sobre-marcaba). Usamos consumed_map con
                # fallback a la venta directa, igual que qty_sold del registro.
                # Aca se usa lo MOVIDO, no el consumo teorico: el stock de
                # apertura se reconstruye desde el kardex. Con el teorico, un
                # ingrediente clampeado en 0 "abriria" con stock y quedaria
                # marcado como stockout (y clean_series le interpolaria
                # encima de la demanda ya recuperada en qty_sold).
                qty_sold = consumed_map.get((product_id, warehouse_id))
                if not qty_sold:
                    qty_sold = sales_map.get((product_id, warehouse_id), {}).get(
                        "qty_sold_direct", Decimal("0.000")
                    )
                qty_lost = loss_map.get((product_id, warehouse_id), Decimal("0.000"))
                qty_received = recv_map.get((product_id, warehouse_id), Decimal("0.000"))

                # Detección intra-día: el stock al INICIO del día = closing +
                # vendido + perdido − recibido. Marcamos stockout si cerró en 0
                # HABIENDO tenido stock al abrir (o habiendo recibido ese día) —
                # se agotó. Si abrió en 0 y no recibió (producto sin reponer,
                # sin demanda), NO lo marcamos: evita el falso positivo que
                # inflaría la demanda interpolada de productos de baja rotación.
                opening = closing + qty_sold + qty_lost - qty_received
                is_stockout = (closing <= Decimal("0.000")) and (
                    opening > Decimal("0.000") or qty_received > Decimal("0.000")
                )
                DailySales.objects.filter(
                    tenant=tenant,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    date=target_date,
                ).update(closing_stock=closing, is_stockout=is_stockout)

        # NOTA: el "PASO 2" original (que iteraba pure_ingredient_ids para
        # capturar consumo via recetas) quedó obsoleto al cambiar qty_sold
        # del PASO 1 a basarse en StockMove (consumed_map). Ahora el PASO 1
        # cubre los 3 casos:
        #   - producto vendido directamente (Cappuccino)
        #   - ingrediente puro (Leche solo usada en cafés)
        #   - mixto: vendido directo Y consumido como ingrediente
        # Los 3 generan StockMove OUT ref_type="SALE" → todos terminan en
        # consumed_map → DailySales correcto.

        return created, updated
