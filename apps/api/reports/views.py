"""
reports.views
=============
Thin REST API views — business logic lives in reports.services.
"""
import datetime
from decimal import Decimal

from django.db.models import Case, DecimalField as DjDecimalField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from billing.permissions import RequireFeature
from core.permissions import HasTenant, IsManager
from catalog.models import Product
from core.models import Warehouse
from inventory.models import StockItem, StockMove
from reports import services


D0 = Decimal("0")


# ══════════════════════════════════════════════════════════════════
# HELPERS (parsing only — no business logic)
# ══════════════════════════════════════════════════════════════════

def _tenant_id(request):
    return getattr(request.user, "tenant_id", None)


def _active_store_id(request):
    return getattr(request.user, "active_store_id", None)


def _require_ctx(request):
    t_id = _tenant_id(request)
    s_id = _active_store_id(request)
    if not t_id:
        raise ValidationError({"detail": "tenant is required on user."})
    if not s_id:
        raise ValidationError({"detail": "active_store is required. Set user.active_store before using reports."})
    return t_id, s_id


def _parse_date_or_none(s: str):
    if not s:
        return None
    d = parse_date(s)
    if not d:
        raise ValidationError({"detail": f"Invalid date '{s}'. Use YYYY-MM-DD."})
    return d


def _to_int(s, default=None):
    if s is None or s == "":
        return default
    try:
        return int(s)
    except ValueError:
        raise ValidationError({"detail": f"Invalid int '{s}'."})


def _to_decimal(s, default="0"):
    if s is None or s == "":
        s = default
    try:
        return Decimal(str(s).replace(",", "."))
    except Exception:
        raise ValidationError({"detail": f"Invalid decimal '{s}'."})


def _user_display(request):
    return getattr(request.user, "username", None) or getattr(request.user, "email", None)


# ══════════════════════════════════════════════════════════════════
# 1. STOCK VALORIZADO
# ══════════════════════════════════════════════════════════════════
class StockValuedReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        data = services.get_stock_valued(
            t_id, s_id,
            warehouse_id=_to_int(request.query_params.get("warehouse_id")),
            q=(request.query_params.get("q") or "").strip() or None,
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 2. PLANILLA SUGERIDO TRANSFERENCIA
# ══════════════════════════════════════════════════════════════════
class TransferSuggestionSheetReportView(APIView):
    permission_classes = [RequireFeature("has_transfers")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params

        mode = (p.get("mode") or "auto").strip().lower()
        if mode not in ("auto", "simple", "rotation"):
            raise ValidationError({"detail": "mode must be one of: auto, simple, rotation"})

        target_qty = _to_decimal(p.get("target_qty", "10"), default="10")
        if target_qty < 0:
            target_qty = D0

        sales_days = max(1, min(365, _to_int(p.get("sales_days"), 30)))
        target_days = max(1, min(365, _to_int(p.get("target_days"), 14)))

        data = services.get_transfer_suggestions(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            category_id=_to_int(p.get("category_id")),
            q=(p.get("q") or "").strip() or None,
            mode=mode,
            target_qty=target_qty,
            sales_days=sales_days,
            target_days=target_days,
            user=_user_display(request),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 3. MERMAS Y PÉRDIDAS
# ══════════════════════════════════════════════════════════════════
class LossesReportView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_losses(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            reason=(p.get("reason") or "").strip().upper() or None,
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 4. VENTAS DEL PERÍODO
# ══════════════════════════════════════════════════════════════════
class SalesSummaryReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_sales_summary(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            category_id=_to_int(p.get("category_id")),
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 5. PRODUCTOS MÁS VENDIDOS (TOP)
# ══════════════════════════════════════════════════════════════════
class TopProductsReportView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_top_products(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            category_id=_to_int(p.get("category_id")),
            sort_by=(p.get("sort") or "revenue").strip(),
            limit=min(100, max(5, _to_int(p.get("limit"), 20))),
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 6. RENTABILIDAD POR PRODUCTO / CATEGORÍA
# ══════════════════════════════════════════════════════════════════
class ProfitabilityReportView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_profitability(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            group_by=(p.get("group_by") or "product").strip(),
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 7. PRODUCTOS SIN ROTACIÓN (DEAD STOCK)
# ══════════════════════════════════════════════════════════════════
class DeadStockReportView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_dead_stock(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            days=min(365, max(7, _to_int(p.get("days"), 30))),
            min_stock=Decimal(str(_to_int(p.get("min_stock"), 0) or 0)),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 8. HOJA DE CONTEO DE INVENTARIO (TOMA FÍSICA)
# ══════════════════════════════════════════════════════════════════
class InventoryCountSheetView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_inventory_count_sheet(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            category_id=_to_int(p.get("category_id")),
            q=(p.get("q") or "").strip() or None,
            show_zero=(p.get("show_zero") or "false").lower() == "true",
            sort_by=(p.get("sort") or "category").strip(),
            user=_user_display(request),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 9. DIFERENCIAS FÍSICO vs SISTEMA
# ══════════════════════════════════════════════════════════════════
class InventoryDiffReportView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        t_id, s_id = _require_ctx(request)
        counts = request.data.get("counts", [])
        if not counts:
            raise ValidationError({"detail": "counts is required (array of {product_id, warehouse_id, physical})"})

        data = services.get_inventory_diff(t_id, s_id, counts)
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 10. AUDITORÍA DE MOVIMIENTOS DE INVENTARIO
# ══════════════════════════════════════════════════════════════════
class AuditTrailReportView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        data = services.get_audit_trail(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            product_id=_to_int(p.get("product_id")),
            ref_type=(p.get("ref_type") or "").strip().upper() or None,
            move_type=(p.get("move_type") or "").strip().upper() or None,
            user_id=_to_int(p.get("user_id")),
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
            page=max(1, _to_int(p.get("page"), 1)),
            page_size=min(200, max(10, _to_int(p.get("page_size"), 50))),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 11. ANÁLISIS ABC DE INVENTARIO (Pareto)
# ══════════════════════════════════════════════════════════════════
class ABCAnalysisReportView(APIView):
    permission_classes = [RequireFeature("has_abc")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        p = request.query_params
        criterion = (p.get("criterion") or "revenue").strip()
        if criterion not in ("revenue", "profit", "qty"):
            criterion = "revenue"

        data = services.get_abc_analysis(
            t_id, s_id,
            warehouse_id=_to_int(p.get("warehouse_id")),
            criterion=criterion,
            date_from=_parse_date_or_none(p.get("date_from")),
            date_to=_parse_date_or_none(p.get("date_to")),
        )
        return Response(data)


# ══════════════════════════════════════════════════════════════════
# 12. SALUD DEL INVENTARIO
# ══════════════════════════════════════════════════════════════════
class InventoryHealthView(APIView):
    permission_classes = [RequireFeature("has_reports")]

    def get(self, request):
        t_id, s_id = _require_ctx(request)
        wh_filter = {"tenant_id": t_id, "store_id": s_id, "is_active": True}
        wh_id = _to_int(request.query_params.get("warehouse_id"))
        if wh_id:
            wh_filter["id"] = wh_id
        wh_ids = list(Warehouse.objects.filter(**wh_filter).values_list("id", flat=True))
        if not wh_ids:
            return Response({"score": 100, "summary": {"total_products": 0, "healthy": 0, "at_risk": 0, "critical": 0},
                             "zero_stock": [], "dead_stock": [], "discrepancies": [], "below_minimum": [], "overstock": []})

        dead_stock_days = max(7, min(365, _to_int(request.query_params.get("dead_stock_days")) or 60))

        now = timezone.now()
        cutoff_30d = now - datetime.timedelta(days=30)
        cutoff_dead = now - datetime.timedelta(days=dead_stock_days)
        cutoff_90d = now - datetime.timedelta(days=90)

        base_si = StockItem.objects.filter(tenant_id=t_id, warehouse_id__in=wh_ids)

        # Count products at DB level first (cheap query)
        total_products = base_si.values("product_id").distinct().count()

        if total_products == 0:
            return Response({"score": 100, "summary": {"total_products": 0, "healthy": 0, "at_risk": 0, "critical": 0},
                             "zero_stock": [], "dead_stock": [], "discrepancies": [], "below_minimum": [], "overstock": []})

        # Cap per-section detail to 50 rows (frontend shows top items, not full list)
        _SECTION_LIMIT = 50

        # Load all items — .values() returns dicts (light), select_related removed (useless with values)
        all_items = list(base_si.values(
            "product_id", "product__name", "product__sku", "product__min_stock",
            "warehouse_id", "warehouse__name", "on_hand", "avg_cost", "stock_value",
        ))
        product_ids_in_scope = {r["product_id"] for r in all_items}

        # Helper: build a key→row lookup
        def _key(r):
            return (r["product_id"], r["warehouse_id"])

        # ── Section 1: Stock negativo o cero con ventas recientes ──
        zero_items = [r for r in all_items if r["on_hand"] <= 0]
        # Products with OUT moves in last 30 days
        recent_out = set(
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                move_type=StockMove.OUT, created_at__gte=cutoff_30d,
                product_id__in=[r["product_id"] for r in zero_items],
            ).values_list("product_id", "warehouse_id").distinct()
        )
        # Last sale date per (product, warehouse)
        last_sale_qs = (
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                move_type=StockMove.OUT,
                product_id__in=[r["product_id"] for r in zero_items],
            ).values("product_id", "warehouse_id")
            .annotate(last_sale=Max("created_at"))
        )
        last_sale_map = {(r["product_id"], r["warehouse_id"]): r["last_sale"] for r in last_sale_qs}

        zero_stock = []
        zero_pids = set()
        for r in zero_items:
            k = _key(r)
            if k in recent_out:
                ls = last_sale_map.get(k)
                zero_stock.append({
                    "product_id": r["product_id"], "product_name": r["product__name"],
                    "sku": r["product__sku"], "warehouse_id": r["warehouse_id"],
                    "warehouse_name": r["warehouse__name"], "on_hand": str(r["on_hand"]),
                    "last_sale_date": ls.date().isoformat() if ls else None,
                })
                zero_pids.add(r["product_id"])

        # ── Section 2: Dead stock (on_hand > 0, no OUT in N days) ──
        positive_items = [r for r in all_items if r["on_hand"] > 0]
        pos_pids = {r["product_id"] for r in positive_items}
        recent_out_dead = set(
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                move_type=StockMove.OUT, created_at__gte=cutoff_dead,
                product_id__in=pos_pids,
            ).values_list("product_id", "warehouse_id").distinct()
        )
        last_out_qs = (
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                move_type=StockMove.OUT,
                product_id__in=pos_pids,
            ).values("product_id", "warehouse_id")
            .annotate(last_out=Max("created_at"))
        )
        last_out_map = {(r["product_id"], r["warehouse_id"]): r["last_out"] for r in last_out_qs}

        dead_stock = []
        dead_pids = set()
        dead_total_value = Decimal("0")
        for r in positive_items:
            k = _key(r)
            if k not in recent_out_dead:
                lo = last_out_map.get(k)
                days_without = (now - lo).days if lo else 9999
                sv = r["stock_value"] or Decimal("0")
                dead_stock.append({
                    "product_id": r["product_id"], "product_name": r["product__name"],
                    "sku": r["product__sku"], "warehouse_id": r["warehouse_id"],
                    "warehouse_name": r["warehouse__name"], "on_hand": str(r["on_hand"]),
                    "days_without_sale": days_without,
                    "stock_value": str(sv),
                })
                dead_total_value += sv
                dead_pids.add(r["product_id"])

        # ── Section 3: Descuadres (discrepancies) ──
        net_moves = (
            StockMove.objects.filter(tenant_id=t_id, warehouse_id__in=wh_ids)
            .values("product_id", "warehouse_id")
            .annotate(
                net=Sum(Case(
                    When(move_type=StockMove.IN, then=F("qty")),
                    When(move_type=StockMove.ADJ, then=F("qty")),
                    When(move_type=StockMove.OUT, then=-F("qty")),
                    default=Value(0),
                    output_field=DjDecimalField(),
                ))
            )
        )
        net_map = {(r["product_id"], r["warehouse_id"]): r["net"] for r in net_moves}

        discrepancies = []
        disc_pids = set()
        for r in all_items:
            k = _key(r)
            expected = net_map.get(k, Decimal("0"))
            diff = r["on_hand"] - expected
            if abs(diff) > Decimal("0.01"):
                discrepancies.append({
                    "product_id": r["product_id"], "product_name": r["product__name"],
                    "sku": r["product__sku"], "warehouse_id": r["warehouse_id"],
                    "warehouse_name": r["warehouse__name"], "on_hand": str(r["on_hand"]),
                    "expected": str(expected), "difference": str(diff),
                })
                disc_pids.add(r["product_id"])

        # ── Section 4: Bajo mínimo ──
        below_minimum = []
        below_pids = set()
        for r in all_items:
            ms = r["product__min_stock"] or 0
            if ms > 0 and r["on_hand"] < ms:
                below_minimum.append({
                    "product_id": r["product_id"], "product_name": r["product__name"],
                    "sku": r["product__sku"], "warehouse_id": r["warehouse_id"],
                    "warehouse_name": r["warehouse__name"], "on_hand": str(r["on_hand"]),
                    "min_stock": str(ms),
                })
                below_pids.add(r["product_id"])

        # ── Section 5: Sobre-stock (>90 days of stock) ──
        out_90 = (
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                move_type=StockMove.OUT, created_at__gte=cutoff_90d,
                product_id__in=pos_pids,
            ).values("product_id", "warehouse_id")
            .annotate(total_out=Sum("qty"))
        )
        avg_daily_map = {(r["product_id"], r["warehouse_id"]): r["total_out"] / Decimal("90") for r in out_90}

        overstock = []
        over_pids = set()
        for r in positive_items:
            k = _key(r)
            avg_daily = avg_daily_map.get(k, Decimal("0"))
            if avg_daily > 0:
                days_of_stock = int(r["on_hand"] / avg_daily)
                if days_of_stock > 90:
                    overstock.append({
                        "product_id": r["product_id"], "product_name": r["product__name"],
                        "sku": r["product__sku"], "warehouse_id": r["warehouse_id"],
                        "warehouse_name": r["warehouse__name"], "on_hand": str(r["on_hand"]),
                        "avg_daily_sales": str(round(avg_daily, 3)),
                        "days_of_stock": days_of_stock,
                    })
                    over_pids.add(r["product_id"])

        # ── Section 6: Summary ──
        issue_counts = {}
        for pid in product_ids_in_scope:
            cnt = sum([
                pid in zero_pids,
                pid in dead_pids,
                pid in disc_pids,
                pid in below_pids,
                pid in over_pids,
            ])
            issue_counts[pid] = cnt

        healthy = sum(1 for c in issue_counts.values() if c == 0)
        at_risk = sum(1 for c in issue_counts.values() if c == 1)
        critical = sum(1 for c in issue_counts.values() if c >= 2)
        score = round(healthy / total_products * 100) if total_products else 100

        return Response({
            "score": score,
            "summary": {
                "total_products": total_products,
                "healthy": healthy,
                "at_risk": at_risk,
                "critical": critical,
            },
            "zero_stock": zero_stock[:_SECTION_LIMIT],
            "zero_stock_total": len(zero_stock),
            "dead_stock": dead_stock[:_SECTION_LIMIT],
            "dead_stock_total": len(dead_stock),
            "dead_stock_days": dead_stock_days,
            "dead_total_value": str(dead_total_value),
            "discrepancies": discrepancies[:_SECTION_LIMIT],
            "discrepancies_total": len(discrepancies),
            "below_minimum": below_minimum[:_SECTION_LIMIT],
            "below_minimum_total": len(below_minimum),
            "overstock": overstock[:_SECTION_LIMIT],
            "overstock_total": len(overstock),
        })
