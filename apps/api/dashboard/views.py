# dashboard/views.py
"""
GET /api/dashboard/summary/
Resumen ejecutivo completo para el dashboard principal.
Store-aware: todo filtrado por active_store.
"""
from decimal import Decimal
from datetime import timedelta

from django.db.models import (
    Sum, Count, Avg, Q, F, Value, DecimalField,
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

D0 = Decimal("0")


def _t(request):
    return getattr(request.user, "tenant_id", None)


def _s(request):
    return getattr(request.user, "active_store_id", None)


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _t(request)
        s_id = _s(request)

        if not t_id or not s_id:
            return Response({"detail": "tenant and active_store required."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.localtime(timezone.now())
        today = now.date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=6)
        month_ago = today - timedelta(days=29)
        prev_month_start = today - timedelta(days=59)
        prev_month_end = today - timedelta(days=30)

        # ═══════════════════════════════════════════
        # 1) KPIs PRINCIPALES (consolidated queries)
        # ═══════════════════════════════════════════
        _df = DecimalField(max_digits=14, decimal_places=3)
        _df2 = DecimalField(max_digits=14, decimal_places=2)

        # Today + Yesterday en 1 query
        _base_q = dict(tenant_id=t_id, store_id=s_id, status=Sale.STATUS_COMPLETED, sale_type=Sale.SALE_TYPE_VENTA)
        recent_agg = Sale.objects.filter(
            **_base_q, created_at__date__gte=yesterday, created_at__date__lte=today,
        ).aggregate(
            today_count=Count("id", filter=Q(created_at__date=today)),
            today_total=Coalesce(Sum("total", filter=Q(created_at__date=today)), D0, output_field=_df2),
            today_profit=Coalesce(Sum("gross_profit", filter=Q(created_at__date=today)), D0, output_field=_df),
            today_cost=Coalesce(Sum("total_cost", filter=Q(created_at__date=today)), D0, output_field=_df),
            yest_count=Count("id", filter=Q(created_at__date=yesterday)),
            yest_total=Coalesce(Sum("total", filter=Q(created_at__date=yesterday)), D0, output_field=_df2),
            yest_profit=Coalesce(Sum("gross_profit", filter=Q(created_at__date=yesterday)), D0, output_field=_df),
        )
        today_agg = {"count": recent_agg["today_count"], "total": recent_agg["today_total"], "profit": recent_agg["today_profit"], "cost": recent_agg["today_cost"]}
        yesterday_agg = {"count": recent_agg["yest_count"], "total": recent_agg["yest_total"], "profit": recent_agg["yest_profit"]}

        # Month + Prev month en 1 query
        months_agg = Sale.objects.filter(
            **_base_q, created_at__date__gte=prev_month_start, created_at__date__lte=today,
        ).aggregate(
            m_count=Count("id", filter=Q(created_at__date__gte=month_ago)),
            m_total=Coalesce(Sum("total", filter=Q(created_at__date__gte=month_ago)), D0, output_field=_df2),
            m_profit=Coalesce(Sum("gross_profit", filter=Q(created_at__date__gte=month_ago)), D0, output_field=_df),
            m_cost=Coalesce(Sum("total_cost", filter=Q(created_at__date__gte=month_ago)), D0, output_field=_df),
            p_count=Count("id", filter=Q(created_at__date__lte=prev_month_end)),
            p_total=Coalesce(Sum("total", filter=Q(created_at__date__lte=prev_month_end)), D0, output_field=_df2),
            p_profit=Coalesce(Sum("gross_profit", filter=Q(created_at__date__lte=prev_month_end)), D0, output_field=_df),
        )
        month_agg = {"count": months_agg["m_count"], "total": months_agg["m_total"], "profit": months_agg["m_profit"], "cost": months_agg["m_cost"]}
        prev_month_agg = {"count": months_agg["p_count"], "total": months_agg["p_total"], "profit": months_agg["p_profit"]}

        # Margin %
        month_rev = month_agg["total"]
        month_margin = (month_agg["profit"] / month_rev * 100) if month_rev > 0 else D0
        prev_rev = prev_month_agg["total"]
        prev_margin = (prev_month_agg["profit"] / prev_rev * 100) if prev_rev > 0 else D0

        # Revenue change % (today vs yesterday)
        today_rev = today_agg["total"]
        yest_rev = yesterday_agg["total"]
        rev_change = ((today_rev - yest_rev) / yest_rev * 100) if yest_rev > 0 else None

        # Month revenue change %
        month_change = ((month_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else None

        # Ticket promedio
        avg_ticket = (today_rev / today_agg["count"]) if today_agg["count"] > 0 else D0

        # ═══════════════════════════════════════════
        # 2) STOCK KPIs
        # ═══════════════════════════════════════════
        stock_agg = StockItem.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id,
        ).aggregate(
            total_value=Coalesce(Sum("stock_value"), D0, output_field=DecimalField(max_digits=14, decimal_places=3)),
            total_items=Count("id"),
        )

        # low_stock_count se calcula junto con low_stock_items más abajo

        # ═══════════════════════════════════════════
        # 3) FORECAST ALERTS (if forecast app exists)
        # ═══════════════════════════════════════════
        forecast_alerts = {"imminent_3d": 0, "at_risk_7d": 0, "pending_suggestions": 0}
        try:
            from forecast.models import Forecast, PurchaseSuggestion
            from core.models import Warehouse
            wh_ids = list(Warehouse.objects.filter(store_id=s_id, tenant_id=t_id).values_list("id", flat=True))
            if wh_ids:
                tomorrow = today + timedelta(days=1)
                fc_qs = Forecast.objects.filter(
                    tenant_id=t_id, warehouse_id__in=wh_ids, forecast_date=tomorrow,
                )
                forecast_alerts["imminent_3d"] = fc_qs.filter(days_to_stockout__lte=3).count()
                forecast_alerts["at_risk_7d"] = fc_qs.filter(days_to_stockout__gt=3, days_to_stockout__lte=7).count()
                forecast_alerts["pending_suggestions"] = PurchaseSuggestion.objects.filter(
                    tenant_id=t_id, warehouse_id__in=wh_ids, status="PENDING"
                ).count()
        except ImportError:
            pass

        # ═══════════════════════════════════════════
        # 4) COMPRAS PENDIENTES
        # ═══════════════════════════════════════════
        pending_purchases = Purchase.objects.filter(
            tenant_id=t_id, store_id=s_id, status="DRAFT",
        ).aggregate(count=Count("id"), total=Coalesce(Sum("total_cost"), D0, output_field=DecimalField(max_digits=14, decimal_places=3)))

        # ═══════════════════════════════════════════
        # 5) CHART: Ventas últimos 30 días
        # ═══════════════════════════════════════════
        daily_sales = (
            Sale.objects.filter(
                tenant_id=t_id, store_id=s_id, status=Sale.STATUS_COMPLETED,
                sale_type=Sale.SALE_TYPE_VENTA,
                created_at__date__gte=month_ago, created_at__date__lte=today,
            )
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                total=Coalesce(Sum("total"), D0, output_field=DecimalField(max_digits=14, decimal_places=2)),
                count=Count("id"),
                profit=Coalesce(Sum("gross_profit"), D0, output_field=DecimalField(max_digits=14, decimal_places=3)),
            )
            .order_by("day")
        )
        daily_map = {r["day"]: r for r in daily_sales}
        chart_data = []
        for i in range(30):
            d = month_ago + timedelta(days=i)
            row = daily_map.get(d)
            chart_data.append({
                "date": d.isoformat(),
                "total": str(row["total"]) if row else "0",
                "count": row["count"] if row else 0,
                "profit": str(row["profit"]) if row else "0",
            })

        # ═══════════════════════════════════════════
        # 6) TOP 5 PRODUCTOS HOY
        # ═══════════════════════════════════════════
        top_today = list(
            SaleLine.objects.filter(
                tenant_id=t_id, sale__store_id=s_id,
                sale__status=Sale.STATUS_COMPLETED,
                sale__sale_type=Sale.SALE_TYPE_VENTA,
                sale__created_at__date=today,
            )
            .values("product_id", "product__name")
            .annotate(
                revenue=Coalesce(Sum("line_total"), D0),
                qty=Coalesce(Sum("qty"), D0),
                profit=Coalesce(Sum("line_gross_profit"), D0),
            )
            .order_by("-revenue")[:5]
        )

        # ═══════════════════════════════════════════
        # 7) ÚLTIMAS 6 VENTAS
        # ═══════════════════════════════════════════
        recent_sales = list(
            Sale.objects.filter(tenant_id=t_id, store_id=s_id)
            .select_related("created_by", "warehouse")
            .order_by("-id")[:6]
        )
        recent_sales_data = [
            {
                "id": s.id,
                "created_at": timezone.localtime(s.created_at).isoformat() if s.created_at else None,
                "total": str(s.total),
                "gross_profit": str(s.gross_profit),
                "status": s.status,
                "sale_type": s.sale_type,
                "warehouse_name": s.warehouse.name if s.warehouse else None,
                "created_by": getattr(s.created_by, "username", None),
            }
            for s in recent_sales
        ]

        # ═══════════════════════════════════════════
        # 8) LOW STOCK DETAIL (top 5)
        # ═══════════════════════════════════════════
        _low_stock_qs = StockItem.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id,
            product__is_active=True, product__min_stock__gt=0,
        ).filter(on_hand__lt=F("product__min_stock"))
        low_stock_count = _low_stock_qs.count()
        low_stock_items = list(
            _low_stock_qs.select_related("product", "warehouse")
            .order_by("on_hand")[:5]
        )
        low_stock_data = [
            {
                "product_id": si.product_id,
                "product_name": si.product.name,
                "on_hand": str(si.on_hand),
                "min_stock": str(si.product.min_stock),
                "deficit": str(si.product.min_stock - si.on_hand),
            }
            for si in low_stock_items
        ]

        # ═══════════════════════════════════════════
        # 9) ONBOARDING STATUS
        # ═══════════════════════════════════════════
        products_count = Product.objects.filter(tenant_id=t_id, is_active=True).count()
        total_sales = Sale.objects.filter(tenant_id=t_id, store_id=s_id, status=Sale.STATUS_COMPLETED, sale_type=Sale.SALE_TYPE_VENTA).count()

        return Response({
            "generated_at": now.isoformat(),
            "store_id": s_id,

            "kpis": {
                "sales_today": {
                    "count": today_agg["count"] or 0,
                    "total": str(today_rev),
                    "profit": str(today_agg["profit"]),
                    "avg_ticket": str(avg_ticket.quantize(Decimal("0.01")) if isinstance(avg_ticket, Decimal) else 0),
                    "vs_yesterday": str(rev_change.quantize(Decimal("0.1"))) if rev_change is not None and isinstance(rev_change, Decimal) else None,
                },
                "sales_month": {
                    "total": str(month_rev),
                    "profit": str(month_agg["profit"]),
                    "count": month_agg["count"] or 0,
                    "margin_pct": str(month_margin.quantize(Decimal("0.1")) if isinstance(month_margin, Decimal) else round(float(month_margin), 1)),
                    "vs_prev_month": str(month_change.quantize(Decimal("0.1"))) if month_change is not None and isinstance(month_change, Decimal) else None,
                    "prev_margin_pct": str(prev_margin.quantize(Decimal("0.1")) if isinstance(prev_margin, Decimal) else round(float(prev_margin), 1)),
                },
                "stock": {
                    "total_value": str(stock_agg["total_value"]),
                    "total_items": stock_agg["total_items"] or 0,
                    "low_stock_count": low_stock_count,
                },
                "forecast": forecast_alerts,
                "pending_purchases": {
                    "count": pending_purchases["count"] or 0,
                    "total": str(pending_purchases["total"]),
                },
            },

            "chart": chart_data,
            "top_products_today": [
                {
                    "product_id": r["product_id"],
                    "product_name": r["product__name"],
                    "revenue": str(r["revenue"]),
                    "qty": str(r["qty"]),
                    "profit": str(r["profit"]),
                }
                for r in top_today
            ],
            "recent_sales": recent_sales_data,
            "low_stock_items": low_stock_data,

            "onboarding": {
                "has_products": products_count > 0,
                "products_count": products_count,
                "has_sales": total_sales > 0,
                "total_sales": total_sales,
            },
        })