"""
tables/views.py — Table and open order management API.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.permissions import HasTenant

logger = logging.getLogger(__name__)

from sales.services import SaleValidationError, StockShortageError

from .models import Table, OpenOrder, OpenOrderLine
from .services import checkout_order, CheckoutError


def _t(request):
    return getattr(request.user, "tenant_id", None)

def _s(request):
    return getattr(request.user, "active_store_id", None)

def _w(request):
    return getattr(request.user, "active_warehouse_id", None)


def _table_data(table):
    active_order = None
    if table.status == Table.STATUS_OPEN:
        order = table.orders.filter(status=OpenOrder.STATUS_OPEN).first()
        if order:
            active_lines = order.lines.filter(is_paid=False, is_cancelled=False)
            active_order = {
                "id": order.id,
                "opened_at": order.opened_at.isoformat(),
                "items_count": active_lines.count(),
                "subtotal": str(
                    sum(l.qty * l.unit_price for l in active_lines)
                ),
                "customer_name": order.customer_name,
            }
    return {
        "id":           table.id,
        "name":         table.name,
        "capacity":     table.capacity,
        "status":       table.status,
        "is_active":    table.is_active,
        "zone":         table.zone,
        "is_counter":   table.is_counter,
        "active_order": active_order,
        "position_x":   table.position_x,
        "position_y":   table.position_y,
        "shape":        table.shape,
        "width":        table.width,
        "height":       table.height,
        "rotation":     table.rotation,
    }


def _line_data(line):
    return {
        "id":          line.id,
        "product_id":  line.product_id,
        "product_name": line.product.name,
        "qty":         str(line.qty),
        "unit_price":  str(line.unit_price),
        "line_total":  str((line.qty * line.unit_price).quantize(Decimal("0.01"))),
        "note":        line.note,
        "added_at":    line.added_at.isoformat(),
        "added_by":    line.added_by.get_full_name() or line.added_by.email,
        "is_paid":     line.is_paid,
        "is_cancelled": line.is_cancelled,
        "cancel_reason": line.cancel_reason or "",
    }


def _order_data(order, include_lines=False):
    d = {
        "id":         order.id,
        "table_id":   order.table_id,
        "table_name": order.table.name,
        "status":     order.status,
        "opened_by":  order.opened_by.get_full_name() or order.opened_by.email,
        "opened_at":  order.opened_at.isoformat(),
        "closed_at":  order.closed_at.isoformat() if order.closed_at else None,
        "customer_name": order.customer_name,
        "note":       order.note,
        "warehouse_id": order.warehouse_id,
    }
    if include_lines:
        lines = list(order.lines.select_related("product", "added_by").order_by("added_at"))
        d["lines"] = [_line_data(l) for l in lines]
        unpaid = [l for l in lines if not l.is_paid and not l.is_cancelled]
        d["subtotal_unpaid"] = str(
            sum((l.qty * l.unit_price).quantize(Decimal("0.01")) for l in unpaid)
        )
    return d


# ══════════════════════════════════════════════════════════════════════════════
# TABLES
# ══════════════════════════════════════════════════════════════════════════════

class TableListCreate(APIView):
    """GET /tables/tables/ — list active tables with current order summary.
       POST /tables/tables/ — create a table."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _t(request); s_id = _s(request)
        from .models import OpenOrder, OpenOrderLine
        tables = (
            Table.objects
            .filter(tenant_id=t_id, store_id=s_id, is_active=True)
            .prefetch_related(
                Prefetch(
                    "orders",
                    queryset=OpenOrder.objects.filter(
                        status=OpenOrder.STATUS_OPEN
                    ).prefetch_related("lines"),
                )
            )
            .order_by("name")[:200]  # Cap to prevent unbounded response
        )
        return Response([_table_data(t) for t in tables])

    def post(self, request):
        t_id = _t(request); s_id = _s(request)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name required"}, status=400)
        try:
            capacity = int(request.data.get("capacity") or 4)
            if capacity < 1:
                capacity = 1
        except (ValueError, TypeError):
            capacity = 4

        zone = (request.data.get("zone") or "").strip()
        is_counter = bool(request.data.get("is_counter", False))

        if Table.objects.filter(tenant_id=t_id, store_id=s_id, name=name).exists():
            return Response({"detail": "Table with this name already exists"}, status=409)

        # Floor plan fields
        shape = request.data.get("shape", "square")
        if shape not in ("round", "square", "rect"):
            shape = "square"
        try:
            pos_x = float(request.data.get("position_x", 0))
            pos_y = float(request.data.get("position_y", 0))
            w = float(request.data.get("width", 8))
            h = float(request.data.get("height", 8))
            rot = float(request.data.get("rotation", 0))
        except (ValueError, TypeError):
            pos_x = pos_y = 0; w = h = 8; rot = 0

        table = Table.objects.create(
            tenant_id=t_id, store_id=s_id, name=name, capacity=capacity,
            zone=zone, is_counter=is_counter,
            shape=shape, position_x=pos_x, position_y=pos_y,
            width=w, height=h, rotation=rot,
        )
        return Response(_table_data(table), status=201)


class TableDetail(APIView):
    """PATCH /tables/tables/<id>/ — update name/capacity/is_active."""
    permission_classes = [IsAuthenticated, HasTenant]

    def patch(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            table = Table.objects.get(id=pk, tenant_id=t_id, store_id=s_id)
        except Table.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)

        update_fields = []
        if "name" in request.data:
            name = (request.data["name"] or "").strip()
            if not name:
                return Response({"detail": "El nombre de la mesa no puede estar vacío."}, status=400)
            table.name = name
            update_fields.append("name")
        if "capacity" in request.data:
            try:
                cap = int(request.data["capacity"])
                if cap < 1:
                    return Response({"detail": "La capacidad debe ser al menos 1."}, status=400)
                table.capacity = cap
            except (ValueError, TypeError):
                return Response({"detail": "Capacidad inválida."}, status=400)
            update_fields.append("capacity")
        if "is_active" in request.data:
            table.is_active = bool(request.data["is_active"])
            update_fields.append("is_active")
        if "zone" in request.data:
            table.zone = (request.data["zone"] or "").strip()
            update_fields.append("zone")
        if "is_counter" in request.data:
            table.is_counter = bool(request.data["is_counter"])
            update_fields.append("is_counter")

        # Floor plan fields
        for field in ("position_x", "position_y", "rotation", "width", "height"):
            if field in request.data:
                try:
                    setattr(table, field, float(request.data[field]))
                    update_fields.append(field)
                except (ValueError, TypeError):
                    pass
        if "shape" in request.data:
            shape = request.data["shape"]
            if shape in ("round", "square", "rect"):
                table.shape = shape
                update_fields.append("shape")

        if update_fields:
            table.save(update_fields=update_fields)
        return Response(_table_data(table))


class SaveTableLayout(APIView):
    """POST /tables/tables/save-layout/ — bulk update table positions."""
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        t_id = _t(request); s_id = _s(request)
        positions = request.data.get("positions", [])
        if not positions:
            return Response({"detail": "positions es requerido."}, status=400)

        updated = 0
        for pos in positions:
            tid = pos.get("id")
            if not tid:
                continue
            try:
                table = Table.objects.get(id=tid, tenant_id=t_id, store_id=s_id)
            except Table.DoesNotExist:
                continue

            fields = []
            for f in ("position_x", "position_y", "rotation", "width", "height"):
                if f in pos:
                    try:
                        setattr(table, f, float(pos[f]))
                        fields.append(f)
                    except (ValueError, TypeError):
                        pass
            if "shape" in pos and pos["shape"] in ("round", "square", "rect"):
                table.shape = pos["shape"]
                fields.append("shape")

            if fields:
                table.save(update_fields=fields)
                updated += 1

        return Response({"ok": True, "updated": updated})


class OpenOrderView(APIView):
    """POST /tables/tables/<id>/open/ — open an order on a free table."""
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)

        # Resolve warehouse: accept from body, fall back to user attr, then store's first warehouse
        from core.models import Warehouse
        w_id = (
            request.data.get("warehouse_id")
            or _w(request)
        )
        if not w_id:
            wh = Warehouse.objects.filter(tenant_id=t_id, store_id=s_id, is_active=True).first()
            if not wh:
                return Response({"detail": "No warehouse configured for this store"}, status=400)
            w_id = wh.id
        else:
            # Validar que el warehouse pertenece al tenant y store
            if not Warehouse.objects.filter(id=w_id, tenant_id=t_id, store_id=s_id, is_active=True).exists():
                return Response({"detail": "Bodega no encontrada o no pertenece a esta tienda."}, status=400)

        try:
            table = Table.objects.select_for_update().get(
                id=pk, tenant_id=t_id, store_id=s_id, is_active=True
            )
        except Table.DoesNotExist:
            return Response({"detail": "Table not found"}, status=404)

        if table.status == Table.STATUS_OPEN:
            return Response({"detail": "Table already has an open order"}, status=409)

        note = (request.data.get("note") or "").strip()
        customer_name = (request.data.get("customer_name") or "").strip()
        order = OpenOrder.objects.create(
            tenant_id=t_id,
            store_id=s_id,
            warehouse_id=w_id,
            table=table,
            opened_by=request.user,
            customer_name=customer_name,
            note=note,
        )
        table.status = Table.STATUS_OPEN
        table.save(update_fields=["status"])

        return Response(_order_data(order, include_lines=True), status=201)


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════════

class OrderDetail(APIView):
    """GET /tables/orders/<id>/ — full detail with lines."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            order = OpenOrder.objects.select_related("table", "opened_by").get(
                id=pk, tenant_id=t_id, store_id=s_id
            )
        except OpenOrder.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        return Response(_order_data(order, include_lines=True))


class AddLinesView(APIView):
    """POST /tables/orders/<id>/add-lines/ — add items to an open order."""
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            order = OpenOrder.objects.get(
                id=pk, tenant_id=t_id, store_id=s_id, status=OpenOrder.STATUS_OPEN
            )
        except OpenOrder.DoesNotExist:
            return Response({"detail": "Open order not found"}, status=404)

        items = request.data.get("lines") or []
        if not items:
            return Response({"detail": "lines must be a non-empty list"}, status=400)
        if len(items) > 100:
            return Response({"detail": "Máximo 100 líneas por pedido."}, status=400)

        from catalog.models import Product
        product_ids = [int(l.get("product_id", 0)) for l in items]
        products = {p.id: p for p in Product.objects.filter(tenant_id=t_id, id__in=product_ids, is_active=True)}

        new_lines = []
        for item in items:
            try:
                pid = int(item.get("product_id", 0))
            except (ValueError, TypeError):
                return Response({"detail": "product_id debe ser un número"}, status=400)
            p = products.get(pid)
            if not p:
                return Response({"detail": f"Product {pid} not found or inactive"}, status=400)
            try:
                raw_qty = item.get("qty")
                qty = Decimal(str(raw_qty)) if raw_qty is not None else Decimal("1")
                raw_price = item.get("unit_price")
                unit_price = Decimal(str(raw_price)) if raw_price is not None else (p.price or Decimal("0"))
            except (ValueError, ArithmeticError, TypeError):
                return Response({"detail": "Invalid qty or unit_price"}, status=400)
            if qty <= 0:
                return Response({"detail": "qty must be > 0"}, status=400)
            if unit_price < 0:
                return Response({"detail": "unit_price no puede ser negativo."}, status=400)

            note = (item.get("note") or "").strip()
            new_lines.append(
                OpenOrderLine(
                    tenant_id=t_id,
                    order=order,
                    product=p,
                    qty=qty,
                    unit_price=unit_price,
                    note=note,
                    added_by=request.user,
                )
            )

        OpenOrderLine.objects.bulk_create(new_lines)
        # Reload to return full order
        order.refresh_from_db()
        return Response(_order_data(order, include_lines=True), status=201)


class DeleteLineView(APIView):
    """DELETE /tables/orders/<id>/lines/<line_id>/ — cancel an unpaid line (keeps it visible)."""
    permission_classes = [IsAuthenticated, HasTenant]

    def delete(self, request, pk, line_id):
        t_id = _t(request); s_id = _s(request)
        try:
            order = OpenOrder.objects.get(
                id=pk, tenant_id=t_id, store_id=s_id, status=OpenOrder.STATUS_OPEN
            )
        except OpenOrder.DoesNotExist:
            return Response({"detail": "Open order not found"}, status=404)

        try:
            line = OpenOrderLine.objects.get(id=line_id, order=order, is_paid=False, is_cancelled=False)
        except OpenOrderLine.DoesNotExist:
            return Response({"detail": "Line not found, already paid, or already cancelled"}, status=404)

        line.is_cancelled = True
        line.cancelled_at = timezone.now()
        line.cancel_reason = (request.data.get("reason") or "").strip()[:255]
        line.save(update_fields=["is_cancelled", "cancelled_at", "cancel_reason"])
        order.refresh_from_db()
        return Response(_order_data(order, include_lines=True))


class CheckoutView(APIView):
    """POST /tables/orders/<id>/checkout/ — pay all or partial lines."""
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)

        mode = (request.data.get("mode") or "all").lower()
        if mode not in ("all", "partial"):
            return Response({"detail": "mode must be 'all' or 'partial'"}, status=400)

        line_ids = request.data.get("line_ids") or []
        payments_in = request.data.get("payments") or []

        sale_type = (request.data.get("sale_type") or "VENTA").upper()
        if sale_type not in ("VENTA", "CONSUMO_INTERNO"):
            return Response({"detail": "sale_type inválido"}, status=400)
        if sale_type == "CONSUMO_INTERNO" and not request.user.is_manager:
            return Response({"detail": "Solo administradores pueden registrar consumo interno"}, status=403)

        try:
            tip = max(Decimal("0"), Decimal(str(request.data.get("tip") or 0)))
        except (ValueError, ArithmeticError, TypeError):
            tip = Decimal("0")

        try:
            result = checkout_order(
                order_id=pk,
                tenant_id=t_id,
                store_id=s_id,
                mode=mode,
                line_ids=line_ids,
                payments_in=payments_in,
                tip=tip,
                user=request.user,
                sale_type=sale_type,
            )
        except CheckoutError as exc:
            return Response(exc.detail, status=exc.status_code)
        except SaleValidationError as exc:
            return Response(exc.detail, status=exc.status_code)
        except StockShortageError as exc:
            return Response(
                {"detail": "Insufficient stock", "shortages": exc.shortages},
                status=409,
            )

        # Return sale summary (exclude the Sale instance object)
        return Response(
            {k: v for k, v in result.items() if k != "sale"},
            status=201,
        )


class CancelOrderView(APIView):
    """POST /tables/orders/<id>/cancel/ — cancel an open order (close without payment)."""
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            order = OpenOrder.objects.select_for_update().get(
                id=pk, tenant_id=t_id, store_id=s_id, status=OpenOrder.STATUS_OPEN
            )
        except OpenOrder.DoesNotExist:
            return Response({"detail": "Open order not found"}, status=404)

        if order.lines.filter(is_paid=True).exists():
            return Response({"detail": "No se puede cancelar una orden con líneas cobradas"}, status=409)

        active_unpaid = order.lines.filter(is_paid=False, is_cancelled=False)
        if active_unpaid.exists():
            return Response({"detail": "Hay ítems pendientes. Cancélalos o cóbralos antes de cerrar."}, status=409)

        order.lines.filter(is_paid=False).delete()
        order.status = OpenOrder.STATUS_CLOSED
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])

        table = Table.objects.select_for_update().get(id=order.table_id)
        table.status = Table.STATUS_FREE
        table.save(update_fields=["status"])

        return Response({"detail": "Order cancelled"})


class ActiveOrderByTable(APIView):
    """GET /tables/tables/<id>/order/ — get the active open order for a table."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            table = Table.objects.get(id=pk, tenant_id=t_id, store_id=s_id)
        except Table.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)

        order = table.orders.filter(status=OpenOrder.STATUS_OPEN).select_related("table", "opened_by").first()
        if not order:
            return Response({"detail": "No open order for this table"}, status=404)
        return Response(_order_data(order, include_lines=True))


class CounterOrderView(APIView):
    """POST /tables/counter-order/ — create a takeaway order instantly.
    Finds the first free counter table, or auto-creates one.
    Opens an order on it and returns the order data.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request):
        t_id = _t(request); s_id = _s(request)

        # Resolve warehouse
        from core.models import Warehouse
        w_id = _w(request)
        if not w_id:
            wh = Warehouse.objects.filter(tenant_id=t_id, store_id=s_id, is_active=True).first()
            if not wh:
                return Response({"detail": "No warehouse configured"}, status=400)
            w_id = wh.id

        # Find first free counter table
        counter_table = (
            Table.objects.select_for_update()
            .filter(tenant_id=t_id, store_id=s_id, is_counter=True, is_active=True, status=Table.STATUS_FREE)
            .first()
        )

        if not counter_table:
            # Cap: max 20 counter tables per store, reuse inactive ones first
            # Lock ALL counter tables to prevent TOCTOU race on count
            MAX_COUNTER_TABLES = 20
            locked_counters = list(
                Table.objects.select_for_update()
                .filter(tenant_id=t_id, store_id=s_id, is_counter=True)
            )
            existing_count = len(locked_counters)

            if existing_count >= MAX_COUNTER_TABLES:
                # Reactivate an inactive counter table
                reusable = next(
                    (t for t in locked_counters if not t.is_active), None
                )
                if reusable:
                    reusable.is_active = True
                    reusable.status = Table.STATUS_FREE
                    reusable.save(update_fields=["is_active", "status"])
                    counter_table = reusable
                else:
                    return Response(
                        {"detail": "Máximo de mesas para llevar alcanzado. Cierra pedidos abiertos."},
                        status=409,
                    )
            else:
                counter_table = Table.objects.create(
                    tenant_id=t_id,
                    store_id=s_id,
                    name=f"Para llevar #{existing_count + 1}",
                    capacity=1,
                    is_counter=True,
                    zone="",
                )

        # Open order on the counter table
        customer_name = (request.data.get("customer_name") or "").strip()
        order = OpenOrder.objects.create(
            tenant_id=t_id,
            store_id=s_id,
            warehouse_id=w_id,
            table=counter_table,
            opened_by=request.user,
            customer_name=customer_name,
            note="Pedido para llevar",
        )
        counter_table.status = Table.STATUS_OPEN
        counter_table.save(update_fields=["status"])

        return Response(_order_data(order, include_lines=True), status=201)
