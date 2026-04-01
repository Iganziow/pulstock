from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction, IntegrityError
from django.db.models import (
    OuterRef, Subquery, Value, F, Case, When, ExpressionWrapper,
    DecimalField, Sum, Q, Count
)
from django.db.models.functions import Coalesce
from django.db.models import Exists

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination

from core.permissions import HasTenant
from core.models import Warehouse
from catalog.models import Product
from .models import StockItem, StockMove, StockTransfer, StockTransferLine
from .serializers import (
    StockAdjustSerializer,
    StockMoveListSerializer,
    StockReceiveSerializer,
    StockIssueSerializer,
    StockTransferSerializer,
    KardexRowSerializer,
    TransferDetailSerializer,
    TransferListSerializer,
)

# ======================================================
# Helpers
# ======================================================

QTY_3 = Decimal("0.001")
COST_3 = Decimal("0.001")
VAL_3 = Decimal("0.001")

def q3(v: Decimal) -> Decimal:
    return (v or Decimal("0")).quantize(QTY_3, rounding=ROUND_HALF_UP)

def c3(v: Decimal) -> Decimal:
    return (v or Decimal("0")).quantize(COST_3, rounding=ROUND_HALF_UP)

def v3(v: Decimal) -> Decimal:
    return (v or Decimal("0")).quantize(VAL_3, rounding=ROUND_HALF_UP)

def _tenant_id(request):
    return getattr(request.user, "tenant_id", None)

def _active_store_id(request):
    return getattr(request.user, "active_store_id", None)

def _require_active_store_id(request):
    s_id = _active_store_id(request)
    if not s_id:
        return None, Response(
            {"detail": "active_store is required. Set user.active_store before using inventory."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return int(s_id), None

def _get_warehouse_for_user(request, warehouse_id: int):
    t_id = _tenant_id(request)
    if not t_id:
        return None, Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

    s_id, err = _require_active_store_id(request)
    if err:
        return None, err

    wh = (
        Warehouse.objects
        .filter(id=warehouse_id, tenant_id=t_id)
        .select_related("store")
        .first()
    )
    if not wh:
        return None, Response({"detail": "Invalid warehouse"}, status=status.HTTP_400_BAD_REQUEST)

    if wh.store_id is None:
        return None, Response(
            {"detail": "Warehouse has no store assigned (migration pending)."},
            status=status.HTTP_409_CONFLICT,
        )

    if wh.store_id != s_id:
        return None, Response(
            {
                "detail": "Warehouse does not belong to your active store.",
                "active_store_id": s_id,
                "warehouse_store_id": wh.store_id,
            },
            status=status.HTTP_409_CONFLICT,
        )

    if not wh.is_active:
        return None, Response(
            {"detail": "La bodega está desactivada."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return wh, None

def _get_product_for_user(request, product_id: int):
    t_id = _tenant_id(request)
    if not t_id:
        return None, Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

    p = Product.objects.filter(id=product_id, tenant_id=t_id).first()
    if not p:
        return None, Response({"detail": "Invalid product"}, status=status.HTTP_400_BAD_REQUEST)
    return p, None

def _get_or_create_stockitem_locked(*, tenant_id: int, warehouse_id: int, product_id: int) -> StockItem:
    """
    Devuelve StockItem con lock select_for_update.
    Maneja carrera de create por unique constraint.
    """
    try:
        si = (
            StockItem.objects
            .select_for_update()
            .filter(tenant_id=tenant_id, warehouse_id=warehouse_id, product_id=product_id)
            .first()
        )
        if si:
            return si

        return StockItem.objects.create(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            on_hand=Decimal("0.000"),
            avg_cost=Decimal("0.000"),
            stock_value=Decimal("0.000"),
        )
    except IntegrityError:
        return (
            StockItem.objects
            .select_for_update()
            .get(tenant_id=tenant_id, warehouse_id=warehouse_id, product_id=product_id)
        )

def _weighted_avg_cost(old_qty: Decimal, old_avg: Decimal, in_qty: Decimal, in_cost: Decimal) -> Decimal:
    """
    avg_cost nuevo = (old_value + in_value) / new_qty
    old_value = old_qty * old_avg
    in_value  = in_qty  * in_cost
    """
    old_qty = q3(old_qty)
    in_qty = q3(in_qty)
    old_avg = c3(old_avg)
    in_cost = c3(in_cost)

    new_qty = old_qty + in_qty
    if new_qty <= 0:
        return Decimal("0.000")

    old_value = v3(old_qty * old_avg)
    in_value = v3(in_qty * in_cost)
    new_avg = (old_value + in_value) / new_qty
    return c3(new_avg)

# ======================================================
# STOCK: ADJUST / RECEIVE / ISSUE (con costo)
# ======================================================

class StockAdjust(APIView):
    """
    Ajuste manual (delta puede ser +/-).
    Costeo:
      - si qty > 0: usa avg_cost actual (si existe) como costo de entrada (MVP)
      - si qty < 0: descuenta valor al avg_cost actual
    Nota: si quieres permitir "ajuste con costo", se agrega unit_cost al serializer.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        ser = StockAdjustSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        warehouse_id = int(ser.validated_data["warehouse_id"])
        product_id = int(ser.validated_data["product_id"])
        qty          = q3(ser.validated_data["qty"])
        note         = ser.validated_data.get("note", "") or "Stock adjustment"
        new_avg_cost = ser.validated_data.get("new_avg_cost")  # opcional

        if qty == 0 and new_avg_cost is None:
            return Response(
                {"detail": "qty must not be 0 unless new_avg_cost is provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err
        _, err = _get_product_for_user(request, product_id)
        if err:
            return err

        si = _get_or_create_stockitem_locked(tenant_id=t_id, warehouse_id=warehouse_id, product_id=product_id)

        new_on_hand = q3(si.on_hand + qty)
        if new_on_hand < 0:
            return Response(
                {
                    "detail": "Insufficient stock for adjustment",
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "current_on_hand": str(si.on_hand),
                    "attempt_delta": str(qty),
                    "would_be": str(new_on_hand),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # costo snapshot: avg_cost actual
        cost_snapshot = c3(si.avg_cost or Decimal("0.000"))
        value_delta = v3(qty * cost_snapshot)  # qty puede ser negativo aquí

        if new_avg_cost is not None:
            # Sobrescritura directa: recalcular stock_value con el nuevo avg_cost
            forced_avg = c3(new_avg_cost)
            new_on_hand_val = q3(si.on_hand + qty)
            new_stock_value = v3(new_on_hand_val * forced_avg)
            StockItem.objects.filter(id=si.id).update(
                on_hand=F("on_hand") + qty,
                avg_cost=forced_avg,
                stock_value=new_stock_value,
            )
        else:
            # update stock + valor (avg_cost no cambia en ajuste por defecto)
            StockItem.objects.filter(id=si.id).update(
                on_hand=F("on_hand") + qty,
                stock_value=F("stock_value") + value_delta,
            )
        si.refresh_from_db(fields=["on_hand", "avg_cost", "stock_value"])

        StockMove.objects.create(
            tenant_id=t_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            move_type=StockMove.ADJ,
            qty=qty,
            unit_cost=None,
            reason="",
            ref_type="ADJUST",
            ref_id=None,
            note=note,
            created_by=request.user,
            cost_snapshot=cost_snapshot,
            value_delta=value_delta,
        )

        return Response(
            {
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "new_stock": str(si.on_hand),
                "avg_cost": str(si.avg_cost),
                "stock_value": str(si.stock_value),
                "warehouse_store_id": getattr(wh, "store_id", None),
            },
            status=status.HTTP_201_CREATED,
        )


class StockReceive(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        ser = StockReceiveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        warehouse_id = int(ser.validated_data["warehouse_id"])
        product_id = int(ser.validated_data["product_id"])
        qty = q3(ser.validated_data["qty"])
        unit_cost = ser.validated_data.get("unit_cost", None)
        unit_cost = c3(unit_cost) if unit_cost is not None else None
        note = ser.validated_data.get("note", "") or "Stock receive"

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err
        _, err = _get_product_for_user(request, product_id)
        if err:
            return err

        si = _get_or_create_stockitem_locked(tenant_id=t_id, warehouse_id=warehouse_id, product_id=product_id)

        old_qty = q3(si.on_hand)
        old_avg = c3(si.avg_cost or Decimal("0.000"))
        old_val = v3(si.stock_value if si.stock_value is not None else (old_qty * old_avg))

        # costo “de entrada”
        in_cost = unit_cost if unit_cost is not None else old_avg
        in_cost = c3(in_cost)

        in_value = v3(qty * in_cost)

        new_qty = q3(old_qty + qty)
        new_val = v3(old_val + in_value)

        # recalcula avg solo si viene unit_cost; si no, mantenlo
        if unit_cost is not None:
            new_avg = c3(new_val / new_qty) if new_qty > 0 else Decimal("0.000")
        else:
            new_avg = old_avg

        StockItem.objects.filter(id=si.id).update(
            on_hand=F("on_hand") + qty,
            stock_value=F("stock_value") + in_value,
            avg_cost=new_avg,
        )
        si.refresh_from_db(fields=["on_hand", "avg_cost", "stock_value"])

        move = StockMove.objects.create(
            tenant_id=t_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            move_type=StockMove.IN,
            qty=qty,
            unit_cost=unit_cost,  # factura si viene
            reason="",
            ref_type="RECEIVE",
            ref_id=None,
            note=note,
            created_by=request.user,
            cost_snapshot=in_cost,     # lo que usaste para valorar esta entrada
            value_delta=in_value,      # +valor
        )

        return Response(
            {
                "move_id": move.id,
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "new_stock": str(si.on_hand),
                "avg_cost": str(si.avg_cost),
                "stock_value": str(si.stock_value),
                "warehouse_store_id": getattr(wh, "store_id", None),
            },
            status=status.HTTP_201_CREATED,
        )


class StockIssue(APIView):
    """
    Salida con motivo.
    Costeo: usa avg_cost actual del StockItem como snapshot.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        ser = StockIssueSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        warehouse_id = int(ser.validated_data["warehouse_id"])
        product_id = int(ser.validated_data["product_id"])
        qty = q3(ser.validated_data["qty"])
        reason = ser.validated_data["reason"]
        note = ser.validated_data.get("note", "") or "Stock issue"

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err
        _, err = _get_product_for_user(request, product_id)
        if err:
            return err

        si = _get_or_create_stockitem_locked(tenant_id=t_id, warehouse_id=warehouse_id, product_id=product_id)

        new_on_hand = q3(si.on_hand - qty)
        if new_on_hand < 0:
            return Response(
                {
                    "detail": "Insufficient stock",
                    "product_id": product_id,
                    "warehouse_id": warehouse_id,
                    "current_on_hand": str(si.on_hand),
                    "required": str(qty),
                },
                status=status.HTTP_409_CONFLICT,
            )

        cost_snapshot = c3(si.avg_cost or Decimal("0.000"))
        out_value = v3(qty * cost_snapshot)  # valor absoluto
        value_delta = -out_value

        StockItem.objects.filter(id=si.id).update(
            on_hand=F("on_hand") - qty,
            stock_value=F("stock_value") - out_value,
        )
        si.refresh_from_db(fields=["on_hand", "avg_cost", "stock_value"])

        move = StockMove.objects.create(
            tenant_id=t_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            move_type=StockMove.OUT,
            qty=qty,
            unit_cost=None,
            reason=reason,
            ref_type="ISSUE",
            ref_id=None,
            note=note,
            created_by=request.user,
            cost_snapshot=cost_snapshot,
            value_delta=value_delta,
        )

        return Response(
            {
                "move_id": move.id,
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "new_stock": str(si.on_hand),
                "avg_cost": str(si.avg_cost),
                "stock_value": str(si.stock_value),
                "issue_reason": reason,
                "warehouse_store_id": getattr(wh, "store_id", None),
            },
            status=status.HTTP_201_CREATED,
        )


# ======================================================
# MOVES LIST
# ======================================================
class StockMoveList(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = StockMoveListSerializer

    def get_queryset(self):
        t_id = _tenant_id(self.request)
        if not t_id:
            return StockMove.objects.none()

        s_id = _active_store_id(self.request)
        if not s_id:
            raise ValidationError({"detail": "active_store is required. Set user.active_store before using inventory."})

        qs = (
            StockMove.objects
            .filter(tenant_id=t_id, warehouse__store_id=int(s_id))
            .select_related("product", "created_by", "warehouse", "warehouse__store")
            .prefetch_related("product__barcodes")
            .order_by("-id")
        )

        warehouse_id = (self.request.query_params.get("warehouse_id") or "").strip()
        if warehouse_id.isdigit():
            qs = qs.filter(warehouse_id=int(warehouse_id))

        move_type = (self.request.query_params.get("move_type") or "").strip().upper()
        if move_type in ["IN", "OUT", "ADJ"]:
            qs = qs.filter(move_type=move_type)

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(product__name__icontains=q) |
                Q(product__sku__icontains=q) |
                Q(product__barcodes__code__icontains=q)
            ).distinct()

        date_from = (self.request.query_params.get("from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = (self.request.query_params.get("to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        ref_type = (self.request.query_params.get("ref_type") or "").strip()
        if ref_type:
            qs = qs.filter(ref_type=ref_type)

        ref_id = (self.request.query_params.get("ref_id") or "").strip()
        if ref_id.isdigit():
            qs = qs.filter(ref_id=int(ref_id))

        return qs


# ======================================================
# STOCK LIST
# ======================================================
class StockList(APIView):
    """
    GET /api/inventory/stock/?warehouse_id=X&q=...&page=1

    Paginación real con PageNumberPagination (PAGE_SIZE=50 global).
    Retrocompatible: si no viene ?page=, devuelve todo (max 200) en
    formato {warehouse_id, count, results} para no romper el frontend
    existente. Cuando el frontend envíe ?page=, devuelve formato
    {count, next, previous, results} estándar de DRF.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    class _Pager(PageNumberPagination):
        page_size = 50
        page_size_query_param = "page_size"
        max_page_size = 200

    def get(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        warehouse_id = (request.query_params.get("warehouse_id") or "").strip()
        if not warehouse_id.isdigit():
            return Response({"detail": "warehouse_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        warehouse_id = int(warehouse_id)

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err

        q = (request.query_params.get("q") or "").strip()

        si_on_hand_qs = (
            StockItem.objects
            .filter(tenant_id=t_id, warehouse_id=warehouse_id, product_id=OuterRef("pk"))
            .values("on_hand")[:1]
        )
        si_avg_cost_qs = (
            StockItem.objects
            .filter(tenant_id=t_id, warehouse_id=warehouse_id, product_id=OuterRef("pk"))
            .values("avg_cost")[:1]
        )

        qs = (
            Product.objects
            .filter(tenant_id=t_id)
            .select_related("category", "unit_obj")
            .prefetch_related("barcodes")
            .annotate(
                on_hand=Coalesce(Subquery(si_on_hand_qs), Value(Decimal("0.000"))),
                avg_cost=Coalesce(Subquery(si_avg_cost_qs), Value(Decimal("0.000"))),
            )
            .order_by("name")
        )

        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(sku__icontains=q) |
                Q(barcodes__code__icontains=q)
            ).distinct().order_by("name")

        def _serialize(product_list):
            results = []
            for p in product_list:
                barcode = None
                bcs = list(getattr(p, "barcodes", []).all()) if hasattr(p, "barcodes") else []
                if bcs:
                    barcode = bcs[0].code
                results.append({
                    "product_id": p.id,
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category.name if p.category else None,
                    "barcode": barcode,
                    "on_hand": str(p.on_hand),
                    "avg_cost": str(p.avg_cost),
                    "unit": p.unit_obj.code if p.unit_obj else (p.unit or "UN"),
                })
            return results

        # ── Paginated path (frontend sends ?page=) ───────────────────────
        if "page" in request.query_params:
            pager = self._Pager()
            page = pager.paginate_queryset(qs, request, view=self)
            results = _serialize(page)
            resp = pager.get_paginated_response(results)
            resp.data["warehouse_id"] = warehouse_id
            resp.data["warehouse_store_id"] = getattr(wh, "store_id", None)
            return resp

        # ── Legacy path (no ?page=) — cap at 200 for backward compat ─────
        limit = min(int(request.query_params.get("limit", 200)), 200)
        items = list(qs[:limit])
        results = _serialize(items)

        return Response({
            "warehouse_id": warehouse_id,
            "warehouse_store_id": getattr(wh, "store_id", None),
            "count": len(results),
            "results": results,
        })


# ======================================================
# TRANSFER CREATE (OFICIAL) con costo
# ======================================================
class StockTransferCreate(APIView):
    """
    Transfiere:
      - on_hand
      - stock_value
    Costeo:
      - snapshot = avg_cost ORIGEN
      - destino recalcula avg_cost ponderado (old_qty, old_avg, in_qty, snapshot_cost)
    """
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        ser = StockTransferSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        from_id = int(ser.validated_data["from_warehouse_id"])
        to_id = int(ser.validated_data["to_warehouse_id"])
        lines = ser.validated_data["lines"]

        wh_from, err = _get_warehouse_for_user(request, from_id)
        if err:
            return err
        wh_to, err = _get_warehouse_for_user(request, to_id)
        if err:
            return err

        if wh_from.store_id != wh_to.store_id:
            return Response(
                {
                    "detail": "Warehouses must belong to the same active store.",
                    "from_warehouse_store_id": wh_from.store_id,
                    "to_warehouse_store_id": wh_to.store_id,
                },
                status=status.HTTP_409_CONFLICT,
            )

        product_ids = sorted({int(l["product_id"]) for l in lines})
        existing = set(Product.objects.filter(tenant_id=t_id, id__in=product_ids).values_list("id", flat=True))
        missing = [pid for pid in product_ids if pid not in existing]
        if missing:
            return Response({"detail": "Invalid product(s)", "product_ids": missing}, status=status.HTTP_400_BAD_REQUEST)

        transfer_note = (request.data.get("note") or "").strip()
        transfer = StockTransfer.objects.create(
            tenant_id=t_id,
            from_warehouse_id=from_id,
            to_warehouse_id=to_id,
            note=transfer_note or "Transferencia",
            created_by=request.user,
        )

        # locks estables
        pairs = set()
        for l in lines:
            pid = int(l["product_id"])
            pairs.add((from_id, pid))
            pairs.add((to_id, pid))
        pairs_sorted = sorted(list(pairs), key=lambda x: (x[0], x[1]))

        locked_items = {}
        for wh_id, product_id in pairs_sorted:
            locked_items[(wh_id, product_id)] = _get_or_create_stockitem_locked(
                tenant_id=t_id, warehouse_id=wh_id, product_id=product_id
            )

        created_moves = []
        created_lines = []

        for l in lines:
            product_id = int(l["product_id"])
            qty = q3(l["qty"])
            note = (l.get("note") or "").strip() or "Stock transfer"

            si_from = locked_items[(from_id, product_id)]
            si_to = locked_items[(to_id, product_id)]

            if q3(si_from.on_hand - qty) < 0:
                return Response(
                    {
                        "detail": "Insufficient stock",
                        "product_id": product_id,
                        "from_warehouse_id": from_id,
                        "current_on_hand": str(si_from.on_hand),
                        "required": str(qty),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # costo snapshot desde ORIGEN (promedio ponderado)
            cost_snapshot = c3(si_from.avg_cost or Decimal("0.000"))
            line_value = v3(qty * cost_snapshot)

            # actualizar origen: baja qty y valor (avg_cost no cambia)
            StockItem.objects.filter(id=si_from.id).update(
                on_hand=F("on_hand") - qty,
                stock_value=F("stock_value") - line_value,
            )

            # destino: recalcular avg_cost ponderado y subir qty/valor
            old_qty_to = q3(si_to.on_hand)
            old_avg_to = c3(si_to.avg_cost or Decimal("0.000"))
            old_val_to = v3(si_to.stock_value if si_to.stock_value is not None else (old_qty_to * old_avg_to))


            new_avg_to = _weighted_avg_cost(old_qty_to, old_avg_to, qty, cost_snapshot)
            new_qty_to = q3(old_qty_to + qty)
            new_val_to = v3(old_val_to + line_value)

            StockItem.objects.filter(id=si_to.id).update(
                on_hand=new_qty_to,
                avg_cost=new_avg_to,
                stock_value=new_val_to,
            )

            line = StockTransferLine.objects.create(
                tenant_id=t_id,
                transfer=transfer,
                product_id=product_id,
                qty=qty,
                note=(l.get("note") or "").strip(),
            )
            created_lines.append(line.id)

            m_out = StockMove.objects.create(
                tenant_id=t_id,
                warehouse_id=from_id,
                product_id=product_id,
                move_type=StockMove.OUT,
                qty=qty,
                unit_cost=None,
                reason="",
                ref_type="TRANSFER",
                ref_id=transfer.id,
                note=note or f"Transfer to warehouse {to_id}",
                created_by=request.user,
                cost_snapshot=cost_snapshot,
                value_delta=-line_value,
            )
            m_in = StockMove.objects.create(
                tenant_id=t_id,
                warehouse_id=to_id,
                product_id=product_id,
                move_type=StockMove.IN,
                qty=qty,
                unit_cost=None,
                reason="",
                ref_type="TRANSFER",
                ref_id=transfer.id,
                note=note or f"Transfer from warehouse {from_id}",
                created_by=request.user,
                cost_snapshot=cost_snapshot,
                value_delta=+line_value,
            )

            created_moves.append({"out_move_id": m_out.id, "in_move_id": m_in.id})

        return Response(
            {
                "transfer_id": transfer.id,
                "from_warehouse_id": from_id,
                "to_warehouse_id": to_id,
                "store_id": wh_from.store_id,
                "line_ids": created_lines,
                "moves": created_moves,
            },
            status=status.HTTP_201_CREATED,
        )


# ======================================================
# KARDEX
# ======================================================
class KardexView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    class _Pager(LimitOffsetPagination):
        default_limit = 200
        max_limit = 2000

    def get(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        s_id = _active_store_id(request)
        if not s_id:
            return Response(
                {"detail": "active_store is required. Set user.active_store before using inventory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        warehouse_id = (request.query_params.get("warehouse_id") or "").strip()
        if not warehouse_id.isdigit():
            return Response({"detail": "warehouse_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        warehouse_id = int(warehouse_id)

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err

        product_id = (request.query_params.get("product_id") or "").strip()
        product_id_int = None
        if product_id:
            if not product_id.isdigit():
                return Response({"detail": "product_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
            product_id_int = int(product_id)
            _, err = _get_product_for_user(request, product_id_int)
            if err:
                return err

        date_from = (request.query_params.get("from") or "").strip()
        date_to = (request.query_params.get("to") or "").strip()
        move_type = (request.query_params.get("move_type") or "").strip().upper()
        q = (request.query_params.get("q") or "").strip()

        qs = (
            StockMove.objects
            .filter(
                tenant_id=t_id,
                warehouse_id=warehouse_id,
                warehouse__store_id=int(s_id),
            )
            .select_related("product", "created_by")
            .prefetch_related("product__barcodes")
        )

        if product_id_int is not None:
            qs = qs.filter(product_id=product_id_int)

        if move_type in ["IN", "OUT", "ADJ"]:
            qs = qs.filter(move_type=move_type)
        elif move_type == "TRANSFER":
            qs = qs.filter(ref_type="TRANSFER")

        if q:
            qs = qs.filter(
                Q(product__name__icontains=q) |
                Q(product__sku__icontains=q) |
                Q(product__barcodes__code__icontains=q)
            ).distinct()

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        qs = qs.order_by("created_at", "id")

        signed_qty = Case(
            When(
                move_type=StockMove.OUT,
                then=ExpressionWrapper(-F("qty"), output_field=DecimalField(max_digits=12, decimal_places=3))
            ),
            default=F("qty"),
            output_field=DecimalField(max_digits=12, decimal_places=3),
        )

        opening_by_product = {}
        if date_from:
            base_before = StockMove.objects.filter(
                tenant_id=t_id,
                warehouse_id=warehouse_id,
                warehouse__store_id=int(s_id),
                created_at__date__lt=date_from,
            )

            if product_id_int is not None:
                base_before = base_before.filter(product_id=product_id_int)
                opening = base_before.aggregate(v=Coalesce(Sum(signed_qty), Decimal("0.000")))["v"]
                opening_by_product[product_id_int] = opening or Decimal("0.000")
            else:
                rows = base_before.values("product_id").annotate(v=Coalesce(Sum(signed_qty), Decimal("0.000")))
                for r in rows:
                    opening_by_product[int(r["product_id"])] = r["v"] or Decimal("0.000")

        pager = self._Pager()
        page = pager.paginate_queryset(qs, request, view=self)

        balances = dict(opening_by_product)
        out_rows = []
        for m in page:
            pid = int(m.product_id)
            if pid not in balances:
                balances[pid] = Decimal("0.000")

            delta = m.qty
            if m.move_type == StockMove.OUT:
                delta = -delta

            balances[pid] = balances[pid] + delta
            m.balance = str(balances[pid])
            out_rows.append(m)

        ser = KardexRowSerializer(out_rows, many=True)
        return pager.get_paginated_response({
            "warehouse_id": warehouse_id,
            "warehouse_name": wh.name,
            "warehouse_type": wh.warehouse_type,
            "warehouse_store_id": getattr(wh, "store_id", None),
            "filters": {
                "product_id": product_id_int,
                "from": date_from or None,
                "to": date_to or None,
                "move_type": move_type or None,
                "q": q or None,
            },
            "results": ser.data,
        })


# ======================================================
# TRANSFER DETAIL
# ======================================================
class StockTransferDetail(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request, pk: int):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        s_id = _active_store_id(request)
        if not s_id:
            return Response(
                {"detail": "active_store is required. Set user.active_store before using inventory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tr = (
            StockTransfer.objects
            .filter(tenant_id=t_id, id=pk)
            .select_related("from_warehouse", "to_warehouse", "created_by")
            .prefetch_related("lines__product__barcodes")
            .first()
        )
        if not tr:
            raise NotFound("Transfer not found")

        if tr.from_warehouse.store_id != int(s_id) or tr.to_warehouse.store_id != int(s_id):
            return Response({"detail": "Transfer does not belong to your active store."}, status=status.HTTP_409_CONFLICT)

        return Response(TransferDetailSerializer(tr).data)


class StockTransferList(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = TransferListSerializer

    class _Pager(LimitOffsetPagination):
        default_limit = 50
        max_limit = 500

    pagination_class = _Pager

    def get_queryset(self):
        t_id = _tenant_id(self.request)
        if not t_id:
            return StockTransfer.objects.none()

        s_id = _active_store_id(self.request)
        if not s_id:
            raise ValidationError({"detail": "active_store is required. Set user.active_store before using inventory."})

        qs = (
            StockTransfer.objects
            .filter(tenant_id=t_id)
            .select_related("from_warehouse", "to_warehouse", "created_by")
            .filter(from_warehouse__store_id=int(s_id), to_warehouse__store_id=int(s_id))
            .annotate(lines_count=Count("lines", distinct=True))
            .order_by("-id")
        )

        date_from = (self.request.query_params.get("from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = (self.request.query_params.get("to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        warehouse_id = (self.request.query_params.get("warehouse_id") or "").strip()
        if warehouse_id.isdigit():
            wid = int(warehouse_id)
            qs = qs.filter(Q(from_warehouse_id=wid) | Q(to_warehouse_id=wid))

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            line_match = (
                StockTransferLine.objects
                .filter(tenant_id=t_id, transfer_id=OuterRef("pk"))
                .filter(
                    Q(product__name__icontains=q)
                    | Q(product__sku__icontains=q)
                    | Q(product__barcodes__code__icontains=q)
                )
            )
            qs = qs.annotate(_has_match=Exists(line_match)).filter(_has_match=True)

        return qs


class KardexReportView(APIView):
    """
    Resumen por producto:
      - in_qty, out_qty, adj_qty
      - net_qty
      - moves_count
    """
    permission_classes = [IsAuthenticated, HasTenant]

    class _Pager(LimitOffsetPagination):
        default_limit = 200
        max_limit = 2000

    def get(self, request):
        t_id = _tenant_id(request)
        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)

        s_id = _active_store_id(request)
        if not s_id:
            return Response(
                {"detail": "active_store is required. Set user.active_store before using inventory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        warehouse_id = (request.query_params.get("warehouse_id") or "").strip()
        if not warehouse_id.isdigit():
            return Response({"detail": "warehouse_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        warehouse_id = int(warehouse_id)

        wh, err = _get_warehouse_for_user(request, warehouse_id)
        if err:
            return err

        date_from = (request.query_params.get("from") or "").strip()
        date_to = (request.query_params.get("to") or "").strip()
        q = (request.query_params.get("q") or "").strip()

        base = StockMove.objects.filter(
            tenant_id=t_id,
            warehouse_id=warehouse_id,
            warehouse__store_id=int(s_id),
        )

        if date_from:
            base = base.filter(created_at__date__gte=date_from)
        if date_to:
            base = base.filter(created_at__date__lte=date_to)

        if q:
            base = base.filter(
                Q(product__name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product__barcodes__code__icontains=q)
            ).distinct()

        agg = (
            base.values("product_id", "product__name", "product__sku")
            .annotate(
                in_qty=Coalesce(Sum(Case(
                    When(move_type=StockMove.IN, then=F("qty")),
                    default=Value(Decimal("0.000")),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                )), Decimal("0.000")),
                out_qty=Coalesce(Sum(Case(
                    When(move_type=StockMove.OUT, then=F("qty")),
                    default=Value(Decimal("0.000")),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                )), Decimal("0.000")),
                adj_qty=Coalesce(Sum(Case(
                    When(move_type=StockMove.ADJ, then=F("qty")),
                    default=Value(Decimal("0.000")),
                    output_field=DecimalField(max_digits=12, decimal_places=3),
                )), Decimal("0.000")),
                moves_count=Count("id"),
            )
            .order_by("product__name", "product_id")
        )

        pager = self._Pager()
        page = pager.paginate_queryset(agg, request, view=self)

        product_ids = [int(r["product_id"]) for r in page]
        products = Product.objects.filter(tenant_id=t_id, id__in=product_ids).prefetch_related("barcodes")

        barcode_map = {}
        for p in products:
            bc = None
            bcs = list(getattr(p, "barcodes", []).all()) if hasattr(p, "barcodes") else []
            if bcs:
                bc = getattr(bcs[0], "code", None)
            barcode_map[p.id] = bc

        out = []
        for r in page:
            in_qty = r["in_qty"] or Decimal("0.000")
            out_qty = r["out_qty"] or Decimal("0.000")
            adj_qty = r["adj_qty"] or Decimal("0.000")
            net_qty = (in_qty - out_qty + adj_qty)

            out.append({
                "product": {
                    "id": int(r["product_id"]),
                    "name": r["product__name"],
                    "sku": r.get("product__sku"),
                    "barcode": barcode_map.get(int(r["product_id"])),
                },
                "in_qty": str(in_qty),
                "out_qty": str(out_qty),
                "adj_qty": str(adj_qty),
                "net_qty": str(net_qty),
                "moves_count": int(r["moves_count"] or 0),
            })

        # serializer "de dict" (no ModelSerializer)
        from .serializers import KardexReportRowSerializer
        ser = KardexReportRowSerializer(out, many=True)

        return pager.get_paginated_response({
            "warehouse_id": warehouse_id,
            "warehouse_name": wh.name,
            "warehouse_type": wh.warehouse_type,
            "warehouse_store_id": getattr(wh, "store_id", None),
            "filters": {
                "from": date_from or None,
                "to": date_to or None,
                "q": q or None,
            },
            "results": ser.data,
        })