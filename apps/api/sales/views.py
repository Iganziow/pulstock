from decimal import Decimal
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.db.models import F, Q, Sum, Count, Avg
from django.db.models.functions import Coalesce, TruncDate
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
    """POS direct sale endpoint.

    NOTA: este endpoint NO acepta `sale_type` desde el cliente — siempre
    crea ventas tipo VENTA (default en `create_sale`). El flow de
    CONSUMO_INTERNO existe solo en `tables/views.py::CheckoutView`
    (mesas), que tiene defensa server-side para tip=0 y payments=[].
    Si en el futuro se permite CONSUMO_INTERNO desde POS directo, hay
    que portar esa misma lógica defensiva aquí.
    """
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

        # Idempotencia: si el cliente envía una clave, respondemos con la
        # venta existente. El filtro debe matchear el UNIQUE constraint
        # del DB (tenant + store + idempotency_key) — antes se filtraba
        # por `created_by=user`, lo que dejaba un agujero: dos cajeros
        # del mismo store reintentando con la misma key entraban a
        # create_sale en vez de hacer early-exit, y la 2ª caía en
        # IntegrityError catch en services.py:242. Funcionaba pero
        # generaba doble query y log ruidoso. Lo más importante: el
        # response anterior NO incluía `tip`, así que el frontend al
        # imprimir la boleta del retry no podía mostrar la propina.
        idempotency_key = (request.data.get("idempotency_key") or "").strip()[:64]
        if idempotency_key:
            existing = Sale.objects.filter(
                tenant_id=t_id, store_id=store_id, idempotency_key=idempotency_key,
            ).first()
            if existing:
                return Response(
                    {
                        "id": existing.id,
                        "sale_number": existing.sale_number,
                        "store_id": existing.store_id,
                        "warehouse_id": existing.warehouse_id,
                        "total": str(existing.total),
                        "tip": str(existing.tip),
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

        lines = list(sale.lines.select_for_update().all())

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
            # Importar helper race-safe (usa savepoint para no romper la
            # transacción externa si hay IntegrityError en la creación)
            from inventory.views import _get_or_create_stockitem_locked
            si = _get_or_create_stockitem_locked(
                tenant_id=t_id,
                warehouse_id=sale.warehouse_id,
                product_id=l.product_id,
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
        # Trazabilidad: al anular, costo y profit a 0 (la línea no afecta
        # margen). Guardamos el tip ORIGINAL en el audit para que Mario
        # pueda saber cuánto era si necesita reconstruir, y lo limpiamos
        # a 0 para que no aparezca en reportes de propinas / desglose
        # por método. Sin esto, una venta anulada seguía contando su
        # propina en queries que filtraran por `tip__gt=0` sin status.
        original_tip = sale.tip
        sale.total_cost = Decimal("0.000")
        sale.gross_profit = Decimal("0.000")
        sale.tip = Decimal("0.00")
        update_fields = ["status", "total_cost", "gross_profit", "tip"]
        if _model_has_field(Sale, "unit_cost_snapshot"):
            sale.unit_cost_snapshot = Decimal("0.000")
            update_fields.append("unit_cost_snapshot")
        sale.save(update_fields=update_fields)

        # Audit
        from core.models import log_audit
        log_audit(request, "sale_void", "sale", sale.id, {
            "lines": len(lines),
            "reversed_cost": str(total_cost_reversed),
            "original_tip": str(original_tip),
        })

        return Response(
            {"id": sale.id, "status": sale.status, "lines_count": len(lines), "reversed_cost": str(total_cost_reversed)},
            status=status.HTTP_200_OK,
        )


class TipsSummaryView(APIView):
    """GET /sales/tips-summary/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

    Returns aggregate tip statistics for the tenant in the given date range.
    Defaults to the last 30 days if no params are provided.

    Las propinas se tratan SIEMPRE separadas de las ganancias del local —
    pertenecen al equipo (mesero/cajero), no al negocio. Por eso este endpoint
    es independiente y no se mezcla con los reportes de ingresos/utilidad.

    Devuelve:
      - total_tips, count_with_tip, avg_tip  (resumen)
      - by_day:    [{date, total, count}]    (serie temporal para gráfico)
      - by_cashier:[{user_id, name, total, count}] (para repartir entre el equipo)
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

        # Breakdown por día — solo días con propinas (los demás no aportan
        # información útil en el gráfico).
        by_day_qs = (
            qs.filter(tip__gt=0)
              .annotate(day=TruncDate("created_at"))
              .values("day")
              .annotate(total=Sum("tip"), count=Count("id"))
              .order_by("day")
        )
        by_day = [
            {"date": str(r["day"]), "total": str(r["total"].quantize(Decimal("1"))), "count": r["count"]}
            for r in by_day_qs
        ]

        # Breakdown por cajero (created_by). Útil para que el dueño reparta
        # las propinas entre quienes las generaron.
        by_cashier_qs = (
            qs.filter(tip__gt=0)
              .values("created_by_id", "created_by__first_name", "created_by__last_name", "created_by__username")
              .annotate(total=Sum("tip"), count=Count("id"))
              .order_by("-total")
        )
        by_cashier = []
        for r in by_cashier_qs:
            full_name = " ".join(filter(None, [r.get("created_by__first_name"), r.get("created_by__last_name")])).strip()
            name = full_name or r.get("created_by__username") or "Desconocido"
            by_cashier.append({
                "user_id": r["created_by_id"],
                "name":    name,
                "total":   str(r["total"].quantize(Decimal("1"))),
                "count":   r["count"],
            })

        # Breakdown por MÉTODO DE PAGO. Mario quiere ver "cuanto hicieron
        # divididos en débito, crédito, efectivo, etc." porque cada método
        # llega a la caja por canales distintos (débito/crédito al banco,
        # efectivo a mano).
        #
        # Repartición proporcional cuando hay múltiples pagos en una venta:
        # si una venta de $8.000 + $1.000 propina se pagó con $5.000 cash
        # + $3.000 card, atribuimos al cash 1000×5/8 = $625 y al card $375.
        # Para el caso típico de cafetería (1 método por venta) coincide
        # con 100% al método dominante.
        #
        # IMPORTANTE: la última fila absorbe el resto del redondeo, así
        # la suma de by_payment_method = total_tips (headline) exacto.
        # Sin esto, propinas como $1.000 split en 3 pagos iguales daban
        # 333+333+333 = 999 ≠ 1.000 y Mario veía "discrepancia".
        method_totals = {}  # method -> {"total": Decimal, "count": int}

        def _bucket(method):
            return method_totals.setdefault(method, {"total": Decimal("0"), "count": 0})

        sales_with_tips = (
            qs.filter(tip__gt=0)
              .prefetch_related("payments")
              .only("id", "tip", "total")
        )
        for sale in sales_with_tips:
            payments = list(sale.payments.all())
            if not payments:
                # Tip sin payments — atribuir a "cash" por defecto.
                # Caso raro (datos legacy) pero evita descuadre con headline.
                b = _bucket("cash")
                b["total"] += sale.tip
                b["count"] += 1
                continue
            total_paid = sum((p.amount for p in payments), Decimal("0"))
            if total_paid <= 0:
                continue
            running = Decimal("0")
            for p in payments[:-1]:
                share = (sale.tip * p.amount / total_paid).quantize(Decimal("1"))
                b = _bucket(p.method)
                b["total"] += share
                b["count"] += 1
                running += share
            last = payments[-1]
            last_share = sale.tip - running  # absorbe el redondeo
            b = _bucket(last.method)
            if last_share > 0:
                b["total"] += last_share
                b["count"] += 1

        # Etiquetas amigables para el frontend (es-CL).
        method_labels = {
            "cash":     "Efectivo",
            "card":     "Crédito",
            "debit":    "Débito",
            "transfer": "Transferencia",
        }
        by_payment_method = sorted(
            [
                {
                    "method":  m,
                    "label":   method_labels.get(m, m.title()),
                    "total":   str(v["total"]),
                    "count":   v["count"],
                }
                for m, v in method_totals.items()
            ],
            key=lambda x: -float(x["total"]),
        )

        return Response({
            "date_from":         str(date_from),
            "date_to":           str(date_to),
            "total_tips":        str(agg["total_tips"].quantize(Decimal("1"))),
            "count_with_tip":    agg["count_with_tip"],
            "avg_tip":           str(agg["avg_tip"].quantize(Decimal("1"))),
            "by_day":            by_day,
            "by_cashier":        by_cashier,
            "by_payment_method": by_payment_method,
        })
