# purchases/views.py
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction, IntegrityError
from django.db.models import F, Q
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics
from rest_framework.exceptions import ValidationError

from core.permissions import HasTenant, IsInventoryOrManager
from core.models import Warehouse
from catalog.models import Product
from inventory.models import StockItem, StockMove

from .models import Purchase, PurchaseLine
from .serializers import (
    PurchaseCreateSerializer,
    PurchaseListSerializer,
    PurchaseDetailSerializer,
)

# -----------------------
# helpers (3 decimales)
# -----------------------
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

def _get_store_warehouse_or_409(*, tenant_id: int, store_id: int, warehouse_id: int):
    wh = (
        Warehouse.objects
        .select_related("store")
        .filter(id=warehouse_id, tenant_id=tenant_id, store_id=store_id)
        .first()
    )
    if not wh:
        return None, Response(
            {"detail": "Warehouse does not belong to active store", "store_id": store_id, "warehouse_id": warehouse_id},
            status=status.HTTP_409_CONFLICT,
        )
    return wh, None

def _weighted_avg_cost(old_qty: Decimal, old_avg: Decimal, in_qty: Decimal, in_cost: Decimal) -> Decimal:
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

def _get_or_create_stockitem_locked(*, tenant_id: int, warehouse_id: int, product_id: int) -> StockItem:
    """
    Devuelve StockItem con lock select_for_update.
    Maneja carrera de create por unique constraint.
    (No rompe nada: si ya existe lo bloquea; si no, intenta crearlo.)
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

# ======================================================
# CREATE (DRAFT)
# ======================================================
class PurchaseCreate(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsInventoryOrManager]

    @transaction.atomic
    def post(self, request):
        user = request.user
        t_id = _tenant_id(request)
        store_id = _active_store_id(request)

        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not store_id:
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)

        ser = PurchaseCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        warehouse_id = int(ser.validated_data["warehouse_id"])
        wh, err = _get_store_warehouse_or_409(tenant_id=t_id, store_id=int(store_id), warehouse_id=warehouse_id)
        if err:
            return err

        lines_in = ser.validated_data["lines"]
        supplier_name = (ser.validated_data.get("supplier_name") or "").strip()
        invoice_number = (ser.validated_data.get("invoice_number") or "").strip()
        invoice_date = ser.validated_data.get("invoice_date", None)
        note = (ser.validated_data.get("note") or "").strip()
        tax_amount = ser.validated_data.get("tax_amount", None)
        tax_amount = c3(tax_amount) if tax_amount is not None else Decimal("0.000")

        # productos del tenant
        product_ids = sorted({int(l["product_id"]) for l in lines_in})
        products = set(Product.objects.filter(tenant_id=t_id, id__in=product_ids).values_list("id", flat=True))
        missing = [pid for pid in product_ids if pid not in products]
        if missing:
            return Response({"detail": "Invalid product(s)", "product_ids": missing}, status=status.HTTP_400_BAD_REQUEST)

        # crea purchase DRAFT
        p = Purchase.objects.create(
            tenant_id=t_id,
            store_id=int(store_id),
            warehouse_id=warehouse_id,
            supplier_name=supplier_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            note=note,
            created_by=user,
            status=Purchase.STATUS_DRAFT,
            subtotal_cost=Decimal("0.000"),
            tax_amount=tax_amount,
            total_cost=Decimal("0.000"),
        )

        subtotal_cost = Decimal("0.000")
        lines = []

        # agregamos por producto (por si viene repetido)
        agg = {}  # pid -> {"qty": Decimal, "unit_cost": Decimal, "note": str}
        for l in lines_in:
            pid = int(l["product_id"])
            qty = q3(l["qty"])
            unit_cost = c3(l["unit_cost"])
            ln_note = (l.get("note") or "").strip()

            if pid in agg:
                agg[pid]["qty"] = q3(agg[pid]["qty"] + qty)
                agg[pid]["unit_cost"] = unit_cost  # MVP: último costo
            else:
                agg[pid] = {"qty": qty, "unit_cost": unit_cost, "note": ln_note}

        for pid, data in agg.items():
            qty = data["qty"]
            unit_cost = data["unit_cost"]
            line_total_cost = v3(qty * unit_cost)
            subtotal_cost = v3(subtotal_cost + line_total_cost)

            lines.append(
                PurchaseLine(
                    purchase=p,
                    tenant_id=t_id,
                    product_id=pid,
                    qty=qty,
                    unit_cost=unit_cost,
                    line_total_cost=line_total_cost,
                    note=data.get("note", ""),
                )
            )

        PurchaseLine.objects.bulk_create(lines)

        total_cost = v3(subtotal_cost + tax_amount)
        p.subtotal_cost = subtotal_cost
        p.total_cost = total_cost
        p.save(update_fields=["subtotal_cost", "tax_amount", "total_cost"])

        return Response(
            {"id": p.id, "status": p.status, "store_id": p.store_id, "warehouse_id": p.warehouse_id, "total_cost": str(p.total_cost)},
            status=status.HTTP_201_CREATED,
        )

# ======================================================
# LIST / DETAIL
# ======================================================
class PurchaseList(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasTenant, IsInventoryOrManager]
    serializer_class = PurchaseListSerializer

    def list(self, request, *args, **kwargs):
        if not _active_store_id(request):
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        t_id = _tenant_id(self.request)
        store_id = _active_store_id(self.request)
        if not t_id or not store_id:
            return Purchase.objects.none()

        qs = (
            Purchase.objects.filter(tenant_id=t_id, store_id=int(store_id))
            .select_related("warehouse", "store", "created_by")
            .order_by("-id")
        )

        warehouse_id = (self.request.query_params.get("warehouse_id") or "").strip()
        if warehouse_id.isdigit():
            qs = qs.filter(warehouse_id=int(warehouse_id))

        status_param = (self.request.query_params.get("status") or "").strip().upper()
        if status_param in [Purchase.STATUS_DRAFT, Purchase.STATUS_POSTED, Purchase.STATUS_VOID]:
            qs = qs.filter(status=status_param)

        q = (self.request.query_params.get("q") or "").strip()
        if q:
            # ✅ fix: id__icontains no es ideal (id es int). Si es dígito, filtramos por id exacto.
            if q.isdigit():
                qs = qs.filter(id=int(q))
            else:
                # mantenemos tu lógica original (sin romper), pero aplicada a campos texto
                qs = qs.filter(
                    Q(invoice_number__icontains=q) |
                    Q(supplier_name__icontains=q)
                )

            # (se conserva tu bloque original sin quitarlo; queda redundante pero no rompe)
            qs = qs.filter(
                Q(id__icontains=q) |
                Q(invoice_number__icontains=q) |
                Q(supplier_name__icontains=q)
            )

        date_from = (self.request.query_params.get("from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = (self.request.query_params.get("to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs

class PurchaseDetail(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasTenant, IsInventoryOrManager]
    serializer_class = PurchaseDetailSerializer

    def get_queryset(self):
        t_id = _tenant_id(self.request)
        store_id = _active_store_id(self.request)
        if not t_id or not store_id:
            return Purchase.objects.none()

        return (
            Purchase.objects.filter(tenant_id=t_id, store_id=int(store_id))
            .select_related("warehouse", "store", "created_by")
            .prefetch_related("lines__product")
        )

# ======================================================
# POST (aplica stock + kardex)
# ======================================================
class PurchasePost(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsInventoryOrManager]

    @transaction.atomic
    def post(self, request, pk: int):
        user = request.user
        t_id = _tenant_id(request)
        store_id = _active_store_id(request)

        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not store_id:
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)

        p = get_object_or_404(
            Purchase.objects.select_for_update(),
            tenant_id=t_id,
            store_id=int(store_id),
            pk=pk,
        )

        if p.status == Purchase.STATUS_POSTED:
            return Response({"id": p.id, "status": p.status, "detail": "Purchase already posted"}, status=status.HTTP_200_OK)
        if p.status != Purchase.STATUS_DRAFT:
            return Response({"detail": f"Cannot post purchase with status {p.status}"}, status=status.HTTP_400_BAD_REQUEST)

        # seguridad: warehouse del store activo
        wh, err = _get_store_warehouse_or_409(tenant_id=t_id, store_id=int(store_id), warehouse_id=p.warehouse_id)
        if err:
            return err

        lines = list(p.lines.all())
        if not lines:
            return Response({"detail": "Purchase has no lines"}, status=status.HTTP_400_BAD_REQUEST)

        product_ids = sorted({l.product_id for l in lines})

        # lock de stockitems en orden estable (los existentes)
        stock_items = (
            StockItem.objects.select_for_update()
            .filter(tenant_id=t_id, warehouse_id=p.warehouse_id, product_id__in=product_ids)
        )
        stock_map = {si.product_id: si for si in stock_items}

        moves = []
        # aplicamos cada línea
        for l in lines:
            si = stock_map.get(l.product_id)
            if not si:
                # ✅ fix: create con carrera segura + con lock
                si = _get_or_create_stockitem_locked(
                    tenant_id=t_id,
                    warehouse_id=p.warehouse_id,
                    product_id=l.product_id,
                )
                stock_map[l.product_id] = si

            old_qty = q3(si.on_hand)
            old_avg = c3(si.avg_cost or Decimal("0.000"))
            old_value = v3(si.stock_value or (old_qty * old_avg))

            in_qty = q3(l.qty)
            in_cost = c3(l.unit_cost)
            in_value = v3(in_qty * in_cost)

            new_avg = _weighted_avg_cost(old_qty, old_avg, in_qty, in_cost)
            new_qty = q3(old_qty + in_qty)
            new_value = v3(old_value + in_value)

            StockItem.objects.filter(id=si.id).update(
                on_hand=new_qty,
                avg_cost=new_avg,
                stock_value=new_value,
            )

            moves.append(
                StockMove(
                    tenant_id=t_id,
                    warehouse_id=p.warehouse_id,
                    product_id=l.product_id,
                    move_type=StockMove.IN,
                    qty=in_qty,
                    unit_cost=in_cost,
                    reason="",
                    ref_type="PURCHASE",
                    ref_id=p.id,
                    note=f"Purchase #{p.id}",
                    created_by=user,
                    cost_snapshot=in_cost,
                    value_delta=in_value,
                )
            )

        if moves:
            StockMove.objects.bulk_create(moves)

        # marca posted
        p.status = Purchase.STATUS_POSTED
        p.save(update_fields=["status"])

        # Audit
        from core.models import log_audit
        log_audit(request, "purchase_post", "purchase", p.id,
                  {"warehouse_id": p.warehouse_id, "moves_count": len(moves)})

        return Response({"id": p.id, "status": p.status, "warehouse_id": p.warehouse_id, "moves_count": len(moves)}, status=status.HTTP_200_OK)

# ======================================================
# VOID (revierte stock + kardex)
# ======================================================
class PurchaseVoid(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsInventoryOrManager]

    @transaction.atomic
    def post(self, request, pk: int):
        user = request.user
        t_id = _tenant_id(request)
        store_id = _active_store_id(request)

        if not t_id:
            return Response({"detail": "User must have a tenant."}, status=status.HTTP_400_BAD_REQUEST)
        if not store_id:
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)

        p = get_object_or_404(
            Purchase.objects.select_for_update(),
            tenant_id=t_id,
            store_id=int(store_id),
            pk=pk,
        )

        # ✅ seguridad también en VOID: warehouse del store activo
        wh, err = _get_store_warehouse_or_409(tenant_id=t_id, store_id=int(store_id), warehouse_id=p.warehouse_id)
        if err:
            return err

        # idempotente
        if p.status == Purchase.STATUS_VOID:
            return Response({"id": p.id, "status": p.status, "detail": "Purchase already voided"}, status=status.HTTP_200_OK)

        if p.status != Purchase.STATUS_POSTED:
            return Response({"detail": f"Cannot void purchase with status {p.status} (must be POSTED)"}, status=status.HTTP_400_BAD_REQUEST)

        lines = list(p.lines.all())
        if not lines:
            return Response({"detail": "Purchase has no lines"}, status=status.HTTP_400_BAD_REQUEST)

        product_ids = sorted({l.product_id for l in lines})

        stock_items = (
            StockItem.objects.select_for_update()
            .filter(tenant_id=t_id, warehouse_id=p.warehouse_id, product_id__in=product_ids)
        )
        stock_map = {si.product_id: si for si in stock_items}

        # precheck: no permitir negativo
        shortages = []
        for l in lines:
            si = stock_map.get(l.product_id)
            available = q3(si.on_hand) if si else Decimal("0.000")
            req = q3(l.qty)
            if q3(available - req) < 0:
                shortages.append({"product_id": l.product_id, "available": str(available), "required": str(req)})

        if shortages:
            return Response({"detail": "Cannot void: insufficient stock to revert purchase", "shortages": shortages}, status=status.HTTP_409_CONFLICT)

        moves = []
        for l in lines:
            si = stock_map.get(l.product_id)
            if not si:
                # (no debería pasar por precheck, pero lo dejamos seguro sin romper)
                si = _get_or_create_stockitem_locked(
                    tenant_id=t_id,
                    warehouse_id=p.warehouse_id,
                    product_id=l.product_id,
                )
                stock_map[l.product_id] = si

            out_qty = q3(l.qty)
            cost = c3(l.unit_cost)  # mismo costo de la factura
            out_value = v3(out_qty * cost)

            old_qty = q3(si.on_hand)
            old_value = v3(si.stock_value or Decimal("0.000"))

            new_qty = q3(old_qty - out_qty)
            new_value = v3(old_value - out_value)

            # Defensive: stock value should never go negative. If it does,
            # it indicates data corruption or accumulated rounding errors.
            if new_value < 0:
                logger.warning(
                    "PurchaseVoid: stock_value would go negative for product=%s "
                    "warehouse=%s old_value=%s out_value=%s. Clamping to 0.",
                    l.product_id, p.warehouse_id, old_value, out_value,
                )
                new_value = Decimal("0.000")

            # recalcula avg_cost desde value/qty (simple y consistente)
            if new_qty > 0:
                new_avg = c3(new_value / new_qty)
                # Defensive: avg_cost should never be negative
                if new_avg < 0:
                    logger.warning(
                        "PurchaseVoid: negative avg_cost detected for product=%s. Clamping to 0.",
                        l.product_id,
                    )
                    new_avg = Decimal("0.000")
            else:
                new_avg = Decimal("0.000")
                new_value = Decimal("0.000")  # si qty 0, dejamos valor 0

            StockItem.objects.filter(id=si.id).update(
                on_hand=new_qty,
                avg_cost=new_avg,
                stock_value=new_value,
            )

            moves.append(
                StockMove(
                    tenant_id=t_id,
                    warehouse_id=p.warehouse_id,
                    product_id=l.product_id,
                    move_type=StockMove.OUT,
                    qty=out_qty,
                    unit_cost=None,
                    reason="",
                    ref_type="PURCHASE_VOID",
                    ref_id=p.id,
                    note=f"Void purchase #{p.id}",
                    created_by=user,
                    cost_snapshot=cost,
                    value_delta=-out_value,
                )
            )

        if moves:
            StockMove.objects.bulk_create(moves)

        p.status = Purchase.STATUS_VOID
        p.save(update_fields=["status"])

        # Audit
        from core.models import log_audit
        log_audit(request, "purchase_void", "purchase", p.id,
                  {"moves_count": len(moves)})

        return Response({"id": p.id, "status": p.status, "moves_count": len(moves)}, status=status.HTTP_200_OK)
