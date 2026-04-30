from decimal import Decimal, InvalidOperation
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
from catalog.models import Product
from inventory.models import StockItem, StockMove

from .models import Sale, SalePayment, SaleLine, SaleTip
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
            .prefetch_related("lines__product", "payments", "tips")
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

        # CRÍTICO (Mario - café Marbrava): el void debe reversar los
        # StockMove ORIGINALES de la venta, no iterar `sale.lines`.
        # Antes: iteraba lines (productos vendidos como "Capuchino") y
        # re-stockeaba el Capuchino → pero create_sale NO descuenta stock
        # del Capuchino sino de los ingredientes (leche, café) tras la
        # expansión de receta. Resultado: cada void de un producto con
        # receta dejaba la leche/café permanentemente faltante e inflaba
        # phantom stock del producto compuesto.
        #
        # Fix: leer los StockMove con ref_type="SALE" y ref_id=sale.id
        # (que ya tienen el producto real — ingrediente o no — y la qty
        # exacta descontada en su momento) y reversarlos uno por uno.
        # Eso garantiza simetría perfecta sin importar si hay receta.
        sale_moves = list(
            StockMove.objects.filter(
                tenant_id=t_id,
                warehouse_id=sale.warehouse_id,
                ref_type="SALE",
                ref_id=sale.id,
            ).only("product_id", "cost_snapshot", "value_delta", "qty")
        )

        moves = []
        total_cost_reversed = Decimal("0.000")

        # Importar helper race-safe (usa savepoint para no romper la
        # transacción externa si hay IntegrityError en la creación).
        from inventory.views import _get_or_create_stockitem_locked

        for m_sale in sale_moves:
            si = _get_or_create_stockitem_locked(
                tenant_id=t_id,
                warehouse_id=sale.warehouse_id,
                product_id=m_sale.product_id,
            )

            # value_delta del SALE es NEGATIVO (qty × cost descontados).
            # Reversamos sumando el valor absoluto al stock_value, y la
            # qty al on_hand. Si el SALE original había clampeado por
            # stock negativo permitido, el value_delta refleja la qty
            # realmente descontada (no la qty solicitada), así que el
            # void revierte exactamente lo mismo.
            qty_to_restore = m_sale.qty
            value_to_restore = abs(Decimal(str(m_sale.value_delta or 0))).quantize(Decimal("0.000"))
            unit_cost = Decimal(str(m_sale.cost_snapshot or 0)).quantize(Decimal("0.000"))

            StockItem.objects.filter(id=si.id).update(
                on_hand=F("on_hand") + qty_to_restore,
                stock_value=F("stock_value") + value_to_restore,
            )

            # IN: value_delta POSITIVO (vuelve al inventario)
            moves.append(
                StockMove(
                    tenant_id=t_id,
                    warehouse_id=sale.warehouse_id,
                    product_id=m_sale.product_id,
                    move_type=StockMove.IN,
                    qty=qty_to_restore,
                    ref_type="SALE_VOID",
                    ref_id=sale.id,
                    note=f"Void sale #{sale.id}",
                    created_by=user,
                    cost_snapshot=unit_cost,
                    value_delta=value_to_restore,
                )
            )

            total_cost_reversed += value_to_restore

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
        # Limpiar también las filas SaleTip relacionales — sin esto el
        # cierre de caja seguiría sumando las propinas de una venta anulada
        # (caen al path "tiene saletips, suma directo"). El flag de status
        # VOID solo se filtra al nivel `sales_in_range` que ya excluye no-COMPLETED,
        # pero para queries directas sobre SaleTip (reportes futuros) la limpieza
        # explícita evita basura.
        SaleTip.objects.filter(sale=sale).delete()
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


class SaleEditPayments(APIView):
    """PATCH /api/sales/sales/<pk>/payments/

    Reemplaza los pagos (SalePayment) de una venta COMPLETED.

    Caso de uso: el cajero registró mal el método (cobró débito y marcó
    efectivo, o viceversa). Solo manager/owner puede corregir.

    Body:
        {"payments": [{"method": "debit", "amount": "10600"}]}

    Validaciones:
    - Sale debe estar COMPLETED (no VOID).
    - Cada method ∈ {cash, card, debit, transfer}.
    - amount > 0.
    - sum(amounts) >= total + tip (no se permite underpayment al editar).

    NOTA: NO modifica `Sale.total` ni stock. Solo cambia cómo se cobró.
    El cierre de caja recalcula breakdown por método porque
    `_session_summary` usa SalePayment en runtime.
    """
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    @transaction.atomic
    def patch(self, request, pk: int):
        t_id = _tenant_id(request)
        s_id = _active_store_id(request)
        if not s_id:
            return Response({"detail": "User has no active_store"}, status=400)

        sale = get_object_or_404(
            Sale.objects.select_for_update(),
            tenant_id=t_id, store_id=s_id, pk=pk,
        )
        if sale.status != Sale.STATUS_COMPLETED:
            return Response(
                {"detail": f"Solo se pueden editar pagos en ventas COMPLETED (estado actual: {sale.status})"},
                status=400,
            )

        payments_in = request.data.get("payments")
        if not isinstance(payments_in, list) or not payments_in:
            return Response({"detail": "payments es requerido y debe ser una lista no vacía"}, status=400)

        valid_methods = {
            SalePayment.METHOD_CASH, SalePayment.METHOD_CARD,
            SalePayment.METHOD_DEBIT, SalePayment.METHOD_TRANSFER,
        }

        # Validar y parsear los pagos nuevos
        parsed = []
        for i, p in enumerate(payments_in):
            method = (p.get("method") or "").strip().lower()
            if method not in valid_methods:
                return Response(
                    {"detail": f"Pago #{i+1}: método inválido '{method}'. Usar: cash/card/debit/transfer"},
                    status=400,
                )
            try:
                amount = Decimal(str(p.get("amount") or 0)).quantize(Decimal("0.01"))
            except (ValueError, ArithmeticError, TypeError, InvalidOperation):
                return Response({"detail": f"Pago #{i+1}: monto inválido"}, status=400)
            if amount <= 0:
                return Response({"detail": f"Pago #{i+1}: monto debe ser mayor a 0"}, status=400)
            parsed.append({"method": method, "amount": amount})

        # Regla simplificada (Daniel 29/04/26): la suma de pagos solo debe
        # cubrir el SUBTOTAL del local. La propina se trata aparte y es
        # libre — el cajero puede registrarla mayor, menor o igual a la
        # diferencia entre pagos y subtotal sin afectar nada del cuadre
        # del local. Caso típico: cliente paga $5000 débito por una
        # cuenta de $3500 y deja $1000 cash de propina; sale.tip=1000 NO
        # tiene por qué encajar matemáticamente con los payments.
        total_paid = sum((p["amount"] for p in parsed), Decimal("0"))
        required = sale.total.quantize(Decimal("0.01"))
        if total_paid < required:
            return Response(
                {"detail": f"Pago insuficiente: {total_paid} < {required} (subtotal de la venta)"},
                status=400,
            )

        # Aplicar: borrar pagos viejos, crear nuevos.
        # En la misma transacción para que no quede inconsistente.
        SalePayment.objects.filter(sale=sale).delete()
        SalePayment.objects.bulk_create([
            SalePayment(
                sale=sale, tenant_id=t_id,
                method=p["method"], amount=p["amount"],
            )
            for p in parsed
        ])

        return Response({
            "id": sale.id,
            "sale_number": sale.sale_number,
            "payments": [{"method": p["method"], "amount": str(p["amount"])} for p in parsed],
            "total_paid": str(total_paid),
        }, status=200)


class SaleEditTip(APIView):
    """PATCH /api/sales/sales/<pk>/tip/

    Actualiza la(s) propina(s) de una venta COMPLETED.

    Body (formato nuevo, split — Daniel 29/04/26):
        {"tips": [
            {"method": "cash",  "amount": "300"},
            {"method": "debit", "amount": "200"},
        ]}

    Body (formato legacy, soportado por compat):
        {"tip": "500", "tip_method": "cash"}        ← se traduce a 1 fila
        {"tip": "500"}                                ← reparto proporcional
                                                       según SalePayments
        {"tip": "0"}                                  ← elimina todas las propinas

    NO modifica `Sale.total` ni `Sale.gross_profit` (la propina siempre
    se trata separada del ingreso del local). Sí afecta el reporte de
    propinas y el breakdown por método.

    Daniel: la propina es libre, NO requiere validación cruzada con los
    pagos. El subtotal del local ya está cubierto al momento de la venta.
    """
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    @transaction.atomic
    def patch(self, request, pk: int):
        t_id = _tenant_id(request)
        s_id = _active_store_id(request)
        if not s_id:
            return Response({"detail": "User has no active_store"}, status=400)

        sale = get_object_or_404(
            Sale.objects.select_for_update(),
            tenant_id=t_id, store_id=s_id, pk=pk,
        )
        if sale.status != Sale.STATUS_COMPLETED:
            return Response(
                {"detail": f"Solo se puede editar propina en ventas COMPLETED (estado: {sale.status})"},
                status=400,
            )

        valid_methods = {
            SalePayment.METHOD_CASH, SalePayment.METHOD_CARD,
            SalePayment.METHOD_DEBIT, SalePayment.METHOD_TRANSFER,
        }

        # Ramificación: nuevo (tips=lista) vs. legacy (tip=monto, tip_method=str).
        tips_in = request.data.get("tips")
        parsed_tips = []  # lista de {"method": str, "amount": Decimal}

        if isinstance(tips_in, list):
            # Formato nuevo split.
            for i, t in enumerate(tips_in):
                method = (t.get("method") or "").strip().lower() if isinstance(t, dict) else ""
                if method not in valid_methods:
                    return Response(
                        {"detail": f"Propina #{i+1}: método inválido '{method}'. Usar: cash/card/debit/transfer"},
                        status=400,
                    )
                try:
                    amount = Decimal(str(t.get("amount") or 0)).quantize(Decimal("0.01"))
                except (ValueError, ArithmeticError, TypeError, InvalidOperation):
                    return Response({"detail": f"Propina #{i+1}: monto inválido"}, status=400)
                if amount < 0:
                    return Response({"detail": f"Propina #{i+1}: monto no puede ser negativo"}, status=400)
                if amount > 0:
                    # Filas con monto 0 simplemente se ignoran (UX: el usuario
                    # puede haber dejado una fila vacía y no quiere persistirla).
                    parsed_tips.append({"method": method, "amount": amount})
        else:
            # Formato legacy: tip + tip_method (single).
            try:
                legacy_tip = Decimal(str(request.data.get("tip", "0"))).quantize(Decimal("0.01"))
            except (ValueError, ArithmeticError, TypeError, InvalidOperation):
                return Response({"detail": "tip debe ser un número"}, status=400)
            if legacy_tip < 0:
                return Response({"detail": "tip no puede ser negativo"}, status=400)

            legacy_method = (request.data.get("tip_method") or "").strip().lower()
            if legacy_method and legacy_method not in valid_methods:
                return Response(
                    {"detail": f"tip_method inválido '{legacy_method}'. Usar: cash/card/debit/transfer o vacío"},
                    status=400,
                )

            if legacy_tip > 0:
                if legacy_method:
                    parsed_tips.append({"method": legacy_method, "amount": legacy_tip})
                else:
                    # Reparto proporcional según SalePayments existentes.
                    payments = list(sale.payments.all().order_by("id"))
                    if not payments:
                        # Sin payments → fallback a cash
                        parsed_tips.append({"method": "cash", "amount": legacy_tip})
                    else:
                        total_paid = sum((p.amount for p in payments), Decimal("0"))
                        if total_paid <= 0:
                            parsed_tips.append({"method": "cash", "amount": legacy_tip})
                        else:
                            running = Decimal("0")
                            for p in payments[:-1]:
                                share = (legacy_tip * p.amount / total_paid).quantize(Decimal("0.01"))
                                if share > 0:
                                    parsed_tips.append({"method": p.method, "amount": share})
                                running += share
                            last = payments[-1]
                            last_share = (legacy_tip - running).quantize(Decimal("0.01"))
                            if last_share > 0:
                                parsed_tips.append({"method": last.method, "amount": last_share})

        # Aplicar: borrar SaleTips viejas, crear nuevas, recalcular Sale.tip
        old_tip = sale.tip
        SaleTip.objects.filter(sale=sale).delete()

        if parsed_tips:
            SaleTip.objects.bulk_create([
                SaleTip(
                    sale=sale, tenant_id=t_id,
                    method=t["method"], amount=t["amount"],
                )
                for t in parsed_tips
            ])

        new_tip_total = sum((t["amount"] for t in parsed_tips), Decimal("0")).quantize(Decimal("0.01"))

        # Actualizar el campo denormalizado Sale.tip + limpiar tip_method
        # (queda obsoleto frente al modelo relacional; ya no se usa para
        # cálculo, pero lo limpiamos para no inducir confusión en lecturas
        # legacy y reportes).
        sale.tip = new_tip_total
        sale.tip_method = ""
        sale.save(update_fields=["tip", "tip_method"])

        return Response({
            "id": sale.id, "sale_number": sale.sale_number,
            "old_tip": str(old_tip),
            "tip": str(new_tip_total),
            "tips": [
                {"method": t["method"], "amount": str(t["amount"])}
                for t in parsed_tips
            ],
        }, status=200)



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
        # Daniel 29/04/26: ahora `SaleTip` es la fuente de verdad. Sumamos
        # directo por método sin reparto proporcional. Compat legacy:
        # ventas con tip>0 y SIN filas SaleTip caen al cálculo histórico.
        method_totals = {}  # method -> {"total": Decimal, "count": int}

        def _bucket(method):
            return method_totals.setdefault(method, {"total": Decimal("0"), "count": 0})

        sale_ids = list(qs.values_list("id", flat=True))
        saletip_rows = (
            SaleTip.objects
            .filter(sale_id__in=sale_ids)
            .values("method")
            .annotate(total=Sum("amount"), count=Count("id"))
        )
        sales_with_saletips = set(
            SaleTip.objects.filter(sale_id__in=sale_ids).values_list("sale_id", flat=True).distinct()
        )
        for r in saletip_rows:
            b = _bucket(r["method"])
            b["total"] += r["total"]
            b["count"] += r["count"]

        legacy_sales = (
            qs.filter(tip__gt=0)
              .exclude(id__in=sales_with_saletips)
              .prefetch_related("payments")
              .only("id", "tip", "tip_method")
        )
        for sale in legacy_sales:
            explicit = (sale.tip_method or "").strip().lower()
            if explicit:
                b = _bucket(explicit)
                b["total"] += sale.tip
                b["count"] += 1
                continue
            payments = list(sale.payments.all())
            if not payments:
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
            last_share = sale.tip - running
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


class TipsListView(APIView):
    """GET /sales/tips-list/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&...

    Lista DETALLADA de propinas (una fila por venta con propina), filtrable
    y paginada. Diseñada para auditoría — Mario lo pidió tipo Fudo:
    "más que gráficos que a veces no dicen nada, una tabla con los registros
    para ver fila por fila quién, cuándo, cuánto, qué método". Cuando hay
    1000 propinas en un mes, la tabla filtrable es mucho más útil que un
    gráfico ilegible.

    Filtros (todos opcionales):
      date_from, date_to     — rango de fechas (default: últimos 30 días)
      cashier_id             — created_by (mesero/cajero)
      payment_method         — cash | debit | card | transfer
      register_id            — caja específica (cash_session.register_id)
      sale_type              — VENTA | CONSUMO_INTERNO (default: solo VENTA)

    Paginación: ?page=1&page_size=50 (default 50, max 500).

    Response:
      {
        "results": [{ ... }],
        "count": int,                    # total filtrado (no de la página)
        "page": int,
        "page_size": int,
        "total_pages": int,
        "totals": {                      # agregados del filtro completo
          "total_tips": "12345",
          "total_sales": "98765",
          "count": 42,
          "avg_tip": "294",
        },
      }
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        from rest_framework.exceptions import ValidationError
        t_id = _tenant_id(request)
        p = request.query_params

        date_from = parse_date(p.get("date_from") or "")
        date_to = parse_date(p.get("date_to") or "")
        if not date_from:
            date_from = (timezone.now() - timedelta(days=30)).date()
        if not date_to:
            date_to = timezone.now().date()

        # Base queryset: ventas COMPLETED con propina > 0 en el rango.
        # CONSUMO_INTERNO no se filtra por defecto (no debería tener tip,
        # pero defensivamente lo dejamos opt-in via sale_type).
        sale_type = (p.get("sale_type") or "VENTA").upper()
        if sale_type not in ("VENTA", "CONSUMO_INTERNO", "ALL"):
            sale_type = "VENTA"

        qs = Sale.objects.filter(
            tenant_id=t_id,
            status=Sale.STATUS_COMPLETED,
            tip__gt=Decimal("0"),
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        if sale_type != "ALL":
            qs = qs.filter(sale_type=sale_type)

        # Filtros opcionales
        cashier_id = p.get("cashier_id")
        if cashier_id and str(cashier_id).isdigit():
            qs = qs.filter(created_by_id=int(cashier_id))

        register_id = p.get("register_id")
        if register_id and str(register_id).isdigit():
            qs = qs.filter(cash_session__register_id=int(register_id))

        payment_method = (p.get("payment_method") or "").strip().lower()
        if payment_method in ("cash", "debit", "card", "transfer"):
            # Una venta queda incluida si TIENE algún pago de ese método.
            # Después en la fila el "método dominante" puede ser otro si la
            # venta es split — eso lo informamos pero filtramos amplio.
            qs = qs.filter(payments__method=payment_method).distinct()

        # Optimización: traer todo en 1 query con joins
        qs = qs.select_related(
            "created_by", "cash_session__register", "open_order__table",
        ).prefetch_related("payments", "tips").order_by("-created_at")

        # Totales del filtro completo (antes de paginar)
        agg = qs.aggregate(
            total_tips=Coalesce(Sum("tip"), Decimal("0")),
            total_sales=Coalesce(Sum("total"), Decimal("0")),
            count=Count("id"),
        )
        avg_tip = (
            (agg["total_tips"] / agg["count"]).quantize(Decimal("1"))
            if agg["count"] else Decimal("0")
        )

        # Paginación (manual con LimitOffset semántica para no depender de
        # DRF Pagination — más control sobre el response shape).
        try:
            page = max(1, int(p.get("page") or 1))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(500, max(1, int(p.get("page_size") or 50)))
        except (ValueError, TypeError):
            page_size = 50

        total_pages = (agg["count"] + page_size - 1) // page_size if agg["count"] else 1
        offset = (page - 1) * page_size
        page_qs = qs[offset:offset + page_size]

        results = []
        for sale in page_qs:
            # Daniel 29/04/26: el método de la PROPINA viene de SaleTip
            # (no de SalePayment). Si hay 1 fila → ese método. Si hay N
            # filas con métodos distintos → "mixed". Compat: si no hay
            # filas SaleTip (legacy), caemos al método dominante de pagos
            # como antes.
            tip_rows = list(sale.tips.all())
            if tip_rows:
                methods_set = {t.method for t in tip_rows}
                if len(methods_set) == 1:
                    method = tip_rows[0].method
                else:
                    method = "mixed"
            else:
                # Legacy: usar tip_method explícito o método dominante de pagos
                explicit = (sale.tip_method or "").strip().lower()
                if explicit:
                    method = explicit
                else:
                    payments = list(sale.payments.all())
                    if not payments:
                        method = "cash"
                    else:
                        payments_sorted = sorted(
                            payments, key=lambda x: (-float(x.amount), x.method)
                        )
                        method = payments_sorted[0].method
                        methods_set = {p.method for p in payments}
                        if len(methods_set) > 1:
                            method = "mixed"

            method_labels = {
                "cash": "Efectivo",
                "debit": "Tarj. Débito",
                "card": "Tarj. Crédito",
                "transfer": "Transferencia",
                "mixed": "Mixto",
            }
            method_label = method_labels.get(method, method.title())

            # Mesa: si la venta vino de mesa, mostrar table.name. Si no,
            # null (POS directo / para llevar). El frontend muestra "—".
            table_name = None
            if sale.open_order_id and getattr(sale.open_order, "table_id", None):
                t = sale.open_order.table
                table_name = getattr(t, "name", None) or getattr(t, "number", None)
                if table_name is not None:
                    table_name = str(table_name)

            # Cajero/garzón: full name → username fallback
            user = sale.created_by
            full_name = " ".join(filter(None, [
                getattr(user, "first_name", "") or "",
                getattr(user, "last_name", "") or "",
            ])).strip()
            cashier_name = full_name or getattr(user, "username", "") or "—"

            # Caja
            register_name = None
            if sale.cash_session_id and sale.cash_session and sale.cash_session.register_id:
                register_name = sale.cash_session.register.name

            results.append({
                "sale_id": sale.id,
                "sale_number": sale.sale_number,
                "created_at": sale.created_at.isoformat(),
                "table_name": table_name,
                "cashier_id": user.id,
                "cashier_name": cashier_name,
                "payment_method": method,
                "payment_method_label": method_label,
                "total_sale": str(sale.total),
                "tip_amount": str(sale.tip),
                # Detalle relacional de propinas (split). Permite al frontend
                # mostrar cada propina como fila separada (Fudo-style).
                "tips": [
                    {"id": t.id, "method": t.method, "amount": str(t.amount)}
                    for t in tip_rows
                ] if tip_rows else [],
                "register_id": sale.cash_session.register_id if sale.cash_session_id else None,
                "register_name": register_name,
                "sale_type": sale.sale_type,
            })

        return Response({
            "results": results,
            "count": agg["count"],
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "totals": {
                "total_tips": str(agg["total_tips"].quantize(Decimal("1"))),
                "total_sales": str(agg["total_sales"].quantize(Decimal("1"))),
                "count": agg["count"],
                "avg_tip": str(avg_tip),
            },
            "filters": {
                "date_from": str(date_from),
                "date_to": str(date_to),
                "cashier_id": int(cashier_id) if cashier_id and str(cashier_id).isdigit() else None,
                "register_id": int(register_id) if register_id and str(register_id).isdigit() else None,
                "payment_method": payment_method or None,
                "sale_type": sale_type,
            },
        })
