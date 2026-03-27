"""
forecast.views
==============
Thin REST API views — business logic lives in forecast.services.
"""
from decimal import Decimal

from api.utils import safe_int
from django.db import transaction
from django.utils import timezone

from django.db import models

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from billing.permissions import RequireFeature
from forecast.models import PurchaseSuggestion, SuggestionLine, Holiday
from forecast.serializers import HolidaySerializer
from forecast import services


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tenant_id(request):
    return getattr(request.user, "tenant_id", None)


def _store_id(request):
    return getattr(request.user, "active_store_id", None)


def _require(request):
    t = _tenant_id(request)
    s = _store_id(request)
    if not t:
        return None, None, Response({"detail": "tenant required"}, status=status.HTTP_400_BAD_REQUEST)
    if not s:
        return None, None, Response({"detail": "active_store required"}, status=status.HTTP_400_BAD_REQUEST)
    return t, s, None


# ══════════════════════════════════════════════════════════════════════════════
# FORECAST DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
class ForecastDashboardView(APIView):
    """GET /api/forecast/dashboard/?warehouse_id="""
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request):
        t_id, s_id, err = _require(request)
        if err:
            return err

        wh_id = request.query_params.get("warehouse_id")
        wh_ids = services.get_warehouse_ids(t_id, s_id, wh_id)
        if not wh_ids:
            return Response({"kpis": {}, "warehouse_ids": []})

        kpis = services.get_dashboard_kpis(t_id, wh_ids)
        return Response({"kpis": kpis, "warehouse_ids": wh_ids})


# ══════════════════════════════════════════════════════════════════════════════
# FORECAST PRODUCTS LIST
# ══════════════════════════════════════════════════════════════════════════════
class ForecastProductListView(APIView):
    """GET /api/forecast/products/?warehouse_id=&sort=stockout&page=1&page_size=50"""
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request):
        t_id, s_id, err = _require(request)
        if err:
            return err

        wh_id = request.query_params.get("warehouse_id")
        sort_by = request.query_params.get("sort", "stockout")
        page = max(1, safe_int(request.query_params.get("page"), 1))
        page_size = min(100, max(1, safe_int(request.query_params.get("page_size"), 50)))

        wh_ids = services.get_warehouse_ids(t_id, s_id, wh_id)
        if not wh_ids:
            return Response({"results": [], "count": 0, "page": page})

        data = services.get_product_forecasts(t_id, wh_ids, sort_by, page, page_size)
        return Response(data)


# ══════════════════════════════════════════════════════════════════════════════
# FORECAST PRODUCT DETAIL
# ══════════════════════════════════════════════════════════════════════════════
class ForecastProductDetailView(APIView):
    """GET /api/forecast/products/<product_id>/?warehouse_id="""
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request, product_id):
        t_id, s_id, err = _require(request)
        if err:
            return err

        wh_id = request.query_params.get("warehouse_id")
        history_days = min(90, max(7, safe_int(request.query_params.get("history_days"), 30)))

        wh_ids = services.get_warehouse_ids(t_id, s_id, wh_id)
        data = services.get_product_detail(t_id, product_id, wh_ids, history_days)
        if data is None:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


# ══════════════════════════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════════════════════════
class ForecastAlertsView(APIView):
    """GET /api/forecast/alerts/?warehouse_id="""
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request):
        t_id, s_id, err = _require(request)
        if err:
            return err

        wh_id = request.query_params.get("warehouse_id")
        wh_ids = services.get_warehouse_ids(t_id, s_id, wh_id)
        data = services.get_stockout_alerts(t_id, wh_ids)
        return Response(data)


# ══════════════════════════════════════════════════════════════════════════════
# SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════════════
class SuggestionListView(APIView):
    """GET /api/forecast/suggestions/?status=PENDING&warehouse_id="""
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request):
        t_id, s_id, err = _require(request)
        if err:
            return err

        st = request.query_params.get("status")
        wh = request.query_params.get("warehouse_id")
        data = services.get_suggestions(t_id, st, wh)
        return Response(data)


class SuggestionApproveView(APIView):
    """POST /api/forecast/suggestions/<id>/approve/"""
    permission_classes = [RequireFeature("has_forecast")]

    def post(self, request, pk):
        t_id, s_id, err = _require(request)
        if err:
            return err

        from purchases.models import Purchase, PurchaseLine as PLine

        from inventory.models import StockItem

        with transaction.atomic():
            try:
                suggestion = (
                    PurchaseSuggestion.objects
                    .select_for_update()
                    .get(id=pk, tenant_id=t_id)
                )
            except PurchaseSuggestion.DoesNotExist:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

            if suggestion.status != "PENDING":
                return Response(
                    {"detail": f"Cannot approve: status is {suggestion.status}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            purchase = Purchase.objects.create(
                tenant_id=t_id,
                store_id=s_id,
                warehouse_id=suggestion.warehouse_id,
                supplier_name=suggestion.supplier_name,
                status=Purchase.STATUS_DRAFT,
                note=f"Generada automáticamente desde sugerencia #{suggestion.id}",
                created_by=request.user,
            )

            total_purchase_cost = Decimal("0.000")

            suggestion_lines = list(
                SuggestionLine.objects.filter(suggestion=suggestion).select_related("product")
            )
            # Batch fetch all stock items for these products
            product_ids = [l.product_id for l in suggestion_lines]
            stock_map = {
                si.product_id: si
                for si in StockItem.objects.filter(
                    tenant_id=t_id, warehouse_id=suggestion.warehouse_id,
                    product_id__in=product_ids,
                )
            }

            for line in suggestion_lines:
                si = stock_map.get(line.product_id)
                unit_cost = si.avg_cost if si else Decimal("0")
                line_total = (line.suggested_qty * unit_cost).quantize(Decimal("0.000"))
                total_purchase_cost += line_total

                PLine.objects.create(
                    tenant_id=t_id,
                    purchase=purchase,
                    product_id=line.product_id,
                    qty=line.suggested_qty,
                    unit_cost=unit_cost,
                    line_total_cost=line_total,
                )

            purchase.subtotal_cost = total_purchase_cost
            purchase.total_cost = total_purchase_cost
            purchase.save(update_fields=["subtotal_cost", "total_cost"])

            suggestion.status = "APPROVED"
            suggestion.approved_at = timezone.now()
            suggestion.approved_by = request.user
            suggestion.purchase = purchase
            suggestion.save()

        return Response({
            "detail": "Suggestion approved",
            "purchase_id": purchase.id,
            "suggestion_id": suggestion.id,
        })


class SuggestionDismissView(APIView):
    """POST /api/forecast/suggestions/<id>/dismiss/"""
    permission_classes = [RequireFeature("has_forecast")]

    def post(self, request, pk):
        t_id, s_id, err = _require(request)
        if err:
            return err

        try:
            suggestion = PurchaseSuggestion.objects.get(id=pk, tenant_id=t_id)
        except PurchaseSuggestion.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if suggestion.status != "PENDING":
            return Response(
                {"detail": f"Cannot dismiss: status is {suggestion.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.status = "DISMISSED"
        suggestion.save()
        return Response({"detail": "Suggestion dismissed"})


# ══════════════════════════════════════════════════════════════════════════════
# HOLIDAY CRUD
# ══════════════════════════════════════════════════════════════════════════════
class HolidayListCreateView(APIView):
    """
    GET  /api/forecast/holidays/?year=2026
    POST /api/forecast/holidays/
    """
    permission_classes = [RequireFeature("has_forecast")]

    def get(self, request):
        t_id = _tenant_id(request)
        year = request.query_params.get("year")

        # Show national (tenant=None) + tenant-specific
        qs = Holiday.objects.filter(
            models.Q(tenant_id=t_id) | models.Q(tenant__isnull=True)
        ).order_by("date")

        if year:
            try:
                qs = qs.filter(date__year=int(year))
            except (ValueError, TypeError):
                return Response({"detail": "year must be a valid integer"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = HolidaySerializer(qs, many=True)
        return Response({"results": serializer.data, "count": len(serializer.data)})

    def post(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "tenant required"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = HolidaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant_id=t_id, scope=Holiday.SCOPE_CUSTOM)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class HolidayDetailView(APIView):
    """
    PATCH  /api/forecast/holidays/<id>/
    DELETE /api/forecast/holidays/<id>/
    """
    permission_classes = [RequireFeature("has_forecast")]

    def _get_holiday(self, pk, tenant_id):
        try:
            return Holiday.objects.get(id=pk, tenant_id=tenant_id, scope=Holiday.SCOPE_CUSTOM)
        except Holiday.DoesNotExist:
            return None

    def patch(self, request, pk):
        t_id = _tenant_id(request)
        holiday = self._get_holiday(pk, t_id)
        if not holiday:
            return Response({"detail": "Not found or not editable"}, status=status.HTTP_404_NOT_FOUND)

        serializer = HolidaySerializer(holiday, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        t_id = _tenant_id(request)
        holiday = self._get_holiday(pk, t_id)
        if not holiday:
            return Response({"detail": "Not found or not editable"}, status=status.HTTP_404_NOT_FOUND)

        holiday.delete()
        return Response({"detail": "Holiday deleted"}, status=status.HTTP_204_NO_CONTENT)
