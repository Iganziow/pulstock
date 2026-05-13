"""
compute_category_profiles
=========================
Nightly cron (02:30): computes per-category demand prior for Bayesian forecasts.

Usage:
    python manage.py compute_category_profiles
    python manage.py compute_category_profiles --tenant 1
    python manage.py compute_category_profiles --days 60

Estadística usada (cambio 13/05/26)
-----------------------------------
Antes: promedio simple de los promedios diarios por producto.
  Problema: 1 producto popular (ej: Café Americano vende 50/día) infla
  el avg para todos los productos de la categoría. Resultado: el
  category_prior predecía 13/día para "Caja torta" (real 0,1/día) →
  WAPE 552% en producción.

Ahora: MEDIANA de productos con consumo > 0.
  - Robusta a outliers: 1 producto popular no afecta a los lentos.
  - Excluye productos con 0 ventas en la ventana (no son señal del
    nivel "típico" de la categoría, son ruido).
  - Si todos los productos venden 0, devuelve 0 (categoría inactiva).

Reportado por Mario el 13/05/26. Documentado en superadmin/forecast.
"""
import statistics
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models import Tenant, Warehouse
from catalog.models import Product
from forecast.models import DailySales, CategoryDemandProfile


def category_prior_estimator(per_product_avgs):
    """
    Calcula el "nivel típico" de demanda diaria de una categoría.

    Política (13/05/26):
      1. Excluir productos con 0 ventas (ruido — no muestran el nivel
         típico de la categoría, solo dicen "esto no se vende").
      2. Tomar la MEDIANA de los restantes.
      3. Si todos son 0, devolver 0 (categoría inactiva — predicción
         razonable: no se va a vender).
    """
    nonzero = [v for v in per_product_avgs if v > 0]
    if not nonzero:
        return 0.0
    return statistics.median(nonzero)


class Command(BaseCommand):
    help = "Compute average demand per category for Bayesian prior forecasts"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, help="Specific tenant ID")
        parser.add_argument("--days", type=int, default=60, help="Days of history to use (default: 60)")

    def handle(self, *args, **options):
        lookback = max(7, options["days"])
        cutoff = date.today() - timedelta(days=lookback)

        tenants = Tenant.objects.all()
        if options["tenant"]:
            tenants = tenants.filter(id=options["tenant"])

        total = 0
        for tenant in tenants:
            total += self._process_tenant(tenant, cutoff, lookback)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {total} category profiles computed/updated"
        ))

    def _process_tenant(self, tenant, cutoff, lookback):
        # Get all warehouses for this tenant
        warehouse_ids = list(
            Warehouse.objects.filter(tenant=tenant).values_list("id", flat=True)
        )

        # Get all products with their categories
        products_with_cat = dict(
            Product.objects.filter(tenant=tenant, is_active=True, category__isnull=False)
            .values_list("id", "category_id")
        )

        if not products_with_cat:
            return 0

        # Aggregate DailySales per (product, warehouse) since cutoff
        daily_data = (
            DailySales.objects.filter(
                tenant=tenant,
                date__gte=cutoff,
                product_id__in=products_with_cat.keys(),
            )
            .values("product_id", "warehouse_id")
            .annotate(
                total_qty=Coalesce(Sum("qty_sold"), Decimal("0.000")),
                day_count=Count("date", distinct=True),
            )
        )

        # Group by (category, warehouse)
        # cat_wh_data[cat_id][wh_id] = list of (product_total_qty, product_day_count)
        cat_wh_data = defaultdict(lambda: defaultdict(list))
        for row in daily_data:
            cat_id = products_with_cat.get(row["product_id"])
            if cat_id:
                cat_wh_data[cat_id][row["warehouse_id"]].append({
                    "product_id": row["product_id"],
                    "total_qty": row["total_qty"],
                    "day_count": row["day_count"],
                })

        # Compute DOW factors per (category, warehouse) from raw DailySales
        dow_data = defaultdict(lambda: defaultdict(list))
        raw_dow = (
            DailySales.objects.filter(
                tenant=tenant,
                date__gte=cutoff,
                product_id__in=products_with_cat.keys(),
            )
            .values("product_id", "warehouse_id", "date", "qty_sold")
        )
        for row in raw_dow:
            cat_id = products_with_cat.get(row["product_id"])
            if cat_id:
                dow = row["date"].weekday()
                dow_data[(cat_id, row["warehouse_id"])][dow].append(float(row["qty_sold"]))

        count = 0
        for cat_id, wh_dict in cat_wh_data.items():
            for wh_id, product_stats in wh_dict.items():
                # avg_daily_demand = mean of (product_total / product_days) across products
                per_product_avgs = []
                for ps in product_stats:
                    if ps["day_count"] > 0:
                        per_product_avgs.append(
                            float(ps["total_qty"]) / ps["day_count"]
                        )

                if not per_product_avgs:
                    continue

                # MEDIANA (en vez de promedio) de productos con consumo > 0.
                # Ver docstring del módulo para el por qué del cambio.
                # Mantenemos el nombre `avg_daily` por retrocompat con el
                # field y los modelos consumidores — semánticamente ahora
                # es "nivel típico" no "promedio".
                avg_daily = Decimal(str(
                    category_prior_estimator(per_product_avgs)
                )).quantize(Decimal("0.001"))

                # DOW factors for this category+warehouse.
                # Días sin ventas en TODA la categoría con >= 4 ocurrencias
                # → factor 0 (asumimos local cerrado ese día). Sin esto,
                # el forecast del category_prior predecía ventas en
                # domingos cuando la cafetería no abre.
                import datetime as _dt
                dow_key = (cat_id, wh_id)
                # Calcular días que se cubrió en el lookback
                end_date = _dt.date.today()
                start_date = end_date - _dt.timedelta(days=lookback)
                dow_occurrences = {dow: 0 for dow in range(7)}
                for i in range(lookback + 1):
                    d = start_date + _dt.timedelta(days=i)
                    dow_occurrences[d.weekday()] += 1
                overall_avg = float(avg_daily) if avg_daily > 0 else 1.0
                dow_factors = {}
                for dow in range(7):
                    values = dow_data[dow_key].get(dow, [])
                    if values:
                        dow_avg = sum(values) / len(values)
                        dow_factors[dow] = round(dow_avg / overall_avg, 3) if overall_avg > 0 else 1.0
                    elif dow_occurrences.get(dow, 0) >= 4:
                        dow_factors[dow] = 0.0  # local cerrado ese día
                    else:
                        dow_factors[dow] = 1.0

                # NORMALIZACIÓN (13/05/26)
                # ──────────────────────────
                # Los dow_factors son RATIOS (consumo del día / avg_daily)
                # y por construcción su promedio debería ser ~1.0 para
                # que la predicción semanal cuadre con 7×avg_daily.
                # PERO: el numerador (`dow_avg`) usa el promedio bruto
                # de TODOS los productos de la categoría ese día, mientras
                # que el denominador (`avg_daily`) ahora usa la MEDIANA
                # de productos con consumo>0. Esos dos no son
                # comparables — su ratio puede dar 30+ y eso re-infla
                # las predicciones.
                #
                # Fix: renormalizar los factores >0 para que promedien
                # exactamente 1.0. Preserva la FORMA semanal (qué día
                # vende más vs menos) pero no escala el avg.
                positive_factors = [v for v in dow_factors.values() if v > 0]
                if positive_factors:
                    factor_mean = sum(positive_factors) / len(positive_factors)
                    if factor_mean > 0:
                        dow_factors = {
                            k: round(v / factor_mean, 3) if v > 0 else 0.0
                            for k, v in dow_factors.items()
                        }

                CategoryDemandProfile.objects.update_or_create(
                    tenant=tenant,
                    category_id=cat_id,
                    warehouse_id=wh_id,
                    defaults={
                        "avg_daily_demand": avg_daily,
                        "product_count": len(per_product_avgs),
                        "data_days": lookback,
                        "dow_factors": dow_factors,
                    },
                )
                count += 1

        return count
