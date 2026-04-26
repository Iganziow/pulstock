"""
billing/views.py
================
API REST del sistema de suscripciones.

Endpoints:
  GET  /api/billing/subscription/         → estado actual de la suscripción
  POST /api/billing/subscription/upgrade/ → cambiar de plan
  POST /api/billing/subscription/cancel/  → cancelar
  POST /api/billing/subscription/reactivate/ → reactivar (tras pago manual)
  GET  /api/billing/invoices/             → historial de facturas
  GET  /api/billing/plans/                → planes disponibles (público)
  POST /api/billing/webhook/flow/         → webhook de Flow.cl
  POST /api/billing/payment-link/         → generar link de pago manual
"""

from django.db import IntegrityError
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from api.throttles import WebhookRateThrottle

from .models import Plan, Subscription, Invoice
from .services import (
    change_plan,
    cancel_subscription,
    reactivate_subscription,
    get_subscription_status_for_api,
    activate_period,
    register_payment_failure,
)
from .gateway import (
    create_payment_link, get_payment_status,
    register_flow_card, get_card_register_status, unregister_flow_card,
)
from .models import PaymentAttempt
from core.permissions import HasTenant, IsOwner

import logging
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# HELPERS COMUNES PARA WEBHOOKS DE FLOW
# ─────────────────────────────────────────────────────────────
def _flow_amount_matches(payment_data: dict, expected_clp: int) -> bool:
    """
    Valida que Flow reporte el mismo monto que esperábamos.

    Flow devuelve `amount` como string o número según versión de API. Convertimos a int.
    Además verifica `currency == "CLP"`. Si no coincide, es amount tampering (crítico).
    """
    try:
        actual = int(float(payment_data.get("amount", 0)))
    except (ValueError, TypeError):
        return False
    currency = (payment_data.get("currency") or "").upper()
    return actual == int(expected_clp) and currency == "CLP"


def _flow_webhook_verify_signature(payment_data: dict) -> bool:
    """
    Verifica firma HMAC de una respuesta de Flow (defensa en profundidad).
    En MOCK siempre devuelve True. En Flow real, la firma puede venir o no
    según el endpoint — si viene, se valida; si no viene, igual se confía en
    el resultado de getStatus (llamado con nuestra apiKey).
    """
    from django.conf import settings as dj_settings
    if dj_settings.PAYMENT_GATEWAY == "mock":
        return True
    sig = payment_data.get("s")
    if not sig:
        # Flow getStatus no siempre firma la respuesta — es OK si no viene firma,
        # dado que el getStatus ya fue autenticado con nuestra apiKey+secret.
        return True
    from .gateway import _verify_flow_token_signature
    return _verify_flow_token_signature(payment_data)


# ─────────────────────────────────────────────────────────────
# PLANES DISPONIBLES (público)
# ─────────────────────────────────────────────────────────────
class PlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = Plan.objects.filter(is_active=True).order_by("price_clp")
        return Response([
            {
                "key":          p.key,
                "name":         p.name,
                "price_clp":    p.price_clp,
                "trial_days":   p.trial_days,
                "max_products": p.max_products,
                "max_stores":   p.max_stores,
                "max_users":    p.max_users,
                "max_registers":p.max_registers,
                "has_forecast": p.has_forecast,
                "has_abc":      p.has_abc,
                "has_reports":  p.has_reports,
                "has_transfers":p.has_transfers,
            }
            for p in plans
        ])


# ─────────────────────────────────────────────────────────────
# ESTADO DE SUSCRIPCIÓN
# ─────────────────────────────────────────────────────────────
class SubscriptionView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        try:
            sub = Subscription.objects.select_related("plan", "tenant").get(
                tenant_id=request.user.tenant_id
            )
        except Subscription.DoesNotExist:
            return Response(
                {"detail": "Sin suscripción activa. Contacta soporte."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = get_subscription_status_for_api(sub)

        # Agregar historial reciente de facturas
        invoices = Invoice.objects.filter(subscription=sub).order_by("-created_at")[:6]
        data["recent_invoices"] = [
            {
                "id":          inv.pk,
                "status":      inv.status,
                "amount_clp":  inv.amount_clp,
                "period_start": inv.period_start.isoformat(),
                "period_end":   inv.period_end.isoformat(),
                "paid_at":     inv.paid_at.isoformat() if inv.paid_at else None,
                "payment_url": inv.payment_url or None,
                "created_at":  inv.created_at.isoformat(),
            }
            for inv in invoices
        ]

        return Response(data)


# ─────────────────────────────────────────────────────────────
# CAMBIAR PLAN (upgrade / downgrade)
# ─────────────────────────────────────────────────────────────
class ChangePlanView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        new_plan_key = request.data.get("plan")
        if not new_plan_key:
            return Response(
                {"detail": "El campo 'plan' es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_keys = list(Plan.objects.filter(is_active=True).values_list("key", flat=True))
        if new_plan_key not in valid_keys:
            return Response(
                {"detail": f"Plan inválido. Opciones: {', '.join(valid_keys)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub = Subscription.objects.select_related("plan").get(
                tenant_id=request.user.tenant_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        if sub.plan.key == new_plan_key:
            return Response({"detail": "Ya estás en ese plan."}, status=status.HTTP_400_BAD_REQUEST)

        sub = change_plan(sub, new_plan_key)

        # Si el nuevo plan es de pago y no hay método guardado → generar link
        response_data = get_subscription_status_for_api(sub)
        if sub.plan.price_clp > 0 and sub.status == Subscription.Status.PAST_DUE:
            invoice = Invoice.objects.filter(
                subscription=sub, status=Invoice.Status.PENDING
            ).first()
            if invoice:
                link_result = create_payment_link(sub, invoice)
                response_data["payment_url"] = link_result.get("payment_url")

        return Response(response_data)


# ─────────────────────────────────────────────────────────────
# CANCELAR SUSCRIPCIÓN
# ─────────────────────────────────────────────────────────────
class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        try:
            sub = Subscription.objects.get(tenant_id=request.user.tenant_id)
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status == Subscription.Status.CANCELLED:
            return Response({"detail": "La suscripción ya está cancelada."})

        reason = request.data.get("reason", "")
        sub = cancel_subscription(sub, reason=reason)

        return Response({
            "ok": True,
            "message": "Suscripción cancelada. Tu acceso continúa hasta el fin del período actual.",
            "access_until": sub.current_period_end.isoformat() if sub.current_period_end else None,
        })


# ─────────────────────────────────────────────────────────────
# REACTIVAR SUSCRIPCIÓN
# ─────────────────────────────────────────────────────────────
class ReactivateSubscriptionView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        try:
            sub = Subscription.objects.select_related("plan").get(
                tenant_id=request.user.tenant_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        if sub.status == Subscription.Status.ACTIVE:
            return Response({"detail": "La suscripción ya está activa."})

        # Si el plan es de pago, se necesita procesar un cobro
        if sub.plan.price_clp > 0:
            from .models import Invoice
            from .services import create_invoice
            from .gateway import charge_subscription

            # Idempotencia: reusar factura pendiente si existe
            existing_invoice = Invoice.objects.filter(
                subscription=sub,
                status=Invoice.Status.PENDING,
            ).order_by("-created_at").first()
            invoice = existing_invoice or create_invoice(sub)
            result  = charge_subscription(sub, invoice)

            if result["success"]:
                sub = reactivate_subscription(sub)
                return Response({
                    "ok": True,
                    "message": "Suscripción reactivada exitosamente.",
                    **get_subscription_status_for_api(sub),
                })
            else:
                # Generar link de pago manual
                link = create_payment_link(sub, invoice)
                return Response({
                    "ok": False,
                    "message": "No pudimos procesar el pago automáticamente. Usa el link de pago.",
                    "payment_url": link.get("payment_url"),
                }, status=status.HTTP_402_PAYMENT_REQUIRED)
        else:
            sub = reactivate_subscription(sub)
            return Response({"ok": True, **get_subscription_status_for_api(sub)})


# ─────────────────────────────────────────────────────────────
# GENERAR LINK DE PAGO MANUAL
# ─────────────────────────────────────────────────────────────
class PaymentLinkView(APIView):
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        try:
            sub = Subscription.objects.select_related("plan").get(
                tenant_id=request.user.tenant_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        # Buscar invoice pendiente o crear uno nuevo
        invoice = Invoice.objects.filter(
            subscription=sub,
            status__in=[Invoice.Status.PENDING, Invoice.Status.FAILED],
        ).order_by("-created_at").first()

        if not invoice:
            from .services import create_invoice
            invoice = create_invoice(sub)

        result = create_payment_link(sub, invoice)

        if result.get("success"):
            return Response({
                "payment_url": result["payment_url"],
                "amount_clp":  invoice.amount_clp,
                "invoice_id":  invoice.pk,
            })
        else:
            return Response(
                {"detail": result.get("error", "No se pudo generar el link de pago.")},
                status=status.HTTP_502_BAD_GATEWAY,
            )


# ─────────────────────────────────────────────────────────────
# CONFIRMAR PAGO (frontend envía token de retorno de Flow)
# ─────────────────────────────────────────────────────────────
class ConfirmPaymentView(APIView):
    """
    Endpoint de seguridad: el frontend llama con el token que Flow
    pone en la URL de retorno (?token=XXX).

    Flujo:
    1. Llama a Flow GET /payment/getStatus con el token
    2. Verifica que commerceOrder corresponde a una factura del tenant
    3. Procesa el pago (idempotente: si el webhook ya procesó, no repite)

    Esto complementa al webhook: si ngrok/tunnel cae, el pago igual
    se confirma cuando el usuario vuelve al frontend.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            return Response(
                {"detail": "Token requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 1. Consultar estado real en Flow ──
        payment_data = get_payment_status(token)

        flow_status = payment_data.get("status")
        commerce_order = payment_data.get("commerceOrder", "")

        if flow_status == -1:
            logger.error("ConfirmPayment: error getStatus token=%s", token[:20])
            return Response(
                {"detail": "Error consultando estado de pago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ── 2. Buscar factura con lock (race-safe con webhook) ──
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            try:
                invoice = (
                    Invoice.objects
                    .select_for_update()
                    .select_related(
                        "subscription", "subscription__plan", "subscription__tenant",
                    )
                    .get(pk=int(commerce_order))
                )
            except (Invoice.DoesNotExist, ValueError, TypeError):
                logger.warning("ConfirmPayment: factura no encontrada order=%s",
                               commerce_order)
                return Response(
                    {"detail": "Factura no encontrada."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Seguridad: verificar que la factura pertenece al tenant del usuario
            if invoice.subscription.tenant_id != request.user.tenant_id:
                logger.warning(
                    "ConfirmPayment: tenant mismatch user=%s invoice_tenant=%s",
                    request.user.tenant_id, invoice.subscription.tenant_id,
                )
                return Response(
                    {"detail": "Factura no encontrada."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            sub = invoice.subscription

            # ── 3. Procesar según estado ──
            if flow_status == 2:
                # PAGADO — idempotente (puede que el webhook ya haya procesado)
                if invoice.status == Invoice.Status.PAID:
                    return Response({
                        "ok": True,
                        "status": "already_paid",
                        "detail": "El pago ya fue procesado.",
                    })

                # Validar monto (defensa contra amount tampering)
                if not _flow_amount_matches(payment_data, int(invoice.amount_clp)):
                    logger.error(
                        "ConfirmPayment: AMOUNT MISMATCH invoice=#%d esperado=%d CLP "
                        "recibido=%s %s",
                        invoice.pk, int(invoice.amount_clp),
                        payment_data.get("amount"), payment_data.get("currency"),
                    )
                    return Response(
                        {"detail": "Amount mismatch."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Extraer datos del pago y guardarlos en el Invoice
                # (mismo flujo que el webhook — ver _FlowWebhookView).
                from .gateway import extract_payment_details
                details = extract_payment_details(payment_data)

                invoice.gateway_tx_id      = str(payment_data.get("flowOrder", ""))
                invoice.card_last4         = details["card_last4"]
                invoice.card_brand         = details["card_brand"]
                invoice.payment_media      = details["payment_media"]
                invoice.payment_media_type = details["payment_media_type"]
                invoice.installments       = details["installments"]
                invoice.authorization_code = details["authorization_code"]
                invoice.failure_code       = ""
                invoice.failure_message    = ""
                invoice.save(update_fields=[
                    "gateway_tx_id", "card_last4", "card_brand",
                    "payment_media", "payment_media_type", "installments",
                    "authorization_code", "failure_code", "failure_message",
                ])

                if details["card_last4"]:
                    sub.card_last4 = details["card_last4"]
                    sub.card_brand = details["card_brand"]
                    sub.save(update_fields=["card_last4", "card_brand"])

                PaymentAttempt.objects.create(
                    invoice=invoice,
                    gateway="flow",
                    result=PaymentAttempt.Result.SUCCESS,
                    raw=payment_data,
                )

                activate_period(sub, invoice)
                logger.info(
                    "ConfirmPayment: pago exitoso invoice=#%d tenant=%s card=%s·%s",
                    invoice.pk, sub.tenant_id,
                    details["card_brand"] or "-", details["card_last4"] or "----",
                )
                return Response({
                    "ok": True,
                    "status": "paid",
                    "detail": "Pago confirmado exitosamente.",
                })

            elif flow_status in (3, 4):
                # Extraer motivo real de Flow si lo hay
                from .gateway import extract_payment_details
                details = extract_payment_details(payment_data)
                if details["failure_message"]:
                    error = details["failure_message"]
                else:
                    error = "Pago rechazado" if flow_status == 3 else "Pago anulado"

                if invoice.status not in (Invoice.Status.FAILED, Invoice.Status.PAID):
                    invoice.failure_code    = details["failure_code"]
                    invoice.failure_message = error
                    invoice.save(update_fields=["failure_code", "failure_message"])
                    register_payment_failure(sub, invoice, error_msg=error, raw=payment_data)

                return Response({
                    "ok": False,
                    "status": "rejected",
                    "detail": error,
                })

            else:
                return Response({
                    "ok": False,
                    "status": "pending",
                    "detail": "El pago aún está pendiente. Inténtalo en unos segundos.",
                })


# ─────────────────────────────────────────────────────────────
# HISTORIAL DE FACTURAS
# ─────────────────────────────────────────────────────────────
class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        try:
            sub = Subscription.objects.get(tenant_id=request.user.tenant_id)
        except Subscription.DoesNotExist:
            return Response([])

        invoices = Invoice.objects.filter(subscription=sub).order_by("-created_at")[:24]
        return Response([
            {
                "id":           inv.pk,
                "status":       inv.status,
                "status_label": inv.get_status_display(),
                "amount_clp":   inv.amount_clp,
                "period_start": inv.period_start.isoformat(),
                "period_end":   inv.period_end.isoformat(),
                "gateway":      inv.gateway,
                "paid_at":      inv.paid_at.isoformat() if inv.paid_at else None,
                "payment_url":  inv.payment_url or None,
                "created_at":   inv.created_at.isoformat(),
                "attempts":     inv.attempts.count(),
            }
            for inv in invoices
        ])


# ─────────────────────────────────────────────────────────────
# REGISTRO DE TARJETA (cobro automático)
# ─────────────────────────────────────────────────────────────
class RegisterCardView(APIView):
    """Inicia el proceso de registro de tarjeta en Flow."""
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        try:
            sub = Subscription.objects.select_related("plan", "tenant").get(
                tenant_id=request.user.tenant_id
            )
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        result = register_flow_card(sub)
        if "error" in result:
            return Response({"detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"register_url": result["url"]})

    def get(self, request):
        """Retorna info de tarjeta registrada."""
        try:
            sub = Subscription.objects.get(tenant_id=request.user.tenant_id)
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "has_card": bool(sub.card_last4),
            "card_brand": sub.card_brand,
            "card_last4": sub.card_last4,
            "flow_customer_id": sub.flow_customer_id or None,
        })


class UnregisterCardView(APIView):
    """Elimina la tarjeta registrada."""
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def post(self, request):
        try:
            sub = Subscription.objects.get(tenant_id=request.user.tenant_id)
        except Subscription.DoesNotExist:
            return Response({"detail": "Sin suscripción."}, status=status.HTTP_404_NOT_FOUND)

        result = unregister_flow_card(sub)
        if "error" in result:
            return Response({"detail": result["error"]}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"ok": True, "detail": "Tarjeta eliminada."})


@method_decorator(csrf_exempt, name="dispatch")
class FlowCardRegisterWebhookView(APIView):
    """
    Callback de Flow tras registro de tarjeta.
    Flow envía POST con {token} a esta URL.
    Verificamos con getRegisterStatus y guardamos datos de tarjeta.
    """
    permission_classes = [AllowAny]

    throttle_classes = [WebhookRateThrottle]

    def post(self, request):
        token = request.data.get("token") or request.POST.get("token", "")
        if not token:
            return Response({"detail": "Token requerido."}, status=status.HTTP_400_BAD_REQUEST)

        result = get_card_register_status(token)

        # HMAC defensa en profundidad (si Flow provee firma)
        if not _flow_webhook_verify_signature(result):
            logger.warning("CardRegister webhook: firma HMAC inválida token=%s", token[:20])
            return Response({"detail": "Firma inválida."}, status=status.HTTP_403_FORBIDDEN)

        reg_status = result.get("status")
        customer_id = (result.get("customerId") or "").strip()

        if str(reg_status) == "1" and customer_id:
            # Buscar subscripción — validar unicidad del customer_id
            # (flow_customer_id puede ser "" en varias subs, filtramos vacíos)
            matches = list(Subscription.objects.filter(
                flow_customer_id=customer_id,
            ).exclude(flow_customer_id=""))
            if len(matches) == 0:
                logger.error(
                    "Card register: subscription not found for customer=%s",
                    customer_id,
                )
            elif len(matches) > 1:
                logger.error(
                    "Card register: MULTIPLE subs with customer_id=%s (ids=%s)",
                    customer_id, [s.pk for s in matches],
                )
            else:
                sub = matches[0]
                sub.card_brand = (result.get("creditCardType") or "")[:30]
                sub.card_last4 = (result.get("last4CardDigits") or "")[:4]
                sub.save(update_fields=["card_brand", "card_last4"])
                logger.info(
                    "Card registered: tenant=%s brand=%s last4=%s",
                    sub.tenant_id, sub.card_brand, sub.card_last4,
                )

        # Redirigir al usuario de vuelta al frontend
        from django.conf import settings as django_settings
        app_base = getattr(django_settings, "APP_BASE_URL", "http://localhost:3000")
        from django.shortcuts import redirect
        card_ok = str(reg_status) == "1"
        return redirect(f"{app_base}/dashboard/settings?tab=plan&card={'ok' if card_ok else 'fail'}")


# ─────────────────────────────────────────────────────────────
# WEBHOOK FLOW.CL
# ─────────────────────────────────────────────────────────────
@method_decorator(csrf_exempt, name="dispatch")
class FlowWebhookView(APIView):
    """
    Webhook que recibe notificaciones de pago de Flow.cl.

    Protocolo Flow:
    1. Flow envía POST con content-type application/x-www-form-urlencoded
    2. El único parámetro es 'token' — un hash que identifica la transacción
    3. Debemos llamar a GET /payment/getStatus con ese token para obtener
       el resultado real del pago (NO confiar en datos del POST)
    4. El getStatus retorna: status 1=pendiente, 2=pagado, 3=rechazado, 4=anulado
    """
    permission_classes = [AllowAny]
    # No requiere autenticación: Flow lo llama desde sus servidores

    throttle_classes = [WebhookRateThrottle]

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)

        # ── 1. Extraer y validar token del POST ──
        token = request.data.get("token") or request.POST.get("token", "")
        if not token:
            logger.warning("Flow webhook: sin token en POST data")
            return Response(
                {"detail": "Token requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Consultar estado real del pago en Flow ──
        payment_data = get_payment_status(token)

        # Verificar firma HMAC cuando Flow la provea (defensa en profundidad).
        # Si la firma no viene (algunos endpoints de Flow no firman), confiamos
        # en que getStatus se llama con nuestra apiKey+secret, lo cual ya es
        # autenticación de lado nuestro.
        if not _flow_webhook_verify_signature(payment_data):
            logger.warning("Flow webhook: firma HMAC inválida token=%s", token[:20])
            return Response({"detail": "Firma inválida."}, status=status.HTTP_403_FORBIDDEN)

        flow_status = payment_data.get("status")
        commerce_order = payment_data.get("commerceOrder", "")
        flow_order = payment_data.get("flowOrder", "")

        if flow_status == -1:
            # Error consultando Flow
            logger.error("Flow webhook: error getStatus token=%s: %s", token[:20], payment_data.get("error"))
            return Response(
                {"detail": "Error consultando estado de pago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not isinstance(flow_status, int):
            logger.error("Flow webhook: flow_status inválido %r token=%s", flow_status, token[:20])
            return Response(
                {"detail": "Estado de pago inválido."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ── 3. Buscar la factura (con lock para idempotencia) ──
        from django.db import transaction as db_transaction
        from .models import PaymentAttempt

        with db_transaction.atomic():
            try:
                invoice = (
                    Invoice.objects
                    .select_for_update()
                    .select_related(
                        "subscription", "subscription__plan",
                        "subscription__tenant",
                    )
                    .get(pk=int(commerce_order))
                )
            except (Invoice.DoesNotExist, ValueError, TypeError):
                logger.error(
                    "Flow webhook: factura no encontrada. commerceOrder=%s token=%s",
                    commerce_order, token[:20],
                )
                return Response(
                    {"detail": "Factura no encontrada."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            sub = invoice.subscription

            # Idempotency by flowOrder: if a PaymentAttempt with this flowOrder exists,
            # we already processed this webhook (Flow may send multiple notifications).
            if flow_order and PaymentAttempt.objects.filter(
                invoice=invoice, raw__flowOrder=str(flow_order)
            ).exists():
                logger.info(
                    "Flow webhook: duplicate flowOrder=%s invoice=#%d (idempotente)",
                    flow_order, invoice.pk,
                )
                return Response({"ok": True, "detail": "duplicate flowOrder"})

            # If invoice is already PAID, never reprocess (prevents status=3 webhook
            # arriving after status=2 from marking a paid invoice as FAILED).
            if invoice.status == Invoice.Status.PAID:
                logger.info(
                    "Flow webhook: invoice #%d already PAID, ignoring status=%s",
                    invoice.pk, flow_status,
                )
                return Response({"ok": True, "detail": "already paid"})

            # ── 4. Procesar según estado ──
            if flow_status == 2:
                # PAGADO — antes de activar, validamos monto (defensa contra
                # amount tampering: si Flow devuelve un monto distinto al que
                # nosotros generamos, NO marcamos como pagada).
                if not _flow_amount_matches(payment_data, int(invoice.amount_clp)):
                    logger.error(
                        "Flow webhook: AMOUNT MISMATCH invoice=#%d esperado=%d CLP "
                        "recibido=%s %s flowOrder=%s",
                        invoice.pk, int(invoice.amount_clp),
                        payment_data.get("amount"), payment_data.get("currency"),
                        flow_order,
                    )
                    PaymentAttempt.objects.create(
                        invoice=invoice,
                        gateway="flow",
                        result=PaymentAttempt.Result.FAILED,
                        raw=payment_data,
                        error_msg=f"Amount mismatch: expected {invoice.amount_clp} CLP",
                    )
                    return Response(
                        {"detail": "Amount mismatch."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Extraer datos del pago (tarjeta, medio, cuotas, auth) y
                # guardarlos en la factura — son los que muestran los emails
                # payment_recovered / renewal / trial_converted.
                from .gateway import extract_payment_details
                details = extract_payment_details(payment_data)

                invoice.gateway_tx_id      = str(flow_order)
                invoice.card_last4         = details["card_last4"]
                invoice.card_brand         = details["card_brand"]
                invoice.payment_media      = details["payment_media"]
                invoice.payment_media_type = details["payment_media_type"]
                invoice.installments       = details["installments"]
                invoice.authorization_code = details["authorization_code"]
                # Limpiar failure fields si el pago se recuperó tras un retry
                invoice.failure_code       = ""
                invoice.failure_message    = ""
                invoice.save(update_fields=[
                    "gateway_tx_id", "card_last4", "card_brand",
                    "payment_media", "payment_media_type", "installments",
                    "authorization_code", "failure_code", "failure_message",
                ])

                # Syncear también Subscription.card_* (mirror del último pago OK,
                # para mostrar al cliente el método en emails sin tener que
                # lookup el último Invoice cada vez).
                if details["card_last4"]:
                    sub.card_last4 = details["card_last4"]
                    sub.card_brand = details["card_brand"]
                    sub.save(update_fields=["card_last4", "card_brand"])

                # Registrar intento exitoso
                PaymentAttempt.objects.create(
                    invoice=invoice,
                    gateway="flow",
                    result=PaymentAttempt.Result.SUCCESS,
                    raw=payment_data,
                )

                # Activar período pagado
                activate_period(sub, invoice)
                logger.info(
                    "Flow webhook: pago exitoso invoice=#%d tenant=%s flowOrder=%s card=%s·%s",
                    invoice.pk, sub.tenant_id, flow_order,
                    details["card_brand"] or "-", details["card_last4"] or "----",
                )

            elif flow_status in (3, 4):
                # RECHAZADO (3) o ANULADO (4)
                # Extraer motivo real de Flow antes de registrar el fallo. Lo
                # que viene en lastError.message es lo que le vamos a mostrar
                # al cliente en el email payment_failed.
                from .gateway import extract_payment_details
                details = extract_payment_details(payment_data)
                if details["failure_message"]:
                    error = details["failure_message"]
                else:
                    error = "Pago rechazado por Flow" if flow_status == 3 else "Pago anulado"

                invoice.failure_code    = details["failure_code"]
                invoice.failure_message = error
                invoice.save(update_fields=["failure_code", "failure_message"])

                register_payment_failure(sub, invoice, error_msg=error, raw=payment_data)
                logger.warning(
                    "Flow webhook: pago fallido invoice=#%d status=%d code=%s error=%s",
                    invoice.pk, flow_status, details["failure_code"] or "-", error,
                )

            elif flow_status == 1:
                # PENDIENTE — no hacer nada, esperar siguiente webhook
                logger.info("Flow webhook: pago pendiente invoice=#%d", invoice.pk)

        return Response({"ok": True})


# ─────────────────────────────────────────────────────────────
# CHECKOUT — Pago directo desde landing (público, sin auth)
# ─────────────────────────────────────────────────────────────
from api.throttles import RegisterRateThrottle, WebhookRateThrottle
from .models import CheckoutSession
from .gateway import create_checkout_payment_link


def _auto_create_checkout_account(session, payment_data=None):
    """Crea Tenant + User automáticamente cuando session tiene los datos.
    Usa el password hash ya almacenado (no re-hashear).

    Thread-safe: usa select_for_update dentro del atomic para evitar que el
    webhook y el GET /status creen la cuenta dos veces en paralelo.

    payment_data: dict opcional con el response de /payment/getStatusExtended
      de Flow. Si se pasa, se extraen los campos card_last4, card_brand,
      payment_media, etc. y se guardan en el Invoice creado. También se
      syncean Subscription.card_last4 y card_brand para que los emails de
      renewal / payment_recovered puedan mostrar el método real.
    """
    from datetime import timedelta
    from django.db import transaction
    from django.utils.text import slugify
    from core.models import Tenant, User, Warehouse
    from stores.models import Store

    with transaction.atomic():
        # Re-lockear y re-chequear bajo el lock — race-safe
        locked_session = (
            CheckoutSession.objects
            .select_for_update()
            .select_related("plan")
            .get(pk=session.pk)
        )
        if locked_session.status == CheckoutSession.STATUS_COMPLETED:
            return  # idempotente: otro proceso ya creó la cuenta
        # Doble seguridad: si ya hay un tenant asociado al session (cuenta
        # parcialmente creada en un run previo), NO reintentamos — evita crear
        # un segundo Tenant si una exception previa rompió el atomic sin
        # marcar COMPLETED. El status queda en PAID y un humano puede
        # completar manualmente si hace falta.
        if locked_session.tenant_id:
            logger.warning(
                "Auto-create skipped: session #%d ya tiene tenant_id=%s asignado "
                "(estado inconsistente, requiere intervención manual)",
                locked_session.pk, locked_session.tenant_id,
            )
            return
        session = locked_session

        email = session.email
        username = session.owner_username or email
        if (User.objects.filter(username=username).exists()
                or User.objects.filter(email=email).exists()):
            logger.warning(
                "Auto-create skipped: user/email already exists (session #%d)",
                session.pk,
            )
            return

        # Generate unique slug (dentro del atomic para evitar race con otro tenant)
        base_slug = slugify(session.business_name)[:60] or "negocio"
        slug = base_slug
        counter = 1
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        parts = (session.owner_name or "").split(" ", 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

        tenant = Tenant(name=session.business_name, slug=slug, is_active=True)
        tenant._skip_default_store = True
        tenant._skip_subscription = True
        tenant.save()

        store = Store.objects.create(
            tenant=tenant, name="Local Principal",
            code=f"{slug}-1", is_active=True,
        )
        warehouse = Warehouse.objects.create(
            tenant=tenant, store=store, name="Bodega Principal", is_active=True,
        )
        tenant.default_warehouse = warehouse
        tenant.save(update_fields=["default_warehouse"])
        store.default_warehouse = warehouse
        store.save(update_fields=["default_warehouse"])

        try:
            from catalog.management.commands.seed_units import seed_units_for_tenant
            seed_units_for_tenant(tenant)
        except Exception as e:
            logger.warning("seed_units falló: %s", e)

        # Create user with pre-hashed password (avoid re-hashing)
        user = User(
            username=username, email=email,
            first_name=first_name, last_name=last_name,
            tenant=tenant, active_store=store,
        )
        user.password = session.owner_password_hash  # already hashed
        user.role = "owner"
        user.save()

        now = timezone.now()
        sub = Subscription.objects.create(
            tenant=tenant,
            plan=session.plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        # Extraer datos del pago si venían en el webhook (getStatusExtended)
        # para mostrarlos al cliente en el email de welcome / primer invoice.
        card_last4 = card_brand = payment_media = payment_media_type = ""
        installments = None
        authorization_code = ""
        if payment_data:
            from .gateway import extract_payment_details
            details = extract_payment_details(payment_data)
            card_last4         = details["card_last4"]
            card_brand         = details["card_brand"]
            payment_media      = details["payment_media"]
            payment_media_type = details["payment_media_type"]
            installments       = details["installments"]
            authorization_code = details["authorization_code"]

        invoice = Invoice.objects.create(
            subscription=sub,
            status=Invoice.Status.PAID,
            amount_clp=session.amount_clp,
            period_start=now.date(),
            period_end=(now + timedelta(days=30)).date(),
            gateway="flow",
            gateway_order_id=session.gateway_order_id,
            gateway_tx_id=session.gateway_tx_id,
            paid_at=now,
            card_last4=card_last4,
            card_brand=card_brand,
            payment_media=payment_media,
            payment_media_type=payment_media_type,
            installments=installments,
            authorization_code=authorization_code,
        )
        PaymentAttempt.objects.create(
            invoice=invoice,
            result=PaymentAttempt.Result.SUCCESS,
            gateway="flow",
            raw={"checkout_session": str(session.token)},
        )

        # Syncear también en la Subscription (mirror del último pago OK)
        if card_last4:
            sub.card_last4 = card_last4
            sub.card_brand = card_brand
            sub.save(update_fields=["card_last4", "card_brand"])

        session.status = CheckoutSession.STATUS_COMPLETED
        session.tenant = tenant
        session.completed_at = now
        session.save(update_fields=["status", "tenant", "completed_at"])
        logger.info("Auto-created account: session=#%d user=%s tenant=%s", session.pk, username, slug)

        # Email de bienvenida — fuera del atomic (la cuenta ya está creada y
        # confirmada; un fallo de SMTP no debe abortear nada). Captura el
        # error para que no propague.
        try:
            from billing.tasks import _send_welcome_email
            _send_welcome_email(user, tenant, session.plan)
        except Exception as e:
            logger.warning(
                "Welcome email falló (cuenta YA creada OK, no afecta): %s", e,
            )


class CheckoutCreateView(APIView):
    """POST /api/billing/checkout/create/ — Inicia checkout pre-registro."""
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        from django.contrib.auth.hashers import make_password
        from core.models import User

        email = (request.data.get("email") or "").strip().lower()
        plan_key = (request.data.get("plan_key") or "").strip().lower()
        business_name = (request.data.get("business_name") or "").strip()
        business_type = (request.data.get("business_type") or "").strip()
        owner_name = (request.data.get("owner_name") or "").strip()
        owner_username = (request.data.get("owner_username") or "").strip()
        owner_password = request.data.get("owner_password") or ""

        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValError
        try:
            validate_email(email)
        except DjangoValError:
            return Response({"detail": "El email no parece válido. Revisa que esté bien escrito (ej: nombre@dominio.cl)."}, status=400)

        try:
            plan = Plan.objects.get(key=plan_key, is_active=True)
        except Plan.DoesNotExist:
            return Response({"detail": "El plan que elegiste no existe o ya no está disponible. Vuelve a planes y elige otro."}, status=404)

        if plan.price_clp <= 0:
            return Response({"detail": "Este plan es gratuito y no requiere pago. Ve a la página de planes para activarlo."}, status=400)

        # Validate new required fields (backward-compatible: optional if missing)
        if business_name and owner_username and owner_password:
            if len(owner_password) < 8:
                return Response({"detail": "La contraseña es muy corta. Debe tener al menos 8 caracteres."}, status=400)
            if User.objects.filter(email=email).exists():
                return Response({"detail": "Ya existe una cuenta con este email. Si es tuya, inicia sesión. Si no, prueba con otro email."}, status=409)
            if User.objects.filter(username=owner_username).exists():
                return Response({"detail": "Ese nombre de usuario ya está tomado. Prueba con otro (ej: agregando un número)."}, status=409)

        # Idempotencia: reusar sesión pending del mismo email+plan del mismo día
        from datetime import timedelta as td
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = CheckoutSession.objects.filter(
            email=email, plan=plan,
            status=CheckoutSession.STATUS_PENDING,
            expires_at__gt=timezone.now(),
            created_at__gte=today_start,
        ).first()

        if existing and existing.payment_url:
            # Refresh business/owner data on reused session
            if business_name or owner_username:
                existing.business_name = business_name or existing.business_name
                existing.business_type = business_type or existing.business_type
                existing.owner_name = owner_name or existing.owner_name
                existing.owner_username = owner_username or existing.owner_username
                if owner_password:
                    existing.owner_password_hash = make_password(owner_password)
                existing.save(update_fields=[
                    "business_name", "business_type", "owner_name",
                    "owner_username", "owner_password_hash",
                ])
            return Response({
                "token": str(existing.token),
                "payment_url": existing.payment_url,
                "plan_name": plan.name,
                "amount_clp": plan.price_clp,
            })

        # Crear nueva sesión (con datos de negocio/owner si vienen)
        session = CheckoutSession.objects.create(
            email=email,
            plan=plan,
            amount_clp=plan.price_clp,
            expires_at=timezone.now() + td(hours=2),
            business_name=business_name,
            business_type=business_type,
            owner_name=owner_name,
            owner_username=owner_username,
            owner_password_hash=make_password(owner_password) if owner_password else "",
        )

        result = create_checkout_payment_link(session)

        if not result.get("success"):
            session.delete()
            # No exponer mensajes técnicos del gateway al usuario final.
            logger.error("Flow checkout creation failed: %s", result.get("error"))
            return Response(
                {"detail": "El sistema de pagos no responde en este momento. Intenta de nuevo en 1 minuto. Si el problema continúa, escríbenos a pulstock.admin@gmail.com."},
                status=502,
            )

        return Response({
            "token": str(session.token),
            "payment_url": result["payment_url"],
            "plan_name": plan.name,
            "amount_clp": plan.price_clp,
        })


class CheckoutStatusView(APIView):
    """GET /api/billing/checkout/status/?token=UUID — Verifica estado del pago.

    Este endpoint es público y solo sirve para hacer polling de estado.
    La creación de la cuenta SOLO sucede en el webhook (race-safe). Si el
    webhook falló, existe un fallback explícito que solo corre si el pago
    lleva >30s en estado PAID sin crearse la cuenta — evita que un atacante
    con el token UUID pueda forzar la creación antes que el usuario legítimo.
    """
    permission_classes = [AllowAny]
    throttle_classes = [WebhookRateThrottle]

    def get(self, request):
        token = request.query_params.get("token", "")
        if not token:
            return Response({"detail": "Falta el código de la sesión. Empieza una nueva desde la página de planes."}, status=400)

        try:
            session = CheckoutSession.objects.select_related("plan").get(token=token)
        except (CheckoutSession.DoesNotExist, ValueError):
            return Response({"detail": "Esta sesión de pago no existe o fue eliminada. Inicia una nueva desde la página de planes."}, status=404)

        # Auto-expire
        if session.is_expired:
            session.status = CheckoutSession.STATUS_EXPIRED
            session.save(update_fields=["status"])

        # Fallback: si el webhook no llegó, creamos la cuenta acá — pero solo
        # después de 30s en PAID (el webhook llega en <5s normalmente, esto es
        # red de seguridad, no fast path).
        if (session.status == CheckoutSession.STATUS_PAID
                and session.business_name
                and session.owner_username
                and session.owner_password_hash):
            from datetime import timedelta as _td
            webhook_grace = timezone.now() - _td(seconds=30)
            # Usamos completed_at como proxy de "hace cuánto pasó a PAID".
            # Si no hay marca de tiempo útil, igual intentamos (caso raro).
            session_age = session.updated_at if hasattr(session, "updated_at") else session.created_at
            if session_age and session_age < webhook_grace:
                try:
                    _auto_create_checkout_account(session)
                    session.refresh_from_db()
                except Exception as e:
                    logger.exception("Status view auto-create failed: %s", e)

        # Mask email: j***@domain.cl
        parts = session.email.split("@")
        masked = parts[0][0] + "***@" + parts[1] if len(parts) == 2 and parts[0] else session.email

        return Response({
            "status": session.status,
            "plan_name": session.plan.name,
            "plan_key": session.plan.key,
            "email_masked": masked,
            "amount_clp": session.amount_clp,
            "username": session.owner_username if session.status == CheckoutSession.STATUS_COMPLETED else "",
        })


class CheckoutCompleteView(APIView):
    """POST /api/billing/checkout/complete/ — Crea cuenta tras pago confirmado."""
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        from django.db import transaction
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.utils.text import slugify
        from rest_framework_simplejwt.tokens import RefreshToken
        from api.auth_views import _set_token_cookies
        from core.models import Tenant, User, Warehouse
        from stores.models import Store

        token = (request.data.get("token") or "").strip()
        password = request.data.get("password") or ""
        full_name = (request.data.get("full_name") or "").strip()
        business_name = (request.data.get("business_name") or "").strip()
        business_type = (request.data.get("business_type") or "").strip()
        store_name = (request.data.get("store_name") or "").strip() or "Mi Local"
        warehouses = request.data.get("warehouses") or []

        # Validate token & session
        try:
            session = CheckoutSession.objects.select_related("plan").get(token=token)
        except (CheckoutSession.DoesNotExist, ValueError):
            return Response({"detail": "Esta sesión de pago no existe o fue eliminada. Inicia una nueva desde la página de planes."}, status=404)

        if session.status == CheckoutSession.STATUS_COMPLETED:
            return Response({"detail": "Tu cuenta ya está creada. Inicia sesión con tu email y contraseña."}, status=409)
        if session.status != CheckoutSession.STATUS_PAID:
            return Response({"detail": "Aún no recibimos la confirmación del pago. Espera unos segundos y vuelve a intentar."}, status=402)

        # Validate fields
        errors = {}
        if not password:
            errors["password"] = "La contraseña es obligatoria."
        else:
            try:
                validate_password(password)
            except DjangoValidationError as e:
                errors["password"] = " ".join(e.messages)
        if not full_name:
            errors["full_name"] = "Tu nombre es obligatorio."
        if not business_name:
            errors["business_name"] = "El nombre de tu negocio es obligatorio."

        email = session.email
        if User.objects.filter(email=email).exists():
            errors["email"] = "Ya existe una cuenta con este email. Inicia sesión."

        if errors:
            return Response({"errors": errors}, status=400)

        # Generate unique slug
        base_slug = slugify(business_name)[:60] or "negocio"
        slug = base_slug
        counter = 1
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        try:
            with transaction.atomic():
                # 1. Tenant (skip auto-subscription)
                tenant = Tenant(name=business_name, slug=slug, is_active=True)
                tenant._skip_default_store = True
                tenant._skip_subscription = True
                tenant.save()

                # 2. Store + Warehouse(s)
                store = Store.objects.create(
                    tenant=tenant, name=store_name,
                    code=f"{slug}-1", is_active=True,
                )
                wh_name = warehouses[0] if warehouses else "Bodega Principal"
                warehouse = Warehouse.objects.create(
                    tenant=tenant, store=store,
                    name=(wh_name or "").strip() or "Bodega Principal",
                    is_active=True,
                )
                for extra_wh in warehouses[1:]:
                    if (extra_wh or "").strip():
                        Warehouse.objects.create(
                            tenant=tenant, store=store,
                            name=extra_wh.strip(), is_active=True,
                        )

                tenant.default_warehouse = warehouse
                tenant.save(update_fields=["default_warehouse"])
                store.default_warehouse = warehouse
                store.save(update_fields=["default_warehouse"])

                # 3. Seed units
                try:
                    from catalog.management.commands.seed_units import seed_units_for_tenant
                    seed_units_for_tenant(tenant)
                except Exception as e:
                    logger.warning("seed_units falló para tenant=%s: %s", tenant.pk, e)

                # 4. User
                user = User.objects.create_user(
                    username=email, email=email, password=password,
                    first_name=first_name, last_name=last_name,
                    tenant=tenant, active_store=store,
                )
                user.role = "owner"
                user.save(update_fields=["role"])

                # 5. Subscription (ACTIVE, no trial)
                now = timezone.now()
                sub = Subscription.objects.create(
                    tenant=tenant,
                    plan=session.plan,
                    status=Subscription.Status.ACTIVE,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )

                # 6. Invoice (PAID)
                invoice = Invoice.objects.create(
                    subscription=sub,
                    status=Invoice.Status.PAID,
                    amount_clp=session.amount_clp,
                    period_start=now.date(),
                    period_end=(now + timedelta(days=30)).date(),
                    gateway="flow",
                    gateway_order_id=session.gateway_order_id,
                    gateway_tx_id=session.gateway_tx_id,
                    paid_at=now,
                )

                # 7. PaymentAttempt
                PaymentAttempt.objects.create(
                    invoice=invoice,
                    result=PaymentAttempt.Result.SUCCESS,
                    gateway="flow",
                    raw={"checkout_session": str(session.token)},
                )

                # 8. Mark session completed
                session.status = CheckoutSession.STATUS_COMPLETED
                session.tenant = tenant
                session.completed_at = now
                session.save(update_fields=["status", "tenant", "completed_at"])

            # Email de bienvenida — fuera del atomic. La cuenta YA está creada
            # y commiteada; un fallo de SMTP no debe abortear nada.
            try:
                from billing.tasks import _send_welcome_email
                _send_welcome_email(user, tenant, session.plan)
            except Exception as e:
                logger.warning(
                    "Welcome email falló (cuenta YA creada OK, no afecta): %s", e,
                )

            # JWT tokens
            refresh = RefreshToken.for_user(user)
            access_str = str(refresh.access_token)
            refresh_str = str(refresh)

            response = Response({
                "detail": "Cuenta creada exitosamente.",
                "user": {"id": user.id, "email": user.email, "full_name": full_name},
                "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
                "store": {"id": store.id, "name": store.name},
                "tokens": {"access": access_str},
            }, status=201)
            _set_token_cookies(response, access_str, refresh_str)
            return response

        except (IntegrityError, ValueError, TypeError) as e:
            logger.exception("Error en checkout complete")
            return Response(
                {"detail": "No se pudo crear la cuenta. Intenta de nuevo."},
                status=500,
            )


@method_decorator(csrf_exempt, name="dispatch")
class FlowCheckoutWebhookView(APIView):
    """
    POST /api/billing/webhook/flow-checkout/ — Webhook de Flow para pagos checkout.

    Protocolo igual que FlowWebhookView pero para CheckoutSession (pre-registro).
    Incluye: HMAC verify, amount validation, select_for_update, expires_at check.
    """
    permission_classes = [AllowAny]
    throttle_classes = [WebhookRateThrottle]

    def post(self, request):
        from django.db import transaction as db_transaction

        token = request.data.get("token") or request.POST.get("token", "")
        if not token:
            return Response({"detail": "Missing token"}, status=400)

        payment_data = get_payment_status(token)

        # HMAC verify (defensa en profundidad)
        if not _flow_webhook_verify_signature(payment_data):
            logger.warning("Checkout webhook: firma HMAC inválida token=%s", token[:20])
            return Response({"detail": "Firma inválida."}, status=status.HTTP_403_FORBIDDEN)

        flow_status = payment_data.get("status")
        commerce_order = str(payment_data.get("commerceOrder", ""))
        flow_order = payment_data.get("flowOrder", "")

        if flow_status == -1:
            logger.error("Checkout webhook: error getStatus token=%s: %s",
                         token[:20], payment_data.get("error"))
            return Response(
                {"detail": "Error consultando estado de pago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if not isinstance(flow_status, int):
            logger.error("Checkout webhook: flow_status inválido %r", flow_status)
            return Response({"detail": "Invalid status."}, status=status.HTTP_502_BAD_GATEWAY)

        # Parse CS-{id} format
        if not commerce_order.startswith("CS-"):
            logger.warning("Checkout webhook: commerceOrder no empieza con CS-: %s",
                           commerce_order)
            return Response({"detail": "Invalid commerceOrder"}, status=400)
        try:
            session_id = int(commerce_order.replace("CS-", ""))
        except ValueError:
            return Response({"detail": "Invalid commerceOrder format"}, status=400)

        # ── Lock de la sesión para evitar race entre webhooks simultáneos y el GET /status ──
        with db_transaction.atomic():
            try:
                session = (
                    CheckoutSession.objects
                    .select_for_update()
                    .select_related("plan")
                    .get(pk=session_id)
                )
            except CheckoutSession.DoesNotExist:
                logger.warning("Checkout webhook: session #%d not found", session_id)
                return Response({"detail": "Session not found"}, status=404)

            # Idempotencia: si ya está completed, no hacemos nada
            if session.status == CheckoutSession.STATUS_COMPLETED:
                return Response({"ok": True, "detail": "already completed"})

            # Sesiones expiradas no se pueden pagar
            if session.is_expired:
                logger.warning("Checkout webhook: session #%d expirada, ignorando", session.pk)
                if session.status == CheckoutSession.STATUS_PENDING:
                    session.status = CheckoutSession.STATUS_EXPIRED
                    session.save(update_fields=["status"])
                return Response({"ok": True, "detail": "expired"})

            if flow_status == 2:
                # Validar monto (defensa contra amount tampering)
                if not _flow_amount_matches(payment_data, int(session.amount_clp)):
                    logger.error(
                        "Checkout webhook: AMOUNT MISMATCH session=#%d esperado=%d CLP "
                        "recibido=%s %s",
                        session.pk, int(session.amount_clp),
                        payment_data.get("amount"), payment_data.get("currency"),
                    )
                    return Response(
                        {"detail": "Amount mismatch."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if session.status == CheckoutSession.STATUS_PENDING:
                    session.status = CheckoutSession.STATUS_PAID
                    session.gateway_tx_id = str(flow_order)
                    session.save(update_fields=["status", "gateway_tx_id"])
                    logger.info("Checkout webhook: session #%d marcada como PAID", session.pk)

                # Auto-create account si tenemos los datos (dentro del lock).
                # Pasamos payment_data para que el Invoice creado guarde los
                # detalles de la tarjeta usada (last4, brand, media, etc.).
                if (session.status == CheckoutSession.STATUS_PAID
                        and session.business_name
                        and session.owner_username
                        and session.owner_password_hash):
                    try:
                        _auto_create_checkout_account(session, payment_data=payment_data)
                    except Exception as e:
                        logger.exception("Auto-create account failed for session #%d: %s",
                                         session.pk, e)

            elif flow_status in (3, 4):
                # Rechazado o anulado — marcamos PENDING todavía para que el
                # usuario pueda reintentar (no EXPIRED que suena a timeout).
                # Actualmente el modelo no tiene STATUS_REJECTED, usamos EXPIRED
                # por compatibilidad pero con un error_msg claro en logs.
                if session.status == CheckoutSession.STATUS_PENDING:
                    session.status = CheckoutSession.STATUS_EXPIRED
                    session.save(update_fields=["status"])
                    logger.warning(
                        "Checkout webhook: pago rechazado session #%d status=%d",
                        session.pk, flow_status,
                    )

            # flow_status == 1 (pendiente) → no-op, Flow reintentará

        return Response({"ok": True})
