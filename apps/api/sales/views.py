from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q, Sum, Count, Avg
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, generics

from core.permissions import HasTenant, IsManager
from core.models import Warehouse
from inventory.models import StockItem, StockMove

from .models import Sale, SalePayment
from .serializers import (
    SaleCreateSerializer,
    SaleDetailSerializer,
    SaleListSerializer,
)
from .services import create_sale, SaleValidationError, StockShortageError


def _tenant_id(request):
    return getattr(request.user, "tenant_id", None)


def _active_store_id(request):
    return getattr(request.user, "active_store_id", None)


def _model_has_field(model_cls, field_name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == field_name for f in model_cls._meta.get_fields())
    except (AttributeError, LookupError):
        return False


class SaleCreate(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        user = request.user
        t_id = _tenant_id(request)
        store_id = _active_store_id(request)

        if not store_id:
            return Response(
                {"detail": "User has no active_store"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Idempotencia: si el cliente envía una clave, respondemos con la venta existente
        idempotency_key = (request.data.get("idempotency_key") or "").strip()[:64]
        if idempotency_key:
            existing = Sale.objects.filter(
                tenant_id=t_id, idempotency_key=idempotency_key, created_by=user
            ).first()
            if existing:
                return Response(
                    {
                        "id": existing.id,
                        "sale_number": existing.sale_number,
                        "store_id": existing.store_id,
                        "warehouse_id": existing.warehouse_id,
                        "total": str(existing.total),
                        "total_cost": str(existing.total_cost),
                        "gross_profit": str(existing.gross_profit),
                        "lines_count": existing.lines.count(),
                        "payment_warning": None,
                        "idempotent": True,
                    },
                    status=status.HTTP_201_CREATED,
                )

        ser = SaleCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        warehouse_id = ser.validated_data["warehouse_id"]
        lines_in = ser.validated_data["lines"]
        payments_in = request.data.get("payments") or []
        from api.utils import safe_decimal
        tip = safe_decimal(request.data.get("tip"), Decimal("0"))

        g_discount_type = ser.validated_data.get("global_discount_type", "none") or "none"
        g_discount_value = ser.validated_data.get("global_discount_value", Decimal("0")) or Decimal("0")

        try:
            result = create_sale(
                user=user,
                tenant_id=t_id,
                store_id=store_id,
                warehouse_id=warehouse_id,
                lines_in=lines_in,
                payments_in=payments_in,
                idempotency_key=idempotency_key,
                tip=tip,
                global_discount_type=g_discount_type,
                global_discount_value=Decimal(str(g_discount_value)),
            )
        except SaleValidationError as exc:
            return Response(exc.detail, status=exc.status_code)
        except StockShortageError as exc:
            return Response(
                {"detail": "Insufficient stock", "shortages": exc.shortages},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {k: v for k, v in result.items() if k != "sale"},
            status=status.HTTP_201_CREATED,
        )


class SaleList(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = SaleListSerializer

    def list(self, request, *args, **kwargs):
        store_id = _active_store_id(request)
        if not store_id:
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        t_id = getattr(user, "tenant_id", None)
        store_id = getattr(user, "active_store_id", None)

        if not t_id or not store_id:
            return Sale.objects.none()

        SORT_MAP = {
            "id": "id", "date": "created_at", "total": "total",
            "number": "sale_number", "cost": "total_cost",
        }
        sort_field = SORT_MAP.get(
            (self.request.query_params.get("sort") or "").strip().lower(), "id"
        )
        order = (self.request.query_params.get("order") or "desc").strip().lower()
        ordering = sort_field if order == "asc" else f"-{sort_field}"

        qs = (
            Sale.objects.filter(
                tenant_id=t_id,
                store_id=store_id,
            )
            .select_related("warehouse", "created_by", "store", "open_order__table")
            .order_by(ordering)
        )

        warehouse_id = (self.request.query_params.get("warehouse_id") or "").strip()
        if warehouse_id.isdigit():
            qs = qs.filter(warehouse_id=int(warehouse_id))

        q = (self.request.query_params.get("q") or "").strip()
        if q.isdigit():
            qs = qs.filter(Q(id=int(q)) | Q(sale_number=int(q)))

        status_param = (self.request.query_params.get("status") or "").strip()
        if status_param:
            qs = qs.filter(status=status_param)

        date_from = (self.request.query_params.get("from") or "").strip()
        if not date_from:
            date_from = (self.request.query_params.get("date_from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = (self.request.query_params.get("to") or "").strip()
        if not date_to:
            date_to = (self.request.query_params.get("date_to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        sale_type_param = (self.request.query_params.get("sale_type") or "").strip()
        if sale_type_param:
            qs = qs.filter(sale_type=sale_type_param)

        return qs


class SaleDetail(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = SaleDetailSerializer

    def get_queryset(self):
        t_id = _tenant_id(self.request)
        store_id = _active_store_id(self.request)

        if not store_id:
            return Sale.objects.none()

        return (
            Sale.objects.filter(
                tenant_id=t_id,
                store_id=store_id,
            )
            .select_related("warehouse", "created_by", "store")
            .prefetch_related("lines__product", "payments")
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Pre-cargar StockMoves en bulk para evitar N+1 en el serializer
        moves_qs = StockMove.objects.filter(
            ref_type="SALE", ref_id=instance.id,
        ).only("product_id", "cost_snapshot", "value_delta", "qty")
        moves_map = {int(m.product_id): m for m in moves_qs}

        serializer = self.get_serializer(
            instance,
            context={**self.get_serializer_context(), "sale_moves_map": moves_map},
        )
        return Response(serializer.data)


class SaleVoid(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    @transaction.atomic
    def post(self, request, pk: int):
        user = request.user
        t_id = _tenant_id(request)
        store_id = _active_store_id(request)

        if not store_id:
            return Response({"detail": "User has no active_store"}, status=status.HTTP_400_BAD_REQUEST)

        # Lock de la venta para evitar doble void concurrente + store-aware
        sale = get_object_or_404(
            Sale.objects.select_for_update(),
            tenant_id=t_id,
            store_id=store_id,  # ✅ store-aware
            pk=pk,
        )

        # Idempotencia: si ya está anulada, responde OK sin repetir movimientos
        if sale.status == "VOID":
            return Response(
                {"id": sale.id, "status": sale.status, "detail": "Sale already voided"},
                status=status.HTTP_200_OK,
            )

        if sale.status != "COMPLETED":
            return Response(
                {"detail": f"Cannot void sale with status {sale.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Seguridad extra: la bodega de la venta debe ser del store activo
        ok_wh = Warehouse.objects.filter(
            id=sale.warehouse_id,
            tenant_id=t_id,
            store_id=store_id,
        ).exists()
        if not ok_wh:
            return Response(
                {"detail": "Sale warehouse does not belong to active store"},
                status=status.HTTP_409_CONFLICT,
            )

        lines = list(sale.lines.all())

        # traemos los moves SALE para recuperar el costo real que usamos al vender
        sale_moves = {
            int(m.product_id): m
            for m in StockMove.objects.filter(
                tenant_id=t_id,
                warehouse_id=sale.warehouse_id,
                ref_type="SALE",
                ref_id=sale.id,
            ).only("product_id", "cost_snapshot", "value_delta", "qty")
        }

        moves = []
        total_cost_reversed = Decimal("0.000")

        for l in lines:
            si, _ = StockItem.objects.select_for_update().get_or_create(
                tenant_id=t_id,
                warehouse_id=sale.warehouse_id,
                product_id=l.product_id,
                defaults={"on_hand": Decimal("0.000"), "avg_cost": Decimal("0.000"), "stock_value": Decimal("0.000")},
            )

            m_sale = sale_moves.get(int(l.product_id))
            unit_cost = Decimal("0.000")
            if m_sale and m_sale.cost_snapshot is not None:
                unit_cost = Decimal(str(m_sale.cost_snapshot)).quantize(Decimal("0.000"))

            line_cost = (l.qty * unit_cost).quantize(Decimal("0.000"))

            # devolver stock y valor al inventario
            StockItem.objects.filter(id=si.id).update(
                on_hand=F("on_hand") + l.qty,
                stock_value=F("stock_value") + line_cost,
            )

            # IN: value_delta POSITIVO (vuelve al inventario)
            moves.append(
                StockMove(
                    tenant_id=t_id,
                    warehouse_id=sale.warehouse_id,
                    product_id=l.product_id,
                    move_type=StockMove.IN,
                    qty=l.qty,
                    ref_type="SALE_VOID",
                    ref_id=sale.id,
                    note=f"Void sale #{sale.id}",
                    created_by=user,
                    cost_snapshot=unit_cost,
                    value_delta=line_cost,
                )
            )

            total_cost_reversed += line_cost

        if moves:
            StockMove.objects.bulk_create(moves)

        sale.status = "VOID"
        # dejamos trazabilidad: al anular, costo y profit a 0 (o puedes mantenerlos y sólo marcar VOID)
        sale.total_cost = Decimal("0.000")
        sale.gross_profit = Decimal("0.000")
        if _model_has_field(Sale, "unit_cost_snapshot"):
            sale.unit_cost_snapshot = Decimal("0.000")

            sale.save(update_fields=["status", "total_cost", "gross_profit", "unit_cost_snapshot"])
        else:
            sale.save(update_fields=["status", "total_cost", "gross_profit"])

        # Audit
        from core.models import log_audit
        log_audit(request, "sale_void", "sale", sale.id,
                  {"lines": len(lines), "reversed_cost": str(total_cost_reversed)})

        return Response(
            {"id": sale.id, "status": sale.status, "lines_count": len(lines), "reversed_cost": str(total_cost_reversed)},
            status=status.HTTP_200_OK,
        )


class TipsSummaryView(APIView):
    """GET /sales/tips-summary/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

    Returns aggregate tip statistics for the tenant in the given date range.
    Defaults to the last 30 days if no params are provided.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _tenant_id(request)

        date_from = parse_date(request.query_params.get("date_from") or "")
        date_to   = parse_date(request.query_params.get("date_to") or "")

        if not date_from:
            date_from = (timezone.now() - timedelta(days=30)).date()
        if not date_to:
            date_to = timezone.now().date()

        qs = Sale.objects.filter(
            tenant_id=t_id,
            status=Sale.STATUS_COMPLETED,
            sale_type=Sale.SALE_TYPE_VENTA,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )

        agg = qs.aggregate(
            total_tips=Coalesce(Sum("tip"), Decimal("0")),
            count_with_tip=Count("id", filter=Q(tip__gt=0)),
            avg_tip=Coalesce(Avg("tip", filter=Q(tip__gt=0)), Decimal("0")),
        )

        return Response({
            "date_from":      str(date_from),
            "date_to":        str(date_to),
            "total_tips":     str(agg["total_tips"].quantize(Decimal("1"))),
            "count_with_tip": agg["count_with_tip"],
            "avg_tip":        str(agg["avg_tip"].quantize(Decimal("1"))),
        })
