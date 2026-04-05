"""
caja/views.py — Cash register management API
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Q
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


def _session_summary(session):
    """Compute live expected_cash and payment breakdown for an open session."""
    from sales.models import SalePayment

    # Single query: GROUP BY method → {method: total}
    method_totals = dict(
        SalePayment.objects.filter(
            sale__cash_session=session,
            sale__status="COMPLETED",
        ).values_list("method").annotate(total=Sum("amount")).values_list("method", "total")
    )
    zero = Decimal("0")
    cash_sales     = method_totals.get("cash", zero) or zero
    debit_sales    = method_totals.get("debit", zero) or zero
    card_sales     = method_totals.get("card", zero) or zero
    transfer_sales = method_totals.get("transfer", zero) or zero
    total_sales    = cash_sales + debit_sales + card_sales + transfer_sales

    cash_tips = session.sales.filter(status="COMPLETED").aggregate(
        s=Coalesce(Sum("tip"), zero)
    )["s"]

    # Single query for movements: GROUP BY type
    mov_totals = dict(
        session.movements.values_list("type").annotate(total=Sum("amount")).values_list("type", "total")
    )
    movements_in  = mov_totals.get("IN", zero) or zero
    movements_out = mov_totals.get("OUT", zero) or zero

    # expected_cash ONLY includes physical cash (efectivo)
    expected = session.initial_amount + cash_sales + cash_tips + movements_in - movements_out
    return {
        "initial_amount":  str(session.initial_amount),
        # Desglose por método de pago
        "cash_sales":      str(cash_sales),
        "debit_sales":     str(debit_sales),
        "card_sales":      str(card_sales),
        "transfer_sales":  str(transfer_sales),
        "total_sales":     str(total_sales),
        # Flujo de caja (efectivo físico)
        "cash_tips":       str(cash_tips),
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
    if include_summary and session.status == CashSession.STATUS_OPEN:
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

        # Verificar límite de cajas del plan
        from billing.models import Subscription
        from billing.services import check_plan_limit
        try:
            sub = Subscription.objects.select_related("plan").get(tenant_id=t_id)
            current = CashRegister.objects.filter(tenant_id=t_id, is_active=True).count()
            result = check_plan_limit(sub, "registers", current)
            if not result["allowed"]:
                return Response(
                    {"detail": f"Tu plan permite máximo {result['limit']} caja(s)."},
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

    def post(self, request, pk):
        t_id = _t(request); s_id = _s(request)
        try:
            session = CashSession.objects.get(id=pk, tenant_id=t_id, store_id=s_id, status=CashSession.STATUS_OPEN)
        except CashSession.DoesNotExist:
            return Response({"detail": "Open session not found"}, status=404)

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

        # Compute expected_cash
        live = _session_summary(session)
        expected = Decimal(live["expected_cash"])
        difference = counted - expected

        session.status       = CashSession.STATUS_CLOSED
        session.closed_by    = request.user
        session.closed_at    = timezone.now()
        session.counted_cash = counted
        session.expected_cash = expected
        session.difference   = difference
        session.note         = note
        session.save(update_fields=[
            "status", "closed_by", "closed_at",
            "counted_cash", "expected_cash", "difference", "note",
        ])

        return Response(_session_data(session))


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
