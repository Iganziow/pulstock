"""
caja/views.py — Cash register management API
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.permissions import HasTenant

from .models import CashRegister, CashSession, CashMovement

logger = logging.getLogger(__name__)


def _t(request):
    return getattr(request.user, "tenant_id", None)

def _s(request):
    return getattr(request.user, "active_store_id", None)


def _sales_in_session_range(session):
    """
    Devuelve QuerySet de Sales que pertenecen a esta sesión POR RANGO TEMPORAL,
    no por FK cash_session_id.

    ANTES (bug reportado por Daniel 29/04/26): el cierre filtraba ventas por
    `sale.cash_session_id == session.id`. Si una venta se hacía con la caja
    cerrada (cash_session=NULL), nunca aparecía en NINGÚN cierre →
    Marbrava 27-abr tenía $6.764 en propinas huérfanas que el dueño no veía.
    Daniel: "el cierre tiene que vizualizar TODO no solo del usuario que abre
    la caja, ¿cómo van a cuadrar si no se muestra todo lo del día?".

    RANGO TEMPORAL CALCULADO:
      - end_dt   = session.closed_at o ahora (si sigue OPEN).
      - start_dt = closed_at de la SESIÓN ANTERIOR cerrada (mismo store), o
                   el inicio del día local de opened_at si no hay anterior.

    Esto cubre el caso típico de Marbrava: el dueño abrió la caja a las
    17:26 después de 6 horas operando con caja cerrada. Las ventas de
    11:24-17:13 quedaron huérfanas. Con el rango extendido, el cierre de
    esa sesión absorbe TODO el día (porque no hay sesión anterior). Si
    después abren otra sesión, la siguiente empezará desde el cierre de
    ésta, sin doble contar.

    Toda venta del store en el rango cuenta, sin importar si tiene
    cash_session asignado o quién la cobró.
    """
    from datetime import datetime, time as dt_time
    from sales.models import Sale

    end_dt = session.closed_at or timezone.now()

    # Buscar la sesión cerrada anterior CON ACTIVIDAD REAL (ventas o
    # movimientos manuales). Sin esto, una sesión-fantasma de 7 minutos
    # que se abrió y cerró por error "reservaba" un período temporal y
    # bloqueaba que la sesión real absorbiera las huérfanas.
    #
    # Caso real Marbrava 27-abr: Mario abrió la caja 21:19, la cerró
    # 21:26 sin vender nada. Después Ignacia abrió 21:26 y vendió hasta
    # 01:23. Las 8 ventas previas del día (huérfanas) deberían entrar al
    # cierre de Ignacia, no quedar atrapadas en la sesión vacía de Mario.
    #
    # Limitamos la búsqueda a las últimas 10 sesiones para no degradar
    # performance — más que suficiente para cualquier caso real.
    prev_closed = None
    # __lte: incluye prev_closed con closed_at == session.opened_at
    # (caso: Ignacia abre exactamente cuando Mario cierra). Sin esto,
    # el boundary __gt no aplica y la venta del segundo entra a las dos.
    candidates = CashSession.objects.filter(
        tenant_id=session.tenant_id,
        store_id=session.store_id,
        status=CashSession.STATUS_CLOSED,
        closed_at__lte=session.opened_at,
    ).exclude(id=session.id).order_by("-closed_at")[:10]

    for pc in candidates:
        # Actividad = ventas con FK a esta sesión O movimientos manuales.
        # Usamos FK directo (no rango temporal) para evitar circularidad:
        # si chequeáramos por rango, las huérfanas que ya están en la
        # sesión-fantasma cuentan como "actividad" y nunca se libera.
        from sales.models import Sale
        has_sales = Sale.objects.filter(
            cash_session_id=pc.id, status="COMPLETED",
        ).exists()
        has_movs = pc.movements.exists()
        if has_sales or has_movs:
            prev_closed = pc
            break

    if prev_closed and prev_closed.closed_at:
        # Empezar desde el cierre anterior con actividad — captura el gap.
        start_dt = prev_closed.closed_at
    else:
        # Sin sesión cerrada previa con actividad: extender hasta el
        # inicio del día local de opened_at. Esto absorbe huérfanas de
        # la mañana cuando la caja se abrió tarde, ignorando sesiones
        # fantasma vacías. Caso Marbrava 27-abr.
        local_tz = timezone.get_current_timezone()
        opened_local = session.opened_at.astimezone(local_tz)
        start_of_day_naive = datetime.combine(opened_local.date(), dt_time(0, 0))
        start_dt = timezone.make_aware(start_of_day_naive, local_tz)

    # Defensivo: nunca exceder opened_at hacia adelante (no perderíamos
    # ventas POSTERIORES al opened_at, esas siempre entran).
    if start_dt > session.opened_at:
        start_dt = session.opened_at

    # BOUNDARY (Daniel 29/04/26 — sesiones consecutivas):
    # - end_dt: usamos __lte para incluir ventas con created_at idéntico
    #   al cierre (caso edge Windows: baja resolución de reloj hace que
    #   `Sale.create(default=now())` y `end_dt = now()` coincidan).
    # - start_dt: si viene de prev_closed.closed_at, usamos __gt
    #   (estrictamente mayor) para evitar DOBLE CONTEO cuando dos
    #   sesiones se solapan en el mismo timestamp. Ej: Mario cierra
    #   12:00:00, Ignacia abre 12:00:00 (mismo segundo), una venta hecha
    #   12:00:00 entraría a las dos sesiones si usamos __gte.
    #   Si start_dt viene del inicio del día (no hay prev_closed), no
    #   hay riesgo de solapamiento → usamos __gte normal.
    use_gt_start = prev_closed is not None and prev_closed.closed_at is not None
    qs = Sale.objects.filter(
        tenant_id=session.tenant_id,
        store_id=session.store_id,
        status="COMPLETED",
        sale_type="VENTA",
        created_at__lte=end_dt,
    )
    if use_gt_start:
        qs = qs.filter(created_at__gt=start_dt)
    else:
        qs = qs.filter(created_at__gte=start_dt)
    return qs


def _session_summary(session):
    """Compute live expected_cash and payment breakdown.

    Suma TODAS las ventas del store en el rango temporal de la sesión, no
    solo las que tienen FK cash_session=session. Ver `_sales_in_session_range`
    para el contexto del fix.
    """
    from sales.models import SalePayment

    sales_in_range = _sales_in_session_range(session)
    sale_ids_in_range = list(sales_in_range.values_list("id", flat=True))

    # Single query: GROUP BY method → {method: total}.
    # NOTA: SalePayment.amount cubre el TOTAL pagado (subtotal + propina),
    # porque en el flujo del PaymentModal el cajero pone el monto que
    # cobra al cliente, que ya incluye la propina si la hubo. Por lo
    # tanto method_totals[method] incluye las propinas.
    method_totals = dict(
        SalePayment.objects.filter(
            sale_id__in=sale_ids_in_range,
        ).values_list("method").annotate(total=Sum("amount")).values_list("method", "total")
    )
    zero = Decimal("0")
    # Pagos brutos por método (incluyen propinas). Usados para
    # expected_cash. Los display _sales se calculan más abajo restando
    # las propinas para no duplicar números en el frontend.
    cash_payments_total     = method_totals.get("cash", zero) or zero
    debit_payments_total    = method_totals.get("debit", zero) or zero
    card_payments_total     = method_totals.get("card", zero) or zero
    transfer_payments_total = method_totals.get("transfer", zero) or zero

    # Propinas POR método de pago (Mario lo pidió: "los chicos quieren ver
    # cuánto va de propina por débito/crédito/efectivo durante el turno").
    # Distribución proporcional cuando hay split: si pagó $5000 cash + $3000
    # card con $1000 propina, atribuye $625 a cash y $375 a card.
    #
    # IMPORTANTE para reconciliación: la última fila absorbe el resto del
    # redondeo, así que la suma de tips_by_method = sale.tip exacto.
    # Sin esto, una propina de $1.000 dividida en 3 pagos iguales daría
    # 333+333+333 = 999, y el total no cuadraría con el headline.
    tips_by_method = {"cash": zero, "debit": zero, "card": zero, "transfer": zero}
    tip_count_by_method = {"cash": 0, "debit": 0, "card": 0, "transfer": 0}

    def _bucket(method):
        # Si llega un método nuevo (ej: mercadopago en el futuro), se
        # crea el bucket on-the-fly en vez de descartar el share.
        if method not in tips_by_method:
            tips_by_method[method] = zero
            tip_count_by_method[method] = 0
        return method

    # Mismo cambio que arriba: usar rango temporal en vez de FK.
    # Daniel 29/04/26: ahora `SaleTip` es la fuente de verdad. Cada venta
    # con propina tiene N filas {method, amount}. Sumamos directo por método
    # — sin reparto proporcional, sin redondeo, sin tip_method.
    #
    # Compat legacy: si una venta tiene Sale.tip > 0 pero NO filas SaleTip
    # (datos previos al refactor que la migración no haya tocado, p.ej.
    # ventas creadas en una transacción con la migración corriendo en otro
    # nodo), caemos al cálculo histórico (tip_method explícito o reparto
    # proporcional). En la práctica la migración ya creó las filas para
    # todas las ventas existentes; este path es solo defensivo.
    from sales.models import SaleTip

    saletip_totals = (
        SaleTip.objects
        .filter(sale_id__in=sale_ids_in_range)
        .values("method")
        .annotate(total=Sum("amount"), count=Count("id"))
    )
    sales_with_saletips = set(
        SaleTip.objects
        .filter(sale_id__in=sale_ids_in_range)
        .values_list("sale_id", flat=True)
        .distinct()
    )
    for row in saletip_totals:
        m = _bucket(row["method"])
        tips_by_method[m] += row["total"]
        tip_count_by_method[m] += row["count"]

    # Path legacy para ventas con tip>0 pero sin filas SaleTip
    legacy_sales = sales_in_range.filter(
        tip__gt=0,
    ).exclude(id__in=sales_with_saletips).prefetch_related("payments")
    for sale in legacy_sales:
        explicit_method = (sale.tip_method or "").strip().lower()
        if explicit_method:
            m = _bucket(explicit_method)
            tips_by_method[m] += sale.tip
            tip_count_by_method[m] += 1
            continue

        payments = list(sale.payments.all())
        if not payments:
            tips_by_method["cash"] += sale.tip
            tip_count_by_method["cash"] += 1
            continue
        total_paid = sum((p.amount for p in payments), zero)
        if total_paid <= 0:
            continue
        running = zero
        for p in payments[:-1]:
            share = (sale.tip * p.amount / total_paid).quantize(Decimal("1"))
            m = _bucket(p.method)
            tips_by_method[m] += share
            tip_count_by_method[m] += 1
            running += share
        last = payments[-1]
        last_share = sale.tip - running
        m = _bucket(last.method)
        if last_share > 0:
            tips_by_method[m] += last_share
            tip_count_by_method[m] += 1

    # Single query for movements: GROUP BY type
    mov_totals = dict(
        session.movements.values_list("type").annotate(total=Sum("amount")).values_list("type", "total")
    )
    movements_in  = mov_totals.get("IN", zero) or zero
    movements_out = mov_totals.get("OUT", zero) or zero

    # BUG FIX (Mario reportó 27/04/26): la caja no cuadraba al cierre
    # porque cash_tips se sumaba a expected_cash, pero las propinas YA
    # estaban incluidas en cash_payments_total (porque SalePayment.amount
    # cubre subtotal + propina). Doble suma → caja esperaba $2.137 más
    # de los que había → al cerrar faltaban esos $2.137.
    #
    # Y un segundo problema relacionado: cash_tips sumaba propinas de
    # TODOS los métodos (incluso débito/crédito), no solo cash. Si la
    # propina iba por tarjeta, igual aparecía como "propina en efectivo".
    #
    # Fix completo:
    # - cash_tips = solo las propinas pagadas en efectivo.
    # - Display _sales = pagos brutos − propinas → "ventas netas" sin
    #   duplicar lo que ya está en el widget de propinas.
    # - expected_cash usa cash_payments_total (que ya incluye todo el
    #   efectivo físico que entró: ventas + propinas en cash).
    #   Eso es matemáticamente equivalente a fondo + cash_sales_neto +
    #   cash_tips + movs, pero evita el riesgo de doble suma.
    cash_tips     = tips_by_method.get("cash", zero)
    debit_tips    = tips_by_method.get("debit", zero)
    card_tips     = tips_by_method.get("card", zero)
    transfer_tips = tips_by_method.get("transfer", zero)
    total_tips    = sum(tips_by_method.values(), zero)

    # Display: ventas NETAS (sin propinas) por método. La propina se
    # muestra aparte en el widget "Propinas del turno".
    #
    # CASO EDGE (Daniel 29/04/26 — split tips relacional): si la propina
    # de un método X excede los payments del mismo método X, restar daría
    # negativo (ej. cliente pagó cash $4.000 con tip $500, después dueño
    # editó tip a "$200 transferencia + $300 cash" → payments siguen
    # cash, pero tip transferencia $200 no tiene payment respaldo).
    # Clamp a 0 para no mostrar -$200 al usuario. El exceso es propina
    # "fuera de banda" (cliente la entregó por canal distinto al pago) y
    # se ve correctamente en el widget de propinas.
    cash_sales     = max(zero, cash_payments_total     - cash_tips)
    debit_sales    = max(zero, debit_payments_total    - debit_tips)
    card_sales     = max(zero, card_payments_total     - card_tips)
    transfer_sales = max(zero, transfer_payments_total - transfer_tips)

    # total_sales: usar el subtotal real de las ventas en rango, NO la suma
    # de los _sales por método. Razón: con split tips libres puede haber
    # inconsistencia entre tips_by_method y payments_by_method (ej. tip
    # transferencia $200 sin payment de transferencia → clamped a 0). El
    # subtotal real (Sale.total agregado) sigue siendo la fuente de verdad
    # de cuánto vendió el local.
    total_sales = sales_in_range.aggregate(
        s=Coalesce(Sum("total"), zero),
    )["s"]

    # expected_cash usa el total pagado en efectivo directo (ya incluye
    # propinas en cash). Esto evita la doble suma del bug original.
    #
    # NOTA edge case split tips: si la propina cash declarada excede
    # los payments cash, ese exceso es cash adicional que entró por fuera
    # del payment registrado. Lo sumamos a expected_cash para que el
    # cuadre refleje el cash físico real esperado en caja.
    extra_cash_from_tips = max(zero, cash_tips - cash_payments_total)
    expected = session.initial_amount + cash_payments_total + extra_cash_from_tips + movements_in - movements_out
    return {
        "initial_amount":  str(session.initial_amount),
        # Desglose por método de pago (ventas netas, sin propinas)
        "cash_sales":      str(cash_sales),
        "debit_sales":     str(debit_sales),
        "card_sales":      str(card_sales),
        "transfer_sales":  str(transfer_sales),
        "total_sales":     str(total_sales),
        # Propinas: cash_tips = SOLO las pagadas en efectivo (informativo
        # para el flujo de caja). total_tips = todas las propinas.
        # tips_by_method = desglose para que los chicos vean cuánto les
        # llegó por cada canal.
        "cash_tips":       str(cash_tips),
        "total_tips":      str(total_tips),
        "tips_by_method":  {k: str(v) for k, v in tips_by_method.items()},
        "tip_count_by_method": tip_count_by_method,
        # Flujo de caja (efectivo físico)
        "movements_in":    str(movements_in),
        "movements_out":   str(movements_out),
        "expected_cash":   str(expected.quantize(Decimal("0.01"))),
    }


def _movement_data(m):
    return {
        "id":          m.id,
        "type":        m.type,
        "amount":      str(m.amount),
        "description": m.description,
        "created_by":  m.created_by.get_full_name() or m.created_by.email,
        "created_at":  m.created_at.isoformat(),
    }


def _session_data(session, include_movements=False, include_summary=False):
    d = {
        "id":             session.id,
        "register_id":    session.register_id,
        "register_name":  session.register.name,
        "status":         session.status,
        "opened_by":      session.opened_by.get_full_name() or session.opened_by.email,
        "opened_at":      session.opened_at.isoformat(),
        "initial_amount": str(session.initial_amount),
        "closed_at":      session.closed_at.isoformat() if session.closed_at else None,
        "counted_cash":   str(session.counted_cash) if session.counted_cash is not None else None,
        "expected_cash":  str(session.expected_cash) if session.expected_cash is not None else None,
        "difference":     str(session.difference) if session.difference is not None else None,
        "note":           session.note,
    }
    if include_movements:
        d["movements"] = [_movement_data(m) for m in session.movements.select_related("created_by").order_by("created_at")]
    # Summary:
    # - Sesión OPEN  → recalcular en vivo (en tiempo real refleja ventas
    #   recién hechas, ediciones de propinas, anulaciones, etc.).
    # - Sesión CLOSED → devolver el SNAPSHOT inmutable persistido al
    #   cerrar (estilo Fudo: arqueo cerrado no puede mutar). Sin esto,
    #   editar/anular una venta DESPUÉS del cierre cambia el reporte de
    #   ayer y rompe la auditoría.
    # - Sesión CLOSED legacy (sin snapshot) → fallback a recálculo y
    #   marcamos `snapshot_legacy=True` para que el frontend pueda avisar
    #   "este arqueo es anterior al snapshot inmutable, los valores se
    #   recalculan con datos actuales y pueden no coincidir con el cierre
    #   original".
    if include_summary:
        if session.status == CashSession.STATUS_CLOSED:
            snap = session.closing_snapshot or {}
            if snap:
                # Snapshot persistido al cierre — fuente de verdad inmutable.
                d["live"] = snap
            else:
                # Legacy: sesión cerrada ANTES del refactor closing_snapshot.
                # NO recalcular dinámicamente — el rango temporal puede haber
                # cambiado (ej. fix PR #93 "ignorar sesiones-fantasma") y dar
                # números distintos a los del cierre original. Caso real
                # Marbrava 27-abr: sesión #14 se cerró con expected=$100k,
                # recálculo hoy daría $150k → confunde al dueño.
                # Devolvemos solo los valores persistidos en BD (autoritativos
                # del momento del cierre) + flag para que el frontend muestre
                # un aviso "este arqueo no tiene desglose detallado".
                zero_str = "0"
                d["live"] = {
                    "initial_amount":   str(session.initial_amount),
                    "expected_cash":    str(session.expected_cash) if session.expected_cash is not None else zero_str,
                    "counted_cash":     str(session.counted_cash) if session.counted_cash is not None else zero_str,
                    "difference":       str(session.difference) if session.difference is not None else zero_str,
                    # Desglose por método NO disponible para sesiones legacy.
                    # Frontend debe mostrar "Detalle no disponible para arqueos
                    # cerrados antes de la actualización del 30/04/26".
                    "snapshot_legacy":  True,
                    # Estos campos quedan vacíos para no inducir cifras falsas.
                    "cash_sales":       zero_str,
                    "debit_sales":      zero_str,
                    "card_sales":       zero_str,
                    "transfer_sales":   zero_str,
                    "total_sales":      zero_str,
                    "cash_tips":        zero_str,
                    "total_tips":       zero_str,
                    "tips_by_method":   {"cash": zero_str, "debit": zero_str, "card": zero_str, "transfer": zero_str},
                    "tip_count_by_method": {"cash": 0, "debit": 0, "card": 0, "transfer": 0},
                    "movements_in":     zero_str,
                    "movements_out":    zero_str,
                }
        else:
            d["live"] = _session_summary(session)
    return d


# ══════════════════════════════════════════════════════════════════════════════
# REGISTERS
# ══════════════════════════════════════════════════════════════════════════════

class RegisterListCreate(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _t(request); s_id = _s(request)
        qs = CashRegister.objects.filter(tenant_id=t_id, store_id=s_id, is_active=True)
        return Response([{
            "id": r.id, "name": r.name, "is_active": r.is_active,
            "has_open_session": r.sessions.filter(status=CashSession.STATUS_OPEN).exists(),
        } for r in qs])

    def post(self, request):
        t_id = _t(request); s_id = _s(request)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name required"}, status=400)

        # Verificar límite de cajas del plan (por local, no global)
        from billing.models import Subscription
        from billing.services import check_plan_limit
        try:
            sub = Subscription.objects.select_related("plan").get(tenant_id=t_id)
            # Count per-store: each store can have up to max_registers cajas
            current = CashRegister.objects.filter(
                tenant_id=t_id, store_id=s_id, is_active=True,
            ).count()
            result = check_plan_limit(sub, "registers", current)
            if not result["allowed"]:
                return Response(
                    {"detail": f"Tu plan permite máximo {result['limit']} caja(s) por local."},
                    status=403,
                )
        except Subscription.DoesNotExist:
            pass  # Sin suscripción → permitir (no bloquear)

        r = CashRegister.objects.create(tenant_id=t_id, store_id=s_id, name=name)
        return Response({"id": r.id, "name": r.name}, status=201)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION — current / open / detail / close / history
# ══════════════════════════════════════════════════════════════════════════════

class CurrentSessionView(APIView):
    """GET /caja/sessions/current/ — returns open session for active store, or 404."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        t_id = _t(request); s_id = _s(request)
        session = CashSession.objects.filter(
            tenant_id=t_id, store_id=s_id, status=CashSession.STATUS_OPEN
        ).select_related("register", "opened_by").first()
        if not session:
            return Response({"detail": "No open session"}, status=404)
        return Response(_session_data(session, include_movements=True, include_summary=True))


class OpenSessionView(APIView):
    """POST /caja/registers/<id>/open/ — open a new session."""
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            register = CashRegister.objects.select_for_update().get(
                id=pk, tenant_id=t_id, store_id=s_id, is_active=True
            )
        except CashRegister.DoesNotExist:
            return Response({"detail": "Register not found"}, status=404)

        if register.sessions.filter(status=CashSession.STATUS_OPEN).exists():
            return Response({"detail": "Register already has an open session"}, status=409)

        try:
            initial = Decimal(str(request.data.get("initial_amount") or 0))
            if initial < 0:
                return Response({"detail": "El monto inicial no puede ser negativo."}, status=400)
        except (ValueError, ArithmeticError, TypeError):
            initial = Decimal("0")

        session = CashSession.objects.create(
            tenant_id=t_id,
            store_id=s_id,
            register=register,
            opened_by=request.user,
            initial_amount=initial,
        )
        return Response(_session_data(session, include_summary=True), status=201)


class SessionDetailView(APIView):
    """GET /caja/sessions/<id>/ — full detail with movements and live summary."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            session = CashSession.objects.select_related("register", "opened_by", "closed_by").get(
                id=pk, tenant_id=t_id, store_id=s_id
            )
        except CashSession.DoesNotExist:
            return Response({"detail": "Not found"}, status=404)
        return Response(_session_data(session, include_movements=True, include_summary=True))


class AddMovementView(APIView):
    """POST /caja/sessions/<id>/movements/ — add a manual cash movement."""
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request, pk):
        """Crear un movimiento manual en una sesión abierta.

        Race-safe: lockeamos la CashSession con select_for_update y re-validamos
        que siga OPEN bajo el lock. Así un movimiento no puede sumarse a una
        sesión que se está cerrando en paralelo (se contabilizaría mal el
        arqueo).
        """
        t_id = _t(request); s_id = _s(request)
        try:
            session = (
                CashSession.objects
                .select_for_update()
                .get(id=pk, tenant_id=t_id, store_id=s_id)
            )
        except CashSession.DoesNotExist:
            return Response({"detail": "Open session not found"}, status=404)
        if session.status != CashSession.STATUS_OPEN:
            return Response(
                {"detail": "La sesión ya no está abierta."},
                status=409,
            )

        mov_type = (request.data.get("type") or "").upper()
        if mov_type not in (CashMovement.TYPE_IN, CashMovement.TYPE_OUT):
            return Response({"detail": "type must be IN or OUT"}, status=400)

        try:
            amount = Decimal(str(request.data.get("amount") or 0))
            if amount <= 0:
                raise ValueError("amount must be positive")
        except (ValueError, ArithmeticError, TypeError):
            return Response({"detail": "amount must be > 0"}, status=400)

        description = (request.data.get("description") or "").strip()
        if not description:
            return Response({"detail": "description required"}, status=400)

        m = CashMovement.objects.create(
            tenant_id=t_id,
            session=session,
            type=mov_type,
            amount=amount,
            description=description,
            created_by=request.user,
        )
        return Response(_movement_data(m), status=201)


class CloseSessionView(APIView):
    """POST /caja/sessions/<id>/close/ — close an open session with counted cash."""
    permission_classes = [IsAuthenticated, HasTenant]

    @transaction.atomic
    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            session = CashSession.objects.select_for_update().select_related("register").get(
                id=pk, tenant_id=t_id, store_id=s_id, status=CashSession.STATUS_OPEN
            )
        except CashSession.DoesNotExist:
            return Response({"detail": "Open session not found"}, status=404)

        try:
            counted = Decimal(str(request.data.get("counted_cash") or 0))
            if counted < 0:
                return Response({"detail": "counted_cash no puede ser negativo."}, status=400)
        except (ValueError, ArithmeticError, TypeError):
            return Response({"detail": "counted_cash must be a number"}, status=400)

        note = (request.data.get("note") or "").strip()

        # Asociar ventas huérfanas (cash_session=NULL) que cayeron dentro
        # del rango EXTENDIDO de esta sesión (incluye huérfanas previas a
        # la apertura si no hay sesión cerrada anterior — caso Marbrava
        # 27-abr donde abrieron caja a las 17:26 con 8 ventas previas).
        # Reusamos exactamente el mismo rango que _session_summary para
        # mantener consistencia: lo que aparece en el cierre = lo que se
        # asocia por FK.
        # NOTA: las que tienen FK a OTRA sesión (no debería pasar por el
        # constraint de 1 sola OPEN, pero defensivo) NO se tocan.
        from sales.models import Sale
        end_dt = timezone.now()  # cierre = ahora
        # Mismo cálculo de rango extendido que `_sales_in_session_range`
        # (ignora sesiones-fantasma sin actividad).
        prev_closed = None
        candidates = CashSession.objects.filter(
            tenant_id=t_id, store_id=s_id,
            status=CashSession.STATUS_CLOSED,
            closed_at__lte=session.opened_at,
        ).exclude(id=session.id).order_by("-closed_at")[:10]
        for pc in candidates:
            has_sales = Sale.objects.filter(
                cash_session_id=pc.id, status="COMPLETED",
            ).exists()
            has_movs = pc.movements.exists()
            if has_sales or has_movs:
                prev_closed = pc
                break

        if prev_closed and prev_closed.closed_at:
            start_dt = prev_closed.closed_at
        else:
            from datetime import datetime, time as dt_time
            local_tz = timezone.get_current_timezone()
            opened_local = session.opened_at.astimezone(local_tz)
            start_of_day_naive = datetime.combine(opened_local.date(), dt_time(0, 0))
            start_dt = timezone.make_aware(start_of_day_naive, local_tz)
        if start_dt > session.opened_at:
            start_dt = session.opened_at

        # Mismo fix de boundary que `_sales_in_session_range`:
        # - end_dt usa __lte (incluye created_at exacto al cierre).
        # - start_dt usa __gt si viene de prev_closed (evita doble FK);
        #   __gte si viene de inicio del día (no hay riesgo).
        sales_qs = Sale.objects.filter(
            tenant_id=t_id, store_id=s_id,
            cash_session__isnull=True,
            created_at__lte=end_dt,
        )
        if prev_closed is not None and prev_closed.closed_at is not None:
            sales_qs = sales_qs.filter(created_at__gt=start_dt)
        else:
            sales_qs = sales_qs.filter(created_at__gte=start_dt)
        sales_qs.update(cash_session=session)

        # Compute expected_cash usando el rango temporal extendido
        live = _session_summary(session)
        expected = Decimal(live["expected_cash"])
        difference = counted - expected

        session.status       = CashSession.STATUS_CLOSED
        session.closed_by    = request.user
        session.closed_at    = end_dt
        session.counted_cash = counted
        session.expected_cash = expected
        session.difference   = difference
        session.note         = note
        # Snapshot inmutable del summary completo. Si después editan/anulan
        # ventas de esta sesión, el reporte de cierre histórico NO debe
        # mutar (estilo Fudo). Ver `_session_data` para cómo se prefiere
        # snapshot vs. recálculo en sesiones cerradas.
        session.closing_snapshot = live
        session.save(update_fields=[
            "status", "closed_by", "closed_at",
            "counted_cash", "expected_cash", "difference", "note",
            "closing_snapshot",
        ])

        # Devolver el detail con summary para que el frontend muestre el
        # cierre completo (incluyendo el snapshot recién persistido).
        return Response(_session_data(session, include_movements=True, include_summary=True))


class SessionHistoryView(APIView):
    """GET /caja/sessions/history/?page=1 — closed sessions paginated."""
    permission_classes = [IsAuthenticated, HasTenant]

    PAGE_SIZE = 20

    def get(self, request):
        t_id = _t(request); s_id = _s(request)
        qs = CashSession.objects.filter(
            tenant_id=t_id, store_id=s_id, status=CashSession.STATUS_CLOSED
        ).select_related("register", "opened_by", "closed_by").order_by("-closed_at")

        # Paginación
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        total = qs.count()
        start = (page - 1) * self.PAGE_SIZE
        sessions = qs[start:start + self.PAGE_SIZE]

        return Response({
            "results": [_session_data(s) for s in sessions],
            "count": total,
            "page": page,
            "page_size": self.PAGE_SIZE,
        })
