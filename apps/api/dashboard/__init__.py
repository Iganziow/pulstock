# dashboard/__init__.py
"""
GET /api/dashboard/summary/
Devuelve KPIs + datos para el dashboard principal.
Store-aware: todo filtrado por active_store.

Cache (Daniel 30/04/26 — Fase 1 escalabilidad):
- Si `settings.CACHE_DASHBOARD_ENABLED=True`, el resultado se cachea
  en Redis por `CACHE_DASHBOARD_TTL` segundos (default 30s).
- Cache key incluye tenant_id + store_id + fecha local — multi-tenant
  safe + invalidación natural al cambio de día.
- TTL corto (30s) → datos máximo 30s desactualizados. Aceptable para
  un overview (no es real-time crítico, para eso está caja/POS).
- Para activar/desactivar sin redeploy: env var `CACHE_DASHBOARD_ENABLED=1`
  y reload gunicorn (HUP).
- Si Redis cae, fallback transparente al cómputo en vivo (try/except).
"""
import logging
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import (
    Sum, Count, Q, F, Value, DecimalField,
    Case, When,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from core.permissions import HasTenant
from sales.models import Sale, SaleLine
from purchases.models import Purchase
from inventory.models import StockItem, StockMove
from catalog.models import Product

_logger = logging.getLogger(__name__)


def _tenant_id(request):
    return getattr(request.user, "tenant_id", None)


def _active_store_id(request):
    return getattr(request.user, "active_store_id", None)


class DashboardSummaryView(APIView):
    """
    Un solo endpoint que devuelve todo lo necesario para el dashboard.
    Optimizado: máximo 6 queries livianas.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _tenant_id(request)
        s_id = _active_store_id(request)

        if not t_id:
            return Response(
                {"detail": "User must have a tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not s_id:
            return Response(
                {"detail": "active_store is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.localtime(timezone.now())
        today = now.date()
        week_ago = today - timedelta(days=6)  # últimos 7 días incluyendo hoy

        # ─── Cache lookup (feature flag) ─────────────────────────
        # Si CACHE_DASHBOARD_ENABLED=False, comportamiento idéntico al
        # anterior (sin cache). Si True, intenta servir desde Redis.
        # Si Redis cae, fallback transparente al cómputo en vivo (NO
        # rompe el endpoint).
        cache_enabled = getattr(settings, "CACHE_DASHBOARD_ENABLED", False)
        cache_key = None
        if cache_enabled:
            cache_key = f"dashboard:summary:t{t_id}:s{s_id}:{today.isoformat()}"
            try:
                cached = cache.get(cache_key)
            except Exception as exc:
                _logger.warning("Cache GET failed (Redis down?): %s", exc)
                cached = None
                cache_key = None  # disable cache.set también
            if cached is not None:
                resp = Response(cached)
                resp["X-Cache"] = "HIT"
                return resp

        # ──────────────────────────────────────────────
        # 1) KPI: Ventas de hoy (COMPLETED)
        # ──────────────────────────────────────────────
        # CONSUMO_INTERNO no es ingreso del local — se excluye del KPI
        # de "ventas de hoy" para que el monto refleje sólo facturación
        # real al cliente. Antes los consumos internos inflaban el KPI
        # y confundían al dueño.
        sales_today_qs = Sale.objects.filter(
            tenant_id=t_id,
            store_id=s_id,
            status=Sale.STATUS_COMPLETED,
            sale_type=Sale.SALE_TYPE_VENTA,
            created_at__date=today,
        )
        sales_today_agg = sales_today_qs.aggregate(
            count=Count("id"),
            total=Coalesce(
                Sum("total"), Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            profit=Coalesce(
                Sum("gross_profit"), Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            ),
        )

        # ──────────────────────────────────────────────
        # 2) KPI: Stock bajo mínimo
        # ──────────────────────────────────────────────
        low_stock_count = (
            StockItem.objects.filter(
                tenant_id=t_id,
                warehouse__store_id=s_id,
                product__is_active=True,
                product__min_stock__gt=0,
            )
            .filter(on_hand__lt=F("product__min_stock"))
            .count()
        )

        # ──────────────────────────────────────────────
        # 3) KPI: Stock valorizado total (del store)
        # ──────────────────────────────────────────────
        stock_agg = StockItem.objects.filter(
            tenant_id=t_id,
            warehouse__store_id=s_id,
        ).aggregate(
            total_value=Coalesce(
                Sum("stock_value"), Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            ),
            total_items=Count("id"),
        )

        # ──────────────────────────────────────────────
        # 4) KPI: Compras pendientes (DRAFT)
        # ──────────────────────────────────────────────
        pending_purchases = Purchase.objects.filter(
            tenant_id=t_id,
            store_id=s_id,
            status=Purchase.STATUS_DRAFT,
        ).aggregate(
            count=Count("id"),
            total=Coalesce(
                Sum("total_cost"), Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=3),
            ),
        )

        # ──────────────────────────────────────────────
        # 5) Últimas 8 ventas (para tabla)
        # ──────────────────────────────────────────────
        recent_sales = list(
            Sale.objects.filter(
                tenant_id=t_id,
                store_id=s_id,
            )
            .select_related("created_by", "warehouse")
            .order_by("-id")[:8]
        )

        recent_sales_data = [
            {
                "id": s.id,
                "created_at": timezone.localtime(s.created_at).isoformat() if s.created_at else None,
                "total": str(s.total),
                "gross_profit": str(s.gross_profit),
                "status": s.status,
                "warehouse_name": s.warehouse.name if s.warehouse else None,
                "created_by": getattr(s.created_by, "username", None),
                "lines_count": None,  # evita N+1; si lo necesitas, annotate
            }
            for s in recent_sales
        ]

        # ──────────────────────────────────────────────
        # 6) Ventas diarias últimos 7 días (para chart)
        # ──────────────────────────────────────────────
        daily_sales = (
            Sale.objects.filter(
                tenant_id=t_id,
                store_id=s_id,
                status=Sale.STATUS_COMPLETED,
                sale_type=Sale.SALE_TYPE_VENTA,
                created_at__date__gte=week_ago,
                created_at__date__lte=today,
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                total=Coalesce(
                    Sum("total"), Decimal("0"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                ),
                count=Count("id"),
                profit=Coalesce(
                    Sum("gross_profit"), Decimal("0"),
                    output_field=DecimalField(max_digits=14, decimal_places=3),
                ),
            )
            .order_by("day")
        )

        # rellenar días sin ventas con 0
        daily_map = {r["day"]: r for r in daily_sales}
        chart_data = []
        for i in range(7):
            d = week_ago + timedelta(days=i)
            row = daily_map.get(d)
            chart_data.append({
                "date": d.isoformat(),
                "total": str(row["total"]) if row else "0",
                "count": row["count"] if row else 0,
                "profit": str(row["profit"]) if row else "0",
            })

        # ──────────────────────────────────────────────
        # 7) Top 5 productos bajo mínimo (detalle)
        # ──────────────────────────────────────────────
        low_stock_items = list(
            StockItem.objects.filter(
                tenant_id=t_id,
                warehouse__store_id=s_id,
                product__is_active=True,
                product__min_stock__gt=0,
            )
            .filter(on_hand__lt=F("product__min_stock"))
            .select_related("product", "warehouse")
            .order_by("on_hand")[:5]
        )
        low_stock_data = [
            {
                "product_id": si.product_id,
                "product_name": si.product.name,
                "sku": getattr(si.product, "sku", None),
                "warehouse_name": si.warehouse.name,
                "on_hand": str(si.on_hand),
                "min_stock": str(si.product.min_stock),
                "deficit": str(si.product.min_stock - si.on_hand),
            }
            for si in low_stock_items
        ]

        # ──────────────────────────────────────────────
        # 8) Counters rápidos para el onboarding
        # ──────────────────────────────────────────────
        products_count = Product.objects.filter(
            tenant_id=t_id, is_active=True
        ).count()

        response_data = {
            "generated_at": now.isoformat(),
            "store_id": s_id,

            "kpis": {
                "sales_today": {
                    "count": sales_today_agg["count"] or 0,
                    "total": str(sales_today_agg["total"]),
                    "profit": str(sales_today_agg["profit"]),
                },
                "low_stock": {
                    "count": low_stock_count,
                },
                "stock_value": {
                    "total_value": str(stock_agg["total_value"]),
                    "total_items": stock_agg["total_items"] or 0,
                },
                "pending_purchases": {
                    "count": pending_purchases["count"] or 0,
                    "total": str(pending_purchases["total"]),
                },
            },

            "chart": chart_data,
            "recent_sales": recent_sales_data,
            "low_stock_items": low_stock_data,

            "onboarding": {
                "has_products": products_count > 0,
                "products_count": products_count,
            },
        }
        # Persistir en cache si está habilitado. Si Redis cae, ignoramos
        # silenciosamente (endpoint sigue funcionando).
        if cache_enabled and cache_key:
            try:
                ttl = getattr(settings, "CACHE_DASHBOARD_TTL", 30)
                cache.set(cache_key, response_data, timeout=ttl)
            except Exception as exc:
                _logger.warning("Cache SET failed (Redis down?): %s", exc)
        resp = Response(response_data)
        if cache_enabled:
            resp["X-Cache"] = "MISS"
        return resp