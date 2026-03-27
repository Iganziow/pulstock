"""
reports.services
================
Business logic for all report endpoints.
Views call these functions; they receive plain IDs and params, return dicts.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.db.models import (
    Q, Sum, Count, Avg, Max,
    Case, When, Value, DecimalField, F,
    OuterRef, Subquery,
)
from django.db.models.functions import Coalesce, TruncDate, Abs
from django.utils import timezone

from catalog.models import Category, Barcode, Product
from inventory.models import StockMove, StockItem
from sales.models import Sale, SaleLine
from stores.models import Store

D0 = Decimal("0")


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _margin_pct(profit, revenue):
    """Calculate margin percentage, return Decimal."""
    if revenue and revenue > 0:
        return (profit / revenue * 100).quantize(Decimal("0.1"))
    return D0


def _ceil_to_int_str(d):
    try:
        d = Decimal(d)
    except Exception:
        return "0"
    if d <= 0:
        return "0"
    return str(d.quantize(Decimal("1"), rounding=ROUND_CEILING))


def _first_barcode_subquery(tenant_id):
    return Subquery(
        Barcode.objects.filter(tenant_id=tenant_id, product_id=OuterRef("product_id"))
        .order_by("id").values("code")[:1]
    )


# ══════════════════════════════════════════════════════════════════
# 1. STOCK VALORIZADO
# ══════════════════════════════════════════════════════════════════

def get_stock_valued(t_id, s_id, warehouse_id=None, q=None):
    qs = (
        StockItem.objects.filter(tenant_id=t_id, warehouse__store_id=s_id, product__is_active=True)
        .select_related("product", "warehouse")
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(product__sku__icontains=q))

    totals = qs.aggregate(
        total_qty=Coalesce(Sum("on_hand"), D0),
        total_value=Coalesce(Sum("stock_value"), D0),
    )

    LIMIT = 5000
    total_count = qs.count()
    results = []
    for si in qs.order_by("product__name")[:LIMIT]:
        results.append({
            "warehouse_id": si.warehouse_id,
            "warehouse_name": si.warehouse.name if si.warehouse_id else None,
            "product_id": si.product_id,
            "sku": getattr(si.product, "sku", None),
            "name": si.product.name if getattr(si, "product", None) else None,
            "on_hand": str(si.on_hand),
            "avg_cost": str(si.avg_cost),
            "stock_value": str(si.stock_value),
        })

    return {
        "meta": {
            "tenant_id": t_id, "active_store_id": s_id,
            "warehouse_id": warehouse_id, "q": q or None,
            "total_count": total_count, "limit": LIMIT,
            "truncated": total_count > LIMIT,
        },
        "totals": {"total_qty": str(totals["total_qty"]), "total_value": str(totals["total_value"])},
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 2. PLANILLA SUGERIDO TRANSFERENCIA
# ══════════════════════════════════════════════════════════════════

def get_transfer_suggestions(t_id, s_id, warehouse_id=None, category_id=None,
                             q=None, mode="auto", target_qty=Decimal("10"),
                             sales_days=30, target_days=14, user=None):
    store = Store.objects.filter(id=s_id, tenant_id=t_id, is_active=True).first()
    store_code = None
    store_name = None
    store_address = None
    if store:
        store_code = getattr(store, "code", None) or str(getattr(store, "id", ""))
        store_name = getattr(store, "name", None)
        store_address = getattr(store, "address", None) or ""

    category_name = None
    if category_id:
        cat = Category.objects.filter(id=category_id, tenant_id=t_id).only("name").first()
        category_name = cat.name if cat else None

    header = {
        "store_code": store_code,
        "store_name": store_name,
        "store_address": store_address,
        "category_name": category_name,
        "generated_at": timezone.localtime(timezone.now()).isoformat(),
        "user_name": user,
    }

    qs = (
        StockItem.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id, product__is_active=True,
        )
        .select_related("product", "warehouse", "product__category")
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    qs = qs.annotate(first_barcode=_first_barcode_subquery(t_id))

    if q:
        qs = qs.filter(
            Q(product__name__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(first_barcode__icontains=q)
        )

    since = timezone.now() - timedelta(days=sales_days)

    base_items = list(
        qs.only(
            "warehouse_id", "product_id", "on_hand",
            "product__name", "product__sku", "product__category__name",
        )[:10000]
    )

    wh_ids = sorted({int(si.warehouse_id) for si in base_items if si.warehouse_id})
    prod_ids = sorted({int(si.product_id) for si in base_items if si.product_id})

    sales_map = {}
    if wh_ids and prod_ids:
        sales_qs = (
            StockMove.objects.filter(
                tenant_id=t_id, warehouse_id__in=wh_ids,
                product_id__in=prod_ids, created_at__gte=since,
            )
            .values("warehouse_id", "product_id")
            .annotate(
                sold_net=Coalesce(
                    Sum(
                        Case(
                            When(move_type=StockMove.OUT, ref_type="SALE", then=F("qty")),
                            When(move_type=StockMove.IN, ref_type="SALE_VOID", then=F("qty") * Value(Decimal("-1"))),
                            default=Value(D0),
                            output_field=DecimalField(max_digits=18, decimal_places=6),
                        )
                    ),
                    D0,
                )
            )
        )
        for r in sales_qs:
            key = (int(r["warehouse_id"]), int(r["product_id"]))
            sales_map[key] = Decimal(str(r["sold_net"] or "0"))

    results = []
    # FIX: track both modes seen when mode="auto"
    modes_seen = set()

    for si in base_items:
        p = si.product
        on_hand = si.on_hand or D0
        stock_in_transit = D0
        stock_theoretical = on_hand + stock_in_transit
        stock_physical = on_hand

        sold_net = sales_map.get((int(si.warehouse_id), int(si.product_id)), D0)
        if sold_net < 0:
            sold_net = D0

        avg_sales_day = (sold_net / Decimal(str(sales_days))).quantize(Decimal("0.000"))
        objective_qty = (avg_sales_day * Decimal(str(target_days))).quantize(Decimal("0.000"))

        effective_mode = mode
        if mode == "auto":
            effective_mode = "rotation" if avg_sales_day > 0 else "simple"
            modes_seen.add(effective_mode)

        if effective_mode == "rotation":
            suggested = objective_qty - stock_theoretical
        else:
            suggested = target_qty - stock_theoretical

        if suggested < 0:
            suggested = D0

        internal_code = (
            getattr(p, "internal_code", None)
            or getattr(p, "code", None)
            or (getattr(p, "sku", None) or "").strip()
            or str(si.product_id)
        )
        barcode = getattr(si, "first_barcode", None)

        results.append({
            "product_id": si.product_id,
            "internal_code": str(internal_code),
            "barcode": barcode,
            "sku": getattr(p, "sku", None),
            "product_name": getattr(p, "name", "") or "",
            "stock_theoretical": str(stock_theoretical),
            "stock_in_transit": str(stock_in_transit),
            "stock_physical": str(stock_physical),
            "avg_sales_day": str(avg_sales_day),
            "objective_qty": str(objective_qty),
            "suggested": str(suggested),
            "suggested_ceil": _ceil_to_int_str(suggested),
            "qty_to_order": _ceil_to_int_str(suggested),
        })

    # FIX: used_mode reflects reality when auto
    if mode == "auto":
        if len(modes_seen) == 2:
            used_mode = "mixed"
        elif len(modes_seen) == 1:
            used_mode = modes_seen.pop()
        else:
            used_mode = "auto"
    else:
        used_mode = mode

    return {
        "header": header,
        "meta": {
            "tenant_id": t_id, "active_store_id": s_id,
            "warehouse_id": warehouse_id, "category_id": category_id,
            "q": q or None, "mode": mode, "used_mode": used_mode,
            "target_qty": str(target_qty), "target_days": target_days,
            "sales_days": sales_days, "count": len(results),
            "since": timezone.localtime(since).isoformat(),
        },
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 3. MERMAS Y PÉRDIDAS
# ══════════════════════════════════════════════════════════════════

def get_losses(t_id, s_id, warehouse_id=None, reason=None, date_from=None, date_to=None):
    qs = (
        StockMove.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id,
            move_type="OUT", ref_type="ISSUE",
        )
        .select_related("product", "product__category", "warehouse")
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if reason:
        qs = qs.filter(reason=reason)

    reason_summary = (
        qs.values("reason")
        .annotate(
            total_qty=Sum("qty"),
            total_cost=Coalesce(Sum(Abs("value_delta")), D0, output_field=DecimalField(max_digits=14, decimal_places=3)),
            moves_count=Count("id"),
        )
        .order_by("-total_cost")
    )

    detail_qs = qs.order_by("-created_at")[:100]
    details = []
    for m in detail_qs:
        details.append({
            "id": m.id,
            "created_at": m.created_at.isoformat(),
            "product_id": m.product_id,
            "product_name": m.product.name if m.product else None,
            "category": m.product.category.name if m.product and m.product.category else None,
            "warehouse_id": m.warehouse_id,
            "warehouse_name": m.warehouse.name if m.warehouse else None,
            "reason": m.reason,
            "qty": str(m.qty),
            "cost_snapshot": str(m.cost_snapshot or 0),
            "value_lost": str(abs(m.value_delta or 0)),
            "note": m.note or "",
        })

    totals = qs.aggregate(
        total_qty=Coalesce(Sum("qty"), D0, output_field=DecimalField(max_digits=14, decimal_places=3)),
        total_cost=Coalesce(Sum(Abs("value_delta")), D0, output_field=DecimalField(max_digits=14, decimal_places=3)),
        total_moves=Count("id"),
    )

    return {
        "meta": {
            "tenant_id": t_id, "active_store_id": s_id,
            "warehouse_id": warehouse_id, "reason": reason or None,
            "date_from": str(date_from) if date_from else None,
            "date_to": str(date_to) if date_to else None,
        },
        "totals": {
            "qty": str(totals["total_qty"]),
            "cost": str(totals["total_cost"]),
            "moves": totals["total_moves"],
        },
        "by_reason": [
            {"reason": r["reason"] or "SIN_MOTIVO", "qty": str(r["total_qty"]), "cost": str(r["total_cost"]), "moves": r["moves_count"]}
            for r in reason_summary
        ],
        "details": details,
    }


# ══════════════════════════════════════════════════════════════════
# 4. VENTAS DEL PERÍODO
# ══════════════════════════════════════════════════════════════════

def get_sales_summary(t_id, s_id, warehouse_id=None, category_id=None,
                      date_from=None, date_to=None):
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    if not date_to:
        date_to = timezone.now().date()

    sales_qs = Sale.objects.filter(
        tenant_id=t_id, store_id=s_id, status=Sale.STATUS_COMPLETED,
        sale_type=Sale.SALE_TYPE_VENTA,
        created_at__date__gte=date_from, created_at__date__lte=date_to,
    )
    if warehouse_id:
        sales_qs = sales_qs.filter(warehouse_id=warehouse_id)

    lines_qs = SaleLine.objects.filter(
        tenant_id=t_id, sale__store_id=s_id, sale__status=Sale.STATUS_COMPLETED,
        sale__sale_type=Sale.SALE_TYPE_VENTA,
        sale__created_at__date__gte=date_from, sale__created_at__date__lte=date_to,
    )
    if warehouse_id:
        lines_qs = lines_qs.filter(sale__warehouse_id=warehouse_id)
    if category_id:
        lines_qs = lines_qs.filter(product__category_id=category_id)

    # FIX: When category_id is set, compute KPIs from lines_qs (not sales_qs)
    # so totals are consistent with the category filter.
    if category_id:
        agg = lines_qs.aggregate(
            total_revenue=Coalesce(Sum("line_total"), D0),
            total_cost=Coalesce(Sum("line_cost"), D0),
            gross_profit=Coalesce(Sum("line_gross_profit"), D0),
            sale_count=Count("sale_id", distinct=True),
        )
        items_sold = agg.pop("sale_count")  # reuse for count
        items_sold_qty = lines_qs.aggregate(total_qty=Coalesce(Sum("qty"), D0))["total_qty"]
        sale_count = Count("sale_id", distinct=True)
        # Re-derive correctly
        sale_count = lines_qs.values("sale_id").distinct().count()
        agg["sale_count"] = sale_count
        items_sold = items_sold_qty
    else:
        agg = sales_qs.aggregate(
            total_revenue=Coalesce(Sum("total"), D0),
            total_cost=Coalesce(Sum("total_cost"), D0),
            gross_profit=Coalesce(Sum("gross_profit"), D0),
            sale_count=Count("id"),
        )
        items_sold = lines_qs.aggregate(total_qty=Coalesce(Sum("qty"), D0))["total_qty"]

    total_rev = agg["total_revenue"]
    gross = agg["gross_profit"]
    sale_count = agg["sale_count"]
    avg_ticket = (total_rev / sale_count) if sale_count > 0 else D0
    margin_pct = _margin_pct(gross, total_rev)

    daily = list(
        sales_qs.annotate(day=TruncDate("created_at")).values("day")
        .annotate(revenue=Coalesce(Sum("total"), D0), cost=Coalesce(Sum("total_cost"), D0), count=Count("id"))
        .order_by("day")
    )

    by_cat = list(
        lines_qs.values("product__category__name")
        .annotate(
            revenue=Coalesce(Sum("line_total"), D0), cost=Coalesce(Sum("line_cost"), D0),
            qty=Coalesce(Sum("qty"), D0), profit=Coalesce(Sum("line_gross_profit"), D0),
        )
        .order_by("-revenue")[:20]
    )

    return {
        "meta": {"date_from": str(date_from), "date_to": str(date_to), "warehouse_id": warehouse_id, "category_id": category_id},
        "kpis": {
            "total_revenue": str(total_rev), "total_cost": str(agg["total_cost"]),
            "gross_profit": str(gross),
            "margin_pct": str(margin_pct),
            "sale_count": sale_count, "items_sold": str(items_sold),
            "avg_ticket": str(avg_ticket.quantize(Decimal("0.01")) if isinstance(avg_ticket, Decimal) else 0),
        },
        "daily": [{"date": str(d["day"]), "revenue": str(d["revenue"]), "cost": str(d["cost"]), "count": d["count"]} for d in daily],
        "by_category": [
            {"category": d["product__category__name"] or "Sin categoría", "revenue": str(d["revenue"]), "cost": str(d["cost"]), "qty": str(d["qty"]), "profit": str(d["profit"])}
            for d in by_cat
        ],
    }


# ══════════════════════════════════════════════════════════════════
# 5. PRODUCTOS MÁS VENDIDOS (TOP)
# ══════════════════════════════════════════════════════════════════

def get_top_products(t_id, s_id, warehouse_id=None, category_id=None,
                     sort_by="revenue", limit=20, date_from=None, date_to=None):
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    if not date_to:
        date_to = timezone.now().date()

    qs = SaleLine.objects.filter(
        tenant_id=t_id, sale__store_id=s_id, sale__status=Sale.STATUS_COMPLETED,
        sale__sale_type=Sale.SALE_TYPE_VENTA,
        sale__created_at__date__gte=date_from, sale__created_at__date__lte=date_to,
    )
    if warehouse_id:
        qs = qs.filter(sale__warehouse_id=warehouse_id)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    agg = (
        qs.values("product_id", "product__name", "product__sku", "product__category__name")
        .annotate(
            revenue=Coalesce(Sum("line_total"), D0), cost=Coalesce(Sum("line_cost"), D0),
            profit=Coalesce(Sum("line_gross_profit"), D0), qty=Coalesce(Sum("qty"), D0),
            sale_count=Count("sale_id", distinct=True),
        )
    )

    sort_map = {"revenue": "-revenue", "qty": "-qty", "profit": "-profit"}
    agg = agg.order_by(sort_map.get(sort_by, "-revenue"))[:limit]

    results = []
    for r in agg:
        rev = r["revenue"]
        results.append({
            "product_id": r["product_id"], "product_name": r["product__name"],
            "sku": r["product__sku"], "category": r["product__category__name"] or "Sin categoría",
            "revenue": str(rev), "cost": str(r["cost"]), "profit": str(r["profit"]),
            "margin_pct": str(_margin_pct(r["profit"], rev)),
            "qty": str(r["qty"]), "sale_count": r["sale_count"],
        })

    return {
        "meta": {"date_from": str(date_from), "date_to": str(date_to), "warehouse_id": warehouse_id, "category_id": category_id, "sort": sort_by, "limit": limit},
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 6. RENTABILIDAD POR PRODUCTO / CATEGORÍA
# ══════════════════════════════════════════════════════════════════

def get_profitability(t_id, s_id, warehouse_id=None, group_by="product",
                      date_from=None, date_to=None):
    if not date_from:
        date_from = (timezone.now() - timedelta(days=30)).date()
    if not date_to:
        date_to = timezone.now().date()

    qs = SaleLine.objects.filter(
        tenant_id=t_id, sale__store_id=s_id, sale__status=Sale.STATUS_COMPLETED,
        sale__sale_type=Sale.SALE_TYPE_VENTA,
        sale__created_at__date__gte=date_from, sale__created_at__date__lte=date_to,
    )
    if warehouse_id:
        qs = qs.filter(sale__warehouse_id=warehouse_id)

    if group_by == "category":
        agg = (
            qs.values("product__category__name")
            .annotate(
                revenue=Coalesce(Sum("line_total"), D0), cost=Coalesce(Sum("line_cost"), D0),
                profit=Coalesce(Sum("line_gross_profit"), D0), qty=Coalesce(Sum("qty"), D0),
                product_count=Count("product_id", distinct=True),
            )
            .order_by("-profit")[:50]
        )
        results = []
        for r in agg:
            results.append({
                "category": r["product__category__name"] or "Sin categoría",
                "revenue": str(r["revenue"]), "cost": str(r["cost"]), "profit": str(r["profit"]),
                "margin_pct": str(_margin_pct(r["profit"], r["revenue"])),
                "qty": str(r["qty"]), "product_count": r["product_count"],
            })
    else:
        agg = (
            qs.values("product_id", "product__name", "product__sku", "product__category__name")
            .annotate(
                revenue=Coalesce(Sum("line_total"), D0), cost=Coalesce(Sum("line_cost"), D0),
                profit=Coalesce(Sum("line_gross_profit"), D0), qty=Coalesce(Sum("qty"), D0),
            )
            .order_by("-profit")[:100]
        )
        results = []
        for r in agg:
            results.append({
                "product_id": r["product_id"], "product_name": r["product__name"],
                "sku": r["product__sku"], "category": r["product__category__name"] or "Sin categoría",
                "revenue": str(r["revenue"]), "cost": str(r["cost"]), "profit": str(r["profit"]),
                "margin_pct": str(_margin_pct(r["profit"], r["revenue"])),
                "qty": str(r["qty"]),
            })

    totals = qs.aggregate(
        total_revenue=Coalesce(Sum("line_total"), D0),
        total_cost=Coalesce(Sum("line_cost"), D0),
        total_profit=Coalesce(Sum("line_gross_profit"), D0),
    )

    return {
        "meta": {"date_from": str(date_from), "date_to": str(date_to), "warehouse_id": warehouse_id, "group_by": group_by},
        "totals": {
            "revenue": str(totals["total_revenue"]), "cost": str(totals["total_cost"]),
            "profit": str(totals["total_profit"]),
            "margin_pct": str(_margin_pct(totals["total_profit"], totals["total_revenue"])),
        },
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 7. PRODUCTOS SIN ROTACIÓN (DEAD STOCK)
# ══════════════════════════════════════════════════════════════════

def get_dead_stock(t_id, s_id, warehouse_id=None, days=30, min_stock=D0):
    since = (timezone.now() - timedelta(days=days)).date()

    stock_qs = StockItem.objects.filter(
        tenant_id=t_id, warehouse__store_id=s_id,
        product__is_active=True, on_hand__gt=min_stock,
    ).select_related("product", "product__category", "warehouse")

    if warehouse_id:
        stock_qs = stock_qs.filter(warehouse_id=warehouse_id)

    sold_product_ids = set(
        SaleLine.objects.filter(
            tenant_id=t_id, sale__store_id=s_id,
            sale__status=Sale.STATUS_COMPLETED,
            sale__sale_type=Sale.SALE_TYPE_VENTA,
            sale__created_at__date__gte=since,
        )
        .values_list("product_id", flat=True).distinct()
    )

    last_sale_map = dict(
        SaleLine.objects.filter(
            tenant_id=t_id, sale__store_id=s_id, sale__status=Sale.STATUS_COMPLETED,
            sale__sale_type=Sale.SALE_TYPE_VENTA,
        )
        .values("product_id")
        .annotate(last_sale=Max("sale__created_at"))
        .values_list("product_id", "last_sale")
    )

    results = []
    total_value = D0
    for si in stock_qs.order_by("-stock_value")[:500]:
        pid = si.product_id
        if pid in sold_product_ids:
            continue

        stock_val = si.stock_value or D0
        total_value += stock_val
        last = last_sale_map.get(pid)
        days_since = (timezone.now() - last).days if last else None

        results.append({
            "product_id": pid, "product_name": si.product.name,
            "sku": si.product.sku or "", "category": si.product.category.name if si.product.category else "Sin categoría",
            "warehouse_id": si.warehouse_id, "warehouse_name": si.warehouse.name if si.warehouse else None,
            "on_hand": str(si.on_hand), "avg_cost": str(si.avg_cost), "stock_value": str(stock_val),
            "last_sale_date": last.isoformat() if last else None,
            "days_since_last_sale": days_since,
        })

    return {
        "meta": {"warehouse_id": warehouse_id, "days": days, "min_stock": str(min_stock), "since": str(since)},
        "totals": {"product_count": len(results), "total_value": str(total_value)},
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 8. HOJA DE CONTEO DE INVENTARIO (TOMA FÍSICA)
# ══════════════════════════════════════════════════════════════════

def get_inventory_count_sheet(t_id, s_id, warehouse_id=None, category_id=None,
                              q=None, show_zero=False, sort_by="category", user=None):
    from core.models import Warehouse as WH

    wh_filter = Q(store_id=s_id, tenant_id=t_id, is_active=True)
    if warehouse_id:
        wh_filter &= Q(id=warehouse_id)
    warehouses = list(WH.objects.filter(wh_filter).values("id", "name"))
    wh_ids = [w["id"] for w in warehouses]
    wh_names = {w["id"]: w["name"] for w in warehouses}

    if not wh_ids:
        return {"header": {}, "meta": {}, "categories": [], "results": [], "totals": {}}

    qs = (
        StockItem.objects.filter(
            tenant_id=t_id, warehouse_id__in=wh_ids, product__is_active=True,
        )
        .select_related("product", "product__category", "warehouse")
    )

    if not show_zero:
        qs = qs.filter(on_hand__gt=0)
    if category_id:
        qs = qs.filter(product__category_id=category_id)

    qs = qs.annotate(first_barcode=_first_barcode_subquery(t_id))

    if q:
        qs = qs.filter(
            Q(product__name__icontains=q)
            | Q(product__sku__icontains=q)
            | Q(first_barcode__icontains=q)
        )

    if sort_by == "sku":
        qs = qs.order_by("product__sku", "product__name")
    elif sort_by == "name":
        qs = qs.order_by("product__name")
    else:
        qs = qs.order_by("product__category__name", "product__name")

    LIMIT = 5000
    total_count = qs.count()
    results = []
    categories_set = set()
    total_items = 0
    total_value = D0

    for si in qs[:LIMIT]:
        p = si.product
        cat_name = p.category.name if p.category else "Sin categoría"
        categories_set.add(cat_name)
        on_hand = si.on_hand or D0
        total_items += 1
        total_value += si.stock_value or D0

        results.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku or "",
            "barcode": getattr(si, "first_barcode", None) or "",
            "category": cat_name,
            "warehouse_id": si.warehouse_id,
            "warehouse_name": wh_names.get(si.warehouse_id, ""),
            "unit": p.unit or "UN",
            "stock_system": str(on_hand),
            "avg_cost": str(si.avg_cost or D0),
            "stock_value": str(si.stock_value or D0),
            "stock_physical": "",
            "difference": "",
            "note": "",
        })

    all_categories = sorted(
        Category.objects.filter(tenant_id=t_id, is_active=True)
        .values_list("id", "name").order_by("name"),
        key=lambda x: x[1],
    )

    store = Store.objects.filter(id=s_id, tenant_id=t_id).first()

    header = {
        "store_name": store.name if store else None,
        "store_address": getattr(store, "address", None) or "",
        "warehouses": [{"id": w["id"], "name": w["name"]} for w in warehouses],
        "generated_at": timezone.localtime(timezone.now()).isoformat(),
        "generated_by": user,
    }

    return {
        "header": header,
        "meta": {
            "tenant_id": t_id, "active_store_id": s_id,
            "warehouse_id": warehouse_id, "category_id": category_id,
            "q": q or None, "show_zero": show_zero, "sort": sort_by,
            "count": total_items, "total_count": total_count,
            "limit": LIMIT, "truncated": total_count > LIMIT,
        },
        "categories": [{"id": c[0], "name": c[1]} for c in all_categories],
        "totals": {
            "product_count": total_items,
            "total_value": str(total_value),
            "category_count": len(categories_set),
        },
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 9. DIFERENCIAS FÍSICO vs SISTEMA
# ══════════════════════════════════════════════════════════════════

def get_inventory_diff(t_id, s_id, counts):
    product_ids = list({c["product_id"] for c in counts if "product_id" in c})
    if not product_ids:
        return {"results": [], "totals": {}}

    # FIX: validate warehouse belongs to active store
    si_qs = StockItem.objects.filter(
        tenant_id=t_id, product_id__in=product_ids,
        warehouse__store_id=s_id,
    ).select_related("product", "product__category", "warehouse")

    stock_map = {(si.product_id, si.warehouse_id): si for si in si_qs}

    results = []
    total_surplus_qty = D0
    total_surplus_value = D0
    total_shortage_qty = D0
    total_shortage_value = D0
    match_count = 0

    for c in counts:
        pid = c.get("product_id")
        wid = c.get("warehouse_id")
        physical = Decimal(str(c.get("physical", 0)))

        si = stock_map.get((pid, wid))
        if not si:
            continue

        system_qty = si.on_hand or D0
        diff_qty = physical - system_qty
        unit_cost = si.avg_cost or D0
        diff_value = diff_qty * unit_cost

        status = "match"
        if diff_qty > 0:
            status = "surplus"
            total_surplus_qty += diff_qty
            total_surplus_value += diff_value
        elif diff_qty < 0:
            status = "shortage"
            total_shortage_qty += abs(diff_qty)
            total_shortage_value += abs(diff_value)
        else:
            match_count += 1

        results.append({
            "product_id": pid,
            "product_name": si.product.name,
            "sku": si.product.sku or "",
            "category": si.product.category.name if si.product.category else "Sin categoría",
            "warehouse_id": wid,
            "warehouse_name": si.warehouse.name if si.warehouse else "",
            "unit": si.product.unit or "UN",
            "stock_system": str(system_qty),
            "stock_physical": str(physical),
            "difference_qty": str(diff_qty),
            "unit_cost": str(unit_cost),
            "difference_value": str(diff_value),
            "status": status,
        })

    status_order = {"shortage": 0, "surplus": 1, "match": 2}
    results.sort(key=lambda r: (status_order.get(r["status"], 3), float(r["difference_value"])))

    return {
        "meta": {
            "tenant_id": t_id,
            "products_counted": len(results),
            "generated_at": timezone.localtime(timezone.now()).isoformat(),
        },
        "totals": {
            "counted": len(results),
            "matches": match_count,
            "shortages": len([r for r in results if r["status"] == "shortage"]),
            "surpluses": len([r for r in results if r["status"] == "surplus"]),
            "shortage_qty": str(total_shortage_qty),
            "shortage_value": str(total_shortage_value),
            "surplus_qty": str(total_surplus_qty),
            "surplus_value": str(total_surplus_value),
            "net_value": str(total_surplus_value - total_shortage_value),
        },
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 10. AUDITORÍA DE MOVIMIENTOS DE INVENTARIO
# ══════════════════════════════════════════════════════════════════

def get_audit_trail(t_id, s_id, warehouse_id=None, product_id=None,
                    ref_type=None, move_type=None, user_id=None,
                    date_from=None, date_to=None, page=1, page_size=50):
    if not date_from:
        date_from = (timezone.now() - timedelta(days=7)).date()
    if not date_to:
        date_to = timezone.now().date()

    qs = (
        StockMove.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id,
            created_at__date__gte=date_from, created_at__date__lte=date_to,
        )
        .select_related("product", "product__category", "warehouse", "created_by")
        .order_by("-created_at", "-id")
    )

    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    if product_id:
        qs = qs.filter(product_id=product_id)
    if ref_type:
        qs = qs.filter(ref_type=ref_type)
    if move_type:
        qs = qs.filter(move_type=move_type)
    if user_id:
        qs = qs.filter(created_by_id=user_id)

    total = qs.count()

    summary = qs.aggregate(
        total_in_qty=Coalesce(
            Sum(Case(When(move_type="IN", then="qty"), default=Value(D0), output_field=DecimalField(max_digits=14, decimal_places=3))), D0),
        total_out_qty=Coalesce(
            Sum(Case(When(move_type="OUT", then="qty"), default=Value(D0), output_field=DecimalField(max_digits=14, decimal_places=3))), D0),
        total_value_in=Coalesce(
            Sum(Case(When(move_type="IN", then="value_delta"), default=Value(D0), output_field=DecimalField(max_digits=14, decimal_places=3))), D0),
        total_value_out=Coalesce(
            Sum(Case(When(move_type="OUT", then=Abs("value_delta")), default=Value(D0), output_field=DecimalField(max_digits=14, decimal_places=3))), D0),
        move_count=Count("id"),
    )

    by_type = list(
        qs.values("ref_type").annotate(count=Count("id"), qty_sum=Coalesce(Sum("qty"), D0)).order_by("-count")
    )
    by_user = list(
        qs.values("created_by__username").annotate(count=Count("id")).order_by("-count")[:10]
    )

    start = (page - 1) * page_size
    moves = qs[start:start + page_size]

    results = []
    for m in moves:
        user_name = None
        if m.created_by:
            user_name = getattr(m.created_by, "username", None) or getattr(m.created_by, "email", None)
        results.append({
            "id": m.id,
            "created_at": m.created_at.isoformat(),
            "product_id": m.product_id,
            "product_name": m.product.name if m.product else None,
            "category": m.product.category.name if m.product and m.product.category else None,
            "warehouse_id": m.warehouse_id,
            "warehouse_name": m.warehouse.name if m.warehouse else None,
            "move_type": m.move_type,
            "ref_type": m.ref_type or "",
            "ref_id": m.ref_id,
            "qty": str(m.qty),
            "cost_snapshot": str(m.cost_snapshot or D0),
            "value_delta": str(m.value_delta or D0),
            "reason": m.reason or "",
            "note": m.note or "",
            "user": user_name,
        })

    ref_types = sorted(
        StockMove.objects.filter(tenant_id=t_id, warehouse__store_id=s_id)
        .values_list("ref_type", flat=True).distinct()
    )

    return {
        "meta": {
            "date_from": str(date_from), "date_to": str(date_to),
            "warehouse_id": warehouse_id, "product_id": product_id,
            "ref_type": ref_type or None, "move_type": move_type or None,
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
        "summary": {
            "move_count": summary["move_count"],
            "total_in_qty": str(summary["total_in_qty"]),
            "total_out_qty": str(summary["total_out_qty"]),
            "total_value_in": str(summary["total_value_in"]),
            "total_value_out": str(summary["total_value_out"]),
            "net_value": str(summary["total_value_in"] - summary["total_value_out"]),
        },
        "by_type": [{"ref_type": r["ref_type"] or "SIN_TIPO", "count": r["count"], "qty": str(r["qty_sum"])} for r in by_type],
        "by_user": [{"user": r["created_by__username"] or "Sistema", "count": r["count"]} for r in by_user],
        "ref_types": [r for r in ref_types if r],
        "results": results,
    }


# ══════════════════════════════════════════════════════════════════
# 11. ANÁLISIS ABC DE INVENTARIO (Pareto)
# ══════════════════════════════════════════════════════════════════

def get_abc_analysis(t_id, s_id, warehouse_id=None, criterion="revenue",
                     date_from=None, date_to=None):
    if not date_from:
        date_from = (timezone.now() - timedelta(days=90)).date()
    if not date_to:
        date_to = timezone.now().date()

    qs = SaleLine.objects.filter(
        tenant_id=t_id, sale__store_id=s_id,
        sale__status=Sale.STATUS_COMPLETED,
        sale__sale_type=Sale.SALE_TYPE_VENTA,
        sale__created_at__date__gte=date_from,
        sale__created_at__date__lte=date_to,
    )
    if warehouse_id:
        qs = qs.filter(sale__warehouse_id=warehouse_id)

    agg = list(
        qs.values("product_id", "product__name", "product__sku", "product__category__name")
        .annotate(
            revenue=Coalesce(Sum("line_total"), D0),
            cost=Coalesce(Sum("line_cost"), D0),
            profit=Coalesce(Sum("line_gross_profit"), D0),
            qty=Coalesce(Sum("qty"), D0),
            sale_count=Count("sale_id", distinct=True),
        )
        .order_by(f"-{criterion}")
    )

    # Get current stock for each product
    stock_map = {}
    if agg:
        pids = [r["product_id"] for r in agg]
        for si in StockItem.objects.filter(
            tenant_id=t_id, warehouse__store_id=s_id,
            product_id__in=pids,
        ).values("product_id").annotate(
            total_stock=Coalesce(Sum("on_hand"), D0),
            total_value=Coalesce(Sum("stock_value"), D0),
        ):
            stock_map[si["product_id"]] = {
                "stock": si["total_stock"],
                "stock_value": si["total_value"],
            }

    # FIX: use Decimal instead of float for grand_total
    grand_total = sum(r[criterion] for r in agg) or Decimal("1")
    cumulative = D0
    results = []

    for i, r in enumerate(agg):
        val = r[criterion]
        cumulative += val
        pct = (val / grand_total) * 100
        cum_pct = (cumulative / grand_total) * 100

        if cum_pct <= 80:
            abc_class = "A"
        elif cum_pct <= 95:
            abc_class = "B"
        else:
            abc_class = "C"

        stk = stock_map.get(r["product_id"], {})

        results.append({
            "rank": i + 1,
            "product_id": r["product_id"],
            "product_name": r["product__name"],
            "sku": r["product__sku"] or "",
            "category": r["product__category__name"] or "Sin categoría",
            "abc_class": abc_class,
            "revenue": str(r["revenue"]),
            "cost": str(r["cost"]),
            "profit": str(r["profit"]),
            "margin_pct": str(_margin_pct(r["profit"], r["revenue"])),
            "qty": str(r["qty"]),
            "sale_count": r["sale_count"],
            "contribution_pct": str(Decimal(str(pct)).quantize(Decimal("0.1"))),
            "cumulative_pct": str(Decimal(str(cum_pct)).quantize(Decimal("0.1"))),
            "current_stock": str(stk.get("stock", D0)),
            "stock_value": str(stk.get("stock_value", D0)),
        })

    # Summary per class
    class_summary = {}
    for cls in ("A", "B", "C"):
        items = [r for r in results if r["abc_class"] == cls]
        cls_revenue = sum(Decimal(r["revenue"]) for r in items)
        cls_profit = sum(Decimal(r["profit"]) for r in items)
        cls_stock = sum(Decimal(r["stock_value"]) for r in items)
        cls_contribution = sum(Decimal(r["contribution_pct"]) for r in items) if items else D0
        class_summary[cls] = {
            "count": len(items),
            "pct_products": str(Decimal(str(len(items) / max(len(results), 1) * 100)).quantize(Decimal("0.1"))),
            "revenue": str(cls_revenue),
            "profit": str(cls_profit),
            "pct_revenue": str(Decimal(str(cls_contribution)).quantize(Decimal("0.1"))),
            "stock_value": str(cls_stock),
        }

    return {
        "meta": {
            "date_from": str(date_from), "date_to": str(date_to),
            "warehouse_id": warehouse_id, "criterion": criterion,
            "total_products": len(results),
            "grand_total": str(Decimal(str(grand_total)).quantize(Decimal("1"))),
        },
        "class_summary": class_summary,
        "results": results,
    }
