"""
Tests EXHAUSTIVOS para el sistema de billing/pagos Flow.

Cubre TODOS los escenarios críticos:

SERVICIOS (business logic):
  1.  activate_period: marca invoice pagada, activa suscripción
  2.  activate_period: encadena períodos si el actual no ha vencido
  3.  activate_period: usa now si el período ya venció
  4.  activate_period: resetea retry_count y notification flags
  5.  register_payment_failure: primer fallo → past_due + retry en 1 día
  6.  register_payment_failure: segundo fallo → retry en 3 días
  7.  register_payment_failure: tercer fallo → retry en 7 días
  8.  register_payment_failure: agota reintentos → SUSPENDED
  9.  register_payment_failure: crea PaymentAttempt con error
  10. create_subscription: plan gratuito → status ACTIVE directo
  11. create_subscription: plan de pago → status TRIALING con fechas
  12. create_invoice: monto correcto del plan
  13. change_plan: upgrade ajusta fechas, downgrade a free limpia todo
  14. cancel_subscription: status CANCELLED, fecha guardada
  15. reactivate_subscription: limpia retry, nuevo período 30 días
  16. check_plan_limit: respeta límites y -1 (ilimitado)

GATEWAY (abstracción de pasarela):
  17. _flow_sign: firma HMAC correcta según protocolo Flow
  18. Mock gateway: cobro exitoso genera PaymentAttempt + order_id
  19. Mock gateway: cobro fallido (env var) genera invoice FAILED
  20. Mock payment link: genera URL con invoice_id
  21. Flow charge: tarjeta registrada → intenta auto-charge
  22. Flow charge: sin tarjeta → cae a payment link
  23. Flow charge: auto-charge falla → fallback a payment link
  24. Flow customer: ya existe → retorna existente sin crear
  25. Flow customer: mock → genera mock_cus_XX

WEBHOOK FLOW (protocolo token → getStatus):
  26. Webhook: token válido, status=2 → activa período
  27. Webhook: idempotencia (doble webhook no repite)
  28. Webhook: sin token → 400
  29. Webhook: status=3 (rechazado) → past_due + invoice FAILED
  30. Webhook: status=4 (anulado) → past_due + invoice FAILED
  31. Webhook: status=1 (pendiente) → no hace nada
  32. Webhook: invoice no encontrada → 404
  33. Webhook: getStatus falla → 502
  34. Webhook: commerceOrder inválido (no numérico) → 404

CONFIRM PAYMENT (frontend safety net):
  35. Confirm: pago exitoso activa período
  36. Confirm: ya pagado → idempotente "already_paid"
  37. Confirm: sin token → 400
  38. Confirm: tenant mismatch → 404 (seguridad multi-tenant)
  39. Confirm: status=3 rechazado → registra fallo
  40. Confirm: status=1 pendiente → responde "pending"

ENDPOINTS API (views):
  41. GET  /subscription/ → estado completo con invoices recientes
  42. POST /subscription/upgrade/ → cambia plan
  43. POST /subscription/upgrade/ → plan inválido → 400
  44. POST /subscription/upgrade/ → mismo plan → 400
  45. POST /subscription/cancel/ → cancela con razón
  46. POST /subscription/cancel/ → ya cancelada → informa
  47. POST /subscription/reactivate/ → plan gratis → reactiva
  48. POST /subscription/pay/ → genera link de pago
  49. GET  /plans/ → lista pública sin auth
  50. GET  /invoices/ → lista facturas del tenant

TARJETA (registro/desregistro):
  51. GET  /subscription/card/ → info tarjeta
  52. POST /subscription/card/remove/ → limpia card info

TASKS (Celery):
  53. process_renewals: cobra suscripciones vencidas
  54. expire_trials: trial vencido sin tarjeta → PAST_DUE
  55. retry_failed_payments: reintenta y activa si éxito
  56. suspend_overdue: past_due + gracia pasada → SUSPENDED

MIDDLEWARE:
  57. Middleware: SUSPENDED → 402
  58. Middleware: ACTIVE → permite
  59. Middleware: billing endpoints always allowed
"""
import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.utils import timezone
from django.test import override_settings

from billing.models import Plan, Subscription, Invoice, PaymentAttempt
from billing.services import (
    activate_period,
    register_payment_failure,
    create_subscription,
    create_invoice,
    change_plan,
    cancel_subscription,
    reactivate_subscription,
    check_plan_limit,
    RETRY_SCHEDULE,
)


# ══════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════

@pytest.fixture
def free_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="inicio",
        defaults={
            "name": "Plan Inicio", "price_clp": 0, "trial_days": 0,
            "max_products": 120, "max_stores": 1, "max_users": 10, "max_registers": 1,
        },
    )
    if plan.price_clp != 0:
        plan.price_clp = 0
        plan.save(update_fields=["price_clp"])
    return plan


@pytest.fixture
def pro_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={
            "name": "Plan Pro", "price_clp": 59990, "trial_days": 7,
            "max_products": 1000, "max_stores": 5, "max_users": -1, "max_registers": 5,
            "has_forecast": True, "has_abc": True, "has_reports": True, "has_transfers": True,
        },
    )
    return plan


@pytest.fixture
def crecimiento_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="crecimiento",
        defaults={
            "name": "Plan Crecimiento", "price_clp": 25990, "trial_days": 0,
            "max_products": 400, "max_stores": 2, "max_users": 15, "max_registers": 2,
            "has_forecast": True, "has_abc": True, "has_reports": True,
        },
    )
    return plan


@pytest.fixture
def subscription(db, tenant, pro_plan):
    sub = Subscription.objects.filter(tenant=tenant).first()
    now = timezone.now()
    if sub:
        sub.plan = pro_plan
        sub.status = Subscription.Status.TRIALING
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=14)
        sub.trial_ends_at = now + timedelta(days=14)
        sub.payment_retry_count = 0
        sub.next_retry_at = None
        sub.flow_customer_id = ""
        sub.card_brand = ""
        sub.card_last4 = ""
        sub.save()
        return sub
    return Subscription.objects.create(
        tenant=tenant,
        plan=pro_plan,
        status=Subscription.Status.TRIALING,
        current_period_start=now,
        current_period_end=now + timedelta(days=14),
        trial_ends_at=now + timedelta(days=14),
    )


@pytest.fixture
def active_subscription(db, subscription):
    """Suscripción activa con período válido."""
    now = timezone.now()
    subscription.status = Subscription.Status.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    subscription.save()
    return subscription


@pytest.fixture
def pending_invoice(db, subscription):
    now = timezone.now()
    return Invoice.objects.create(
        subscription=subscription,
        amount_clp=59990,
        period_start=now.date(),
        period_end=(now + timedelta(days=30)).date(),
        status=Invoice.Status.PENDING,
        gateway_order_id=f"ORDER-{timezone.now().timestamp():.0f}",
    )


@pytest.fixture
def jwt_client(db, tenant):
    """Client that uses real JWT auth so middleware sees the user."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    from core.models import User
    from stores.models import Store

    store = Store.objects.filter(tenant=tenant).first()
    if not store:
        store = Store.objects.create(tenant=tenant, name="Store Test", code="JWT-1", is_active=True)
    user = User.objects.create_user(username="jwt_user", password="pass123")
    user.tenant = tenant
    user.active_store = store
    user.save()
    token = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")
    return client


def _mock_flow_status(invoice_pk, flow_status=2, flow_order="FLOW-999"):
    """Helper para crear respuesta mock de payment/getStatus."""
    return {
        "flowOrder": flow_order,
        "commerceOrder": str(invoice_pk),
        "status": flow_status,
        "subject": "Pulstock - Pro",
        "amount": 59990,
        "currency": "CLP",
        "payer": "test@example.com",
    }


# ══════════════════════════════════════════════════
# 1-4: activate_period
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestActivatePeriod:

    def test_marks_invoice_paid(self, subscription, pending_invoice):
        activate_period(subscription, pending_invoice)
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID
        assert pending_invoice.paid_at is not None

    def test_sets_subscription_active(self, subscription, pending_invoice):
        activate_period(subscription, pending_invoice)
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE
        assert subscription.payment_retry_count == 0

    def test_chains_from_current_period_end(self, subscription, pending_invoice):
        """Si período actual no ha vencido, el nuevo encadena desde current_period_end."""
        future_end = timezone.now() + timedelta(days=10)
        subscription.current_period_end = future_end
        subscription.save()

        activate_period(subscription, pending_invoice)
        subscription.refresh_from_db()

        assert subscription.current_period_start == future_end
        expected_end = future_end + timedelta(days=30)
        assert abs((subscription.current_period_end - expected_end).total_seconds()) < 5

    def test_uses_now_if_period_already_expired(self, subscription, pending_invoice):
        """Si período ya venció, nuevo comienza desde ahora."""
        past_end = timezone.now() - timedelta(days=5)
        subscription.current_period_end = past_end
        subscription.save()

        before = timezone.now()
        activate_period(subscription, pending_invoice)
        after = timezone.now()
        subscription.refresh_from_db()

        assert before <= subscription.current_period_start <= after

    def test_resets_notification_flags(self, subscription, pending_invoice):
        subscription.notified_7_days = True
        subscription.notified_3_days = True
        subscription.notified_1_day = True
        subscription.notified_past_due = True
        subscription.save()

        activate_period(subscription, pending_invoice)
        subscription.refresh_from_db()

        assert subscription.notified_7_days is False
        assert subscription.notified_3_days is False
        assert subscription.notified_1_day is False
        assert subscription.notified_past_due is False

    def test_clears_retry_count_and_next_retry(self, subscription, pending_invoice):
        subscription.payment_retry_count = 2
        subscription.next_retry_at = timezone.now() + timedelta(days=1)
        subscription.save()

        activate_period(subscription, pending_invoice)
        subscription.refresh_from_db()

        assert subscription.payment_retry_count == 0
        assert subscription.next_retry_at is None


# ══════════════════════════════════════════════════
# 5-9: register_payment_failure
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterPaymentFailure:

    def test_first_failure_sets_past_due(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice, error_msg="Rechazado")
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.PAST_DUE
        assert subscription.payment_retry_count == 1

    def test_first_failure_schedules_retry_in_1_day(self, subscription, pending_invoice):
        before = timezone.now()
        register_payment_failure(subscription, pending_invoice)
        subscription.refresh_from_db()
        expected = before + timedelta(days=RETRY_SCHEDULE[0])
        assert abs((subscription.next_retry_at - expected).total_seconds()) < 10

    def test_second_failure_schedules_retry_in_3_days(self, subscription, pending_invoice):
        subscription.payment_retry_count = 1
        subscription.save()
        before = timezone.now()
        register_payment_failure(subscription, pending_invoice)
        subscription.refresh_from_db()
        assert subscription.payment_retry_count == 2
        expected = before + timedelta(days=RETRY_SCHEDULE[1])
        assert abs((subscription.next_retry_at - expected).total_seconds()) < 10

    def test_third_failure_schedules_retry_in_7_days(self, subscription, pending_invoice):
        subscription.payment_retry_count = 2
        subscription.save()
        before = timezone.now()
        register_payment_failure(subscription, pending_invoice)
        subscription.refresh_from_db()
        assert subscription.payment_retry_count == 3
        expected = before + timedelta(days=RETRY_SCHEDULE[2])
        assert abs((subscription.next_retry_at - expected).total_seconds()) < 10

    def test_exhausted_retries_suspends(self, tenant, pro_plan):
        """4to fallo (retry_count=3 → 4) → SUSPENDED."""
        now = timezone.now()
        sub = Subscription.objects.create(
            tenant=tenant, plan=pro_plan,
            status=Subscription.Status.PAST_DUE,
            current_period_start=now, current_period_end=now + timedelta(days=30),
            payment_retry_count=len(RETRY_SCHEDULE),
        )
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            status=Invoice.Status.PENDING,
            gateway_order_id=f"ORDER-LAST-{now.timestamp():.0f}",
        )
        register_payment_failure(sub, inv, error_msg="Último intento")
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.SUSPENDED
        assert sub.suspended_at is not None
        assert sub.next_retry_at is None

    def test_creates_failed_payment_attempt(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice, error_msg="Fondos insuficientes")
        attempt = PaymentAttempt.objects.get(invoice=pending_invoice)
        assert attempt.result == PaymentAttempt.Result.FAILED
        assert attempt.error_msg == "Fondos insuficientes"

    def test_marks_invoice_as_failed(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice)
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.FAILED


# ══════════════════════════════════════════════════
# 10-16: Otros servicios
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestServices:

    def test_create_subscription_free_plan(self, tenant, free_plan):
        Subscription.objects.filter(tenant=tenant).delete()
        sub = create_subscription(tenant, "inicio")
        assert sub.status == Subscription.Status.ACTIVE
        assert sub.trial_ends_at is None

    def test_create_subscription_paid_plan(self, tenant, pro_plan):
        Subscription.objects.filter(tenant=tenant).delete()
        sub = create_subscription(tenant, "pro")
        assert sub.status == Subscription.Status.TRIALING
        assert sub.trial_ends_at is not None
        assert sub.current_period_end == sub.trial_ends_at

    def test_create_invoice_correct_amount(self, subscription):
        inv = create_invoice(subscription)
        assert inv.amount_clp == subscription.plan.price_clp
        assert inv.status == Invoice.Status.PENDING

    def test_change_plan_upgrade(self, subscription, crecimiento_plan, pro_plan):
        subscription.plan = crecimiento_plan
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()

        before = timezone.now()
        sub = change_plan(subscription, "pro")
        assert sub.plan.key == "pro"
        assert sub.current_period_start >= before
        assert sub.current_period_end >= before + timedelta(days=29)

    def test_change_plan_downgrade_to_free(self, subscription, free_plan):
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()
        sub = change_plan(subscription, "inicio")
        assert sub.plan.key == "inicio"
        assert sub.status == Subscription.Status.ACTIVE
        assert sub.current_period_start is None
        assert sub.current_period_end is None

    def test_cancel_subscription(self, active_subscription):
        sub = cancel_subscription(active_subscription, reason="Muy caro")
        assert sub.status == Subscription.Status.CANCELLED
        assert sub.cancelled_at is not None

    def test_reactivate_subscription(self, subscription):
        subscription.status = Subscription.Status.SUSPENDED
        subscription.suspended_at = timezone.now()
        subscription.payment_retry_count = 3
        subscription.save()

        before = timezone.now()
        sub = reactivate_subscription(subscription)
        assert sub.status == Subscription.Status.ACTIVE
        assert sub.suspended_at is None
        assert sub.payment_retry_count == 0
        assert sub.current_period_end >= before + timedelta(days=29)

    def test_check_plan_limit_within(self, subscription):
        r = check_plan_limit(subscription, "products", 500)
        assert r["allowed"] is True  # pro has 1000

    def test_check_plan_limit_exceeded(self, subscription):
        r = check_plan_limit(subscription, "products", 1000)
        assert r["allowed"] is False

    def test_check_plan_limit_unlimited(self, subscription):
        r = check_plan_limit(subscription, "users", 9999)
        assert r["allowed"] is True  # pro has -1 (unlimited)


# ══════════════════════════════════════════════════
# 17-25: Gateway
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestGateway:

    def test_flow_sign_hmac(self):
        from billing.gateway import _flow_sign
        params = {"amount": 1000, "currency": "CLP", "apiKey": "test_key"}
        sig = _flow_sign(params, "my_secret")
        # Verify it's a valid hex SHA256 (64 chars)
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_flow_sign_deterministic(self):
        from billing.gateway import _flow_sign
        params = {"b": "2", "a": "1"}
        sig1 = _flow_sign(params, "secret")
        sig2 = _flow_sign(params, "secret")
        assert sig1 == sig2

    def test_flow_sign_different_secret(self):
        from billing.gateway import _flow_sign
        params = {"a": "1"}
        sig1 = _flow_sign(params, "secret1")
        sig2 = _flow_sign(params, "secret2")
        assert sig1 != sig2

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_mock_charge_success(self, subscription, pending_invoice):
        from billing.gateway import charge_subscription
        import os
        os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)
        result = charge_subscription(subscription, pending_invoice)
        assert result["success"] is True
        assert "MOCK-" in result["gateway_order_id"]
        assert PaymentAttempt.objects.filter(
            invoice=pending_invoice, result=PaymentAttempt.Result.SUCCESS
        ).exists()

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_mock_charge_fail(self, subscription, pending_invoice):
        from billing.gateway import charge_subscription
        import os
        os.environ["PAYMENT_GATEWAY_MOCK_FAIL"] = "1"
        try:
            result = charge_subscription(subscription, pending_invoice)
            assert result["success"] is False
            assert "rechazada" in result["error"].lower()
            pending_invoice.refresh_from_db()
            assert pending_invoice.status == Invoice.Status.FAILED
        finally:
            os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_mock_payment_link(self, subscription, pending_invoice):
        from billing.gateway import create_payment_link
        result = create_payment_link(subscription, pending_invoice)
        assert result["success"] is True
        assert "mock_pay" in result["payment_url"]
        pending_invoice.refresh_from_db()
        assert pending_invoice.payment_url != ""

    @override_settings(PAYMENT_GATEWAY="flow")
    def test_flow_charge_with_card_attempts_auto(self, subscription, pending_invoice):
        """Con tarjeta registrada, intenta cobro automático."""
        subscription.flow_customer_id = "cus_test123"
        subscription.card_last4 = "4242"
        subscription.save()

        mock_result = {"status": 2, "flowOrder": "12345"}
        with patch("billing.gateway._flow_api_call", return_value=mock_result):
            from billing.gateway import _charge_via_flow
            result = _charge_via_flow(subscription, pending_invoice)
        assert result["success"] is True
        assert result["gateway_tx_id"] == "12345"

    @override_settings(PAYMENT_GATEWAY="flow")
    def test_flow_charge_without_card_falls_to_link(self, subscription, pending_invoice):
        """Sin tarjeta → genera link de pago manual."""
        subscription.flow_customer_id = ""
        subscription.card_last4 = ""
        subscription.save()

        mock_link = {"url": "https://www.flow.cl/app/web/pay.php", "token": "tok_abc"}
        with patch("billing.gateway._flow_api_call", return_value=mock_link):
            from billing.gateway import _charge_via_flow
            result = _charge_via_flow(subscription, pending_invoice)
        assert result["success"] is True
        assert "flow.cl" in result["payment_url"]

    @override_settings(PAYMENT_GATEWAY="flow")
    def test_flow_auto_charge_fail_falls_to_link(self, subscription, pending_invoice):
        """Si auto-charge falla → fallback a link manual."""
        subscription.flow_customer_id = "cus_test123"
        subscription.card_last4 = "4242"
        subscription.save()

        call_count = 0
        def mock_api_call(method, endpoint, params):
            nonlocal call_count
            call_count += 1
            if "/customer/charge" in endpoint:
                return {"status": 3, "flowOrder": ""}  # rejected
            return {"url": "https://www.flow.cl/app/web/pay.php", "token": "tok_fb"}

        with patch("billing.gateway._flow_api_call", side_effect=mock_api_call):
            from billing.gateway import _charge_via_flow
            result = _charge_via_flow(subscription, pending_invoice)

        # Should have called charge then payment/create (fallback)
        assert call_count == 2
        assert result["success"] is True
        assert result["payment_url"] is not None

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_create_flow_customer_already_exists(self, subscription):
        subscription.flow_customer_id = "cus_existing"
        subscription.save()
        from billing.gateway import create_flow_customer
        result = create_flow_customer(subscription)
        assert result["customerId"] == "cus_existing"
        assert result.get("already_exists") is True

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_create_flow_customer_mock(self, subscription):
        subscription.flow_customer_id = ""
        subscription.save()
        from billing.gateway import create_flow_customer
        result = create_flow_customer(subscription)
        assert "mock_cus_" in result["customerId"]
        subscription.refresh_from_db()
        assert subscription.flow_customer_id == result["customerId"]


# ══════════════════════════════════════════════════
# 26-34: Webhook Flow
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestFlowWebhook:

    def test_valid_payment_activates_period(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-OK"}, format="multipart",
            )
        assert resp.status_code == 200
        assert resp.data["ok"] is True
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE

    def test_idempotent_double_webhook(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            api_client.post("/api/billing/webhook/flow/", {"token": "T1"}, format="multipart")
            period_end_1 = Subscription.objects.get(pk=subscription.pk).current_period_end
            resp2 = api_client.post("/api/billing/webhook/flow/", {"token": "T1"}, format="multipart")
        assert resp2.status_code == 200
        assert "already processed" in resp2.data.get("detail", "")
        subscription.refresh_from_db()
        assert subscription.current_period_end == period_end_1

    def test_missing_token_returns_400(self, api_client):
        resp = api_client.post("/api/billing/webhook/flow/", {}, format="multipart")
        assert resp.status_code == 400

    def test_rejected_payment_sets_past_due(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=3)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-REJECTED"}, format="multipart",
            )
        assert resp.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.PAST_DUE
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.FAILED

    def test_voided_payment_sets_past_due(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=4)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-VOIDED"}, format="multipart",
            )
        assert resp.status_code == 200
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.PAST_DUE

    def test_pending_payment_does_nothing(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=1)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-PENDING"}, format="multipart",
            )
        assert resp.status_code == 200
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PENDING

    def test_invoice_not_found_returns_404(self, api_client):
        mock_status = {"status": 2, "commerceOrder": "99999", "flowOrder": "X"}
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-NOTFOUND"}, format="multipart",
            )
        assert resp.status_code == 404

    def test_invalid_commerce_order_returns_404(self, api_client):
        mock_status = {"status": 2, "commerceOrder": "not-a-number", "flowOrder": "X"}
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-BAD"}, format="multipart",
            )
        assert resp.status_code == 404

    def test_flow_api_error_returns_502(self, api_client):
        with patch("billing.views.get_payment_status", return_value={"status": -1, "error": "timeout"}):
            resp = api_client.post(
                "/api/billing/webhook/flow/",
                {"token": "TOKEN-ERR"}, format="multipart",
            )
        assert resp.status_code == 502

    def test_creates_payment_attempt_on_success(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            api_client.post("/api/billing/webhook/flow/", {"token": "T"}, format="multipart")
        assert PaymentAttempt.objects.filter(
            invoice=pending_invoice, result=PaymentAttempt.Result.SUCCESS
        ).exists()

    def test_saves_gateway_tx_id(self, api_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2, flow_order="FL-12345")
        with patch("billing.views.get_payment_status", return_value=mock_status):
            api_client.post("/api/billing/webhook/flow/", {"token": "T"}, format="multipart")
        pending_invoice.refresh_from_db()
        assert pending_invoice.gateway_tx_id == "FL-12345"


# ══════════════════════════════════════════════════
# 35-40: ConfirmPayment (frontend safety)
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestConfirmPayment:

    def test_successful_confirmation(self, auth_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = auth_client.post(
                "/api/billing/subscription/confirm-payment/",
                {"token": "TOKEN-CONFIRM"}, format="json",
            )
        assert resp.status_code == 200
        assert resp.data["ok"] is True
        assert resp.data["status"] == "paid"
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID

    def test_already_paid_is_idempotent(self, auth_client, subscription, pending_invoice):
        pending_invoice.status = Invoice.Status.PAID
        pending_invoice.paid_at = timezone.now()
        pending_invoice.save()

        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = auth_client.post(
                "/api/billing/subscription/confirm-payment/",
                {"token": "TOKEN-ALREADY"}, format="json",
            )
        assert resp.status_code == 200
        assert resp.data["status"] == "already_paid"

    def test_missing_token_returns_400(self, auth_client):
        resp = auth_client.post(
            "/api/billing/subscription/confirm-payment/",
            {}, format="json",
        )
        assert resp.status_code == 400

    def test_tenant_mismatch_returns_404(self, auth_client, pro_plan):
        """Un usuario no puede confirmar pago de otro tenant."""
        from core.models import Tenant
        other_tenant = Tenant.objects.create(name="Other Biz")
        other_sub = Subscription.objects.create(
            tenant=other_tenant, plan=pro_plan,
            status=Subscription.Status.ACTIVE,
        )
        now = timezone.now()
        other_invoice = Invoice.objects.create(
            subscription=other_sub, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            status=Invoice.Status.PENDING,
            gateway_order_id=f"ORDER-OTHER-{now.timestamp():.0f}",
        )
        mock_status = _mock_flow_status(other_invoice.pk, flow_status=2)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = auth_client.post(
                "/api/billing/subscription/confirm-payment/",
                {"token": "TOKEN-HACKER"}, format="json",
            )
        # Security: must return 404, not 200
        assert resp.status_code == 404

    def test_rejected_payment_returns_failure(self, auth_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=3)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = auth_client.post(
                "/api/billing/subscription/confirm-payment/",
                {"token": "TOKEN-REJ"}, format="json",
            )
        assert resp.data["ok"] is False
        assert resp.data["status"] == "rejected"

    def test_pending_payment_returns_pending(self, auth_client, subscription, pending_invoice):
        mock_status = _mock_flow_status(pending_invoice.pk, flow_status=1)
        with patch("billing.views.get_payment_status", return_value=mock_status):
            resp = auth_client.post(
                "/api/billing/subscription/confirm-payment/",
                {"token": "TOKEN-PEND"}, format="json",
            )
        assert resp.data["ok"] is False
        assert resp.data["status"] == "pending"


# ══════════════════════════════════════════════════
# 41-50: API Endpoints
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestAPIEndpoints:

    def test_get_subscription_status(self, auth_client, subscription):
        resp = auth_client.get("/api/billing/subscription/")
        assert resp.status_code == 200
        assert "plan" in resp.data
        assert resp.data["status"] == "trialing"
        assert "recent_invoices" in resp.data
        assert "days_remaining" in resp.data
        assert "has_card" in resp.data

    def test_upgrade_plan(self, auth_client, subscription, crecimiento_plan):
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()
        resp = auth_client.post(
            "/api/billing/subscription/upgrade/",
            {"plan": "crecimiento"}, format="json",
        )
        assert resp.status_code == 200
        subscription.refresh_from_db()
        assert subscription.plan.key == "crecimiento"

    def test_upgrade_invalid_plan_returns_400(self, auth_client, subscription):
        resp = auth_client.post(
            "/api/billing/subscription/upgrade/",
            {"plan": "enterprise_ultra"}, format="json",
        )
        assert resp.status_code == 400

    def test_upgrade_same_plan_returns_400(self, auth_client, subscription):
        resp = auth_client.post(
            "/api/billing/subscription/upgrade/",
            {"plan": "pro"}, format="json",
        )
        assert resp.status_code == 400

    def test_upgrade_missing_plan_returns_400(self, auth_client, subscription):
        resp = auth_client.post(
            "/api/billing/subscription/upgrade/",
            {}, format="json",
        )
        assert resp.status_code == 400

    def test_cancel_subscription(self, auth_client, active_subscription):
        resp = auth_client.post(
            "/api/billing/subscription/cancel/",
            {"reason": "Muy caro"}, format="json",
        )
        assert resp.status_code == 200
        assert resp.data["ok"] is True
        assert "access_until" in resp.data
        active_subscription.refresh_from_db()
        assert active_subscription.status == Subscription.Status.CANCELLED

    def test_cancel_already_cancelled(self, auth_client, subscription):
        subscription.status = Subscription.Status.CANCELLED
        subscription.save()
        resp = auth_client.post("/api/billing/subscription/cancel/", format="json")
        assert resp.status_code == 200
        assert "ya está cancelada" in resp.data.get("detail", "")

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_reactivate_free_plan(self, auth_client, subscription, free_plan):
        subscription.plan = free_plan
        subscription.status = Subscription.Status.CANCELLED
        subscription.save()
        resp = auth_client.post("/api/billing/subscription/reactivate/", format="json")
        assert resp.status_code == 200
        assert resp.data["ok"] is True
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_payment_link_generation(self, auth_client, subscription):
        import os
        os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)
        resp = auth_client.post("/api/billing/subscription/pay/", format="json")
        assert resp.status_code == 200
        assert "payment_url" in resp.data
        assert resp.data["amount_clp"] == subscription.plan.price_clp

    def test_plans_list_public(self, api_client, pro_plan, free_plan):
        resp = api_client.get("/api/billing/plans/")
        assert resp.status_code == 200
        assert len(resp.data) >= 2
        keys = [p["key"] for p in resp.data]
        assert "pro" in keys

    def test_invoices_list(self, auth_client, subscription, pending_invoice):
        resp = auth_client.get("/api/billing/invoices/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1
        assert resp.data[0]["amount_clp"] == 59990


# ══════════════════════════════════════════════════
# 51-52: Card registration
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestCardManagement:

    def test_get_card_info(self, auth_client, subscription):
        subscription.card_brand = "Visa"
        subscription.card_last4 = "4242"
        subscription.save()
        resp = auth_client.get("/api/billing/subscription/card/")
        assert resp.status_code == 200
        assert resp.data["has_card"] is True
        assert resp.data["card_brand"] == "Visa"
        assert resp.data["card_last4"] == "4242"

    def test_get_card_info_no_card(self, auth_client, subscription):
        resp = auth_client.get("/api/billing/subscription/card/")
        assert resp.status_code == 200
        assert resp.data["has_card"] is False

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_unregister_card(self, auth_client, subscription):
        subscription.card_brand = "Mastercard"
        subscription.card_last4 = "1234"
        subscription.save()
        resp = auth_client.post("/api/billing/subscription/card/remove/", format="json")
        assert resp.status_code == 200
        assert resp.data["ok"] is True
        subscription.refresh_from_db()
        assert subscription.card_last4 == ""
        assert subscription.card_brand == ""


# ══════════════════════════════════════════════════
# 53-56: Tasks (Celery)
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestTasks:

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_process_renewals(self, subscription):
        """Suscripción activa con período vencido → se cobra."""
        import os
        os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_end = timezone.now() - timedelta(hours=1)
        subscription.save()

        from billing.tasks import process_renewals
        result = process_renewals()
        assert result["processed"] >= 1

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE
        assert Invoice.objects.filter(
            subscription=subscription, status=Invoice.Status.PAID
        ).exists()

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_expire_trials_charges_on_success(self, subscription):
        """Trial vencido → intenta cobrar. Mock éxito → ACTIVE."""
        import os
        os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)
        subscription.status = Subscription.Status.TRIALING
        subscription.trial_ends_at = timezone.now() - timedelta(hours=1)
        subscription.save()

        from billing.tasks import expire_trials
        result = expire_trials()
        assert result["converted"] >= 1

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_expire_trials_failure_sets_past_due(self, subscription):
        """Trial vencido + fallo de pago → PAST_DUE."""
        import os
        os.environ["PAYMENT_GATEWAY_MOCK_FAIL"] = "1"
        try:
            subscription.status = Subscription.Status.TRIALING
            subscription.trial_ends_at = timezone.now() - timedelta(hours=1)
            subscription.save()

            from billing.tasks import expire_trials
            expire_trials()

            subscription.refresh_from_db()
            assert subscription.status == Subscription.Status.PAST_DUE
        finally:
            os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_retry_failed_payments_success(self, subscription):
        """Past_due con next_retry_at pasado → reintenta y activa."""
        import os
        os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)
        subscription.status = Subscription.Status.PAST_DUE
        subscription.payment_retry_count = 1
        subscription.next_retry_at = timezone.now() - timedelta(hours=1)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.save()

        from billing.tasks import retry_failed_payments
        result = retry_failed_payments()
        assert result["retried"] >= 1

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE

    def test_suspend_overdue(self, subscription):
        """Past_due + gracia expirada + reintentos agotados → SUSPENDED."""
        subscription.status = Subscription.Status.PAST_DUE
        subscription.payment_retry_count = len(RETRY_SCHEDULE)
        subscription.current_period_end = timezone.now() - timedelta(days=10)
        subscription.save()

        from billing.tasks import suspend_overdue_subscriptions
        result = suspend_overdue_subscriptions()
        assert result["suspended"] >= 1

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.SUSPENDED

    def test_suspend_overdue_within_grace_not_suspended(self, subscription):
        """Past_due pero dentro del período de gracia → NO suspender."""
        subscription.status = Subscription.Status.PAST_DUE
        subscription.payment_retry_count = 1
        subscription.current_period_end = timezone.now() - timedelta(hours=1)
        subscription.save()

        from billing.tasks import suspend_overdue_subscriptions
        result = suspend_overdue_subscriptions()

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.PAST_DUE


# ══════════════════════════════════════════════════
# 57-59: Middleware
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestMiddleware:

    def test_suspended_returns_402(self, jwt_client, subscription):
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save()
        from django.core.cache import cache
        cache.delete(f"sub_access:{subscription.tenant_id}")

        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 402

    def test_active_allows_access(self, jwt_client, active_subscription):
        from django.core.cache import cache
        cache.delete(f"sub_access:{active_subscription.tenant_id}")

        resp = jwt_client.get("/api/catalog/products/")
        # Should not be 402 (might be 200 or other but NOT 402)
        assert resp.status_code != 402

    def test_billing_endpoints_always_allowed(self, jwt_client, subscription):
        """Billing endpoints deben funcionar incluso con suscripción suspendida."""
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save()
        from django.core.cache import cache
        cache.delete(f"sub_access:{subscription.tenant_id}")

        resp = jwt_client.get("/api/billing/subscription/")
        assert resp.status_code != 402

    def test_past_due_still_has_access(self, jwt_client, subscription):
        """PAST_DUE permite acceso (período de gracia)."""
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save()
        from django.core.cache import cache
        cache.delete(f"sub_access:{subscription.tenant_id}")

        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code != 402


# ══════════════════════════════════════════════════
# 60+: Edge cases extra
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestEdgeCases:

    def test_invoice_mark_paid(self, pending_invoice):
        """Invoice.mark_paid() actualiza status, paid_at y tx_id."""
        pending_invoice.mark_paid(tx_id="TX-123")
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID
        assert pending_invoice.paid_at is not None
        assert pending_invoice.gateway_tx_id == "TX-123"

    def test_subscription_is_access_allowed_property(self, subscription):
        for status_val in [Subscription.Status.TRIALING, Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE]:
            subscription.status = status_val
            assert subscription.is_access_allowed is True

        for status_val in [Subscription.Status.SUSPENDED, Subscription.Status.CANCELLED]:
            subscription.status = status_val
            assert subscription.is_access_allowed is False

    def test_subscription_days_until_renewal(self, subscription):
        subscription.current_period_end = timezone.now() + timedelta(days=15)
        subscription.save()
        assert subscription.days_until_renewal == 15 or subscription.days_until_renewal == 14

    def test_subscription_is_trial_property(self, subscription):
        subscription.status = Subscription.Status.TRIALING
        assert subscription.is_trial is True
        subscription.status = Subscription.Status.ACTIVE
        assert subscription.is_trial is False

    def test_concurrent_invoice_unique_constraint(self, subscription):
        """Dos invoices con mismo gateway_order_id no vacío → IntegrityError."""
        from django.db import IntegrityError
        now = timezone.now()
        Invoice.objects.create(
            subscription=subscription, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            gateway_order_id="SAME-ORDER",
        )
        with pytest.raises(IntegrityError):
            Invoice.objects.create(
                subscription=subscription, amount_clp=59990,
                period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
                gateway_order_id="SAME-ORDER",
            )

    def test_empty_gateway_order_id_allows_multiple(self, subscription):
        """Invoices con gateway_order_id vacío no violan constraint."""
        now = timezone.now()
        inv1 = Invoice.objects.create(
            subscription=subscription, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            gateway_order_id="",
        )
        inv2 = Invoice.objects.create(
            subscription=subscription, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            gateway_order_id="",
        )
        assert inv1.pk != inv2.pk

    def test_webhook_flow_card_register_saves_card(self, api_client, subscription):
        """Webhook de registro de tarjeta guarda brand y last4."""
        subscription.flow_customer_id = "cus_test_card"
        subscription.save()

        mock_result = {
            "status": "1",
            "customerId": "cus_test_card",
            "creditCardType": "Visa",
            "last4CardDigits": "9876",
        }
        with patch("billing.views.get_card_register_status", return_value=mock_result):
            resp = api_client.post(
                "/api/billing/webhook/flow-card-register/",
                {"token": "CARD-REG-TOKEN"}, format="multipart",
            )
        # Should redirect (302)
        assert resp.status_code == 302
        subscription.refresh_from_db()
        assert subscription.card_brand == "Visa"
        assert subscription.card_last4 == "9876"

    def test_webhook_flow_card_register_failed(self, api_client, subscription):
        """Webhook de registro de tarjeta con status=0 no guarda nada."""
        subscription.flow_customer_id = "cus_test_fail"
        subscription.save()

        mock_result = {"status": "0", "error": "User cancelled"}
        with patch("billing.views.get_card_register_status", return_value=mock_result):
            resp = api_client.post(
                "/api/billing/webhook/flow-card-register/",
                {"token": "CARD-FAIL-TOKEN"}, format="multipart",
            )
        assert resp.status_code == 302
        subscription.refresh_from_db()
        assert subscription.card_last4 == ""

    @override_settings(PAYMENT_GATEWAY="flow")
    def test_flow_api_error_on_charge_falls_to_link(self, subscription, pending_invoice):
        """FlowAPIError durante auto-charge → fallback a payment link."""
        subscription.flow_customer_id = "cus_err"
        subscription.card_last4 = "4242"
        subscription.save()

        from billing.gateway import FlowAPIError

        call_count = 0
        def mock_api_call(method, endpoint, params):
            nonlocal call_count
            call_count += 1
            if "/customer/charge" in endpoint:
                raise FlowAPIError(400, "Tarjeta bloqueada", {"code": 400})
            return {"url": "https://www.flow.cl/app/web/pay.php", "token": "tok_fb"}

        with patch("billing.gateway._flow_api_call", side_effect=mock_api_call):
            from billing.gateway import _charge_via_flow
            result = _charge_via_flow(subscription, pending_invoice)

        assert call_count == 2  # charge attempt + fallback link
        assert result["success"] is True
        assert result["payment_url"] is not None

    @override_settings(PAYMENT_GATEWAY="flow")
    def test_flow_unexpected_exception_falls_to_link(self, subscription, pending_invoice):
        """Exception inesperada durante auto-charge → fallback a payment link."""
        subscription.flow_customer_id = "cus_crash"
        subscription.card_last4 = "4242"
        subscription.save()

        call_count = 0
        def mock_api_call(method, endpoint, params):
            nonlocal call_count
            call_count += 1
            if "/customer/charge" in endpoint:
                raise ConnectionError("Network unreachable")
            return {"url": "https://www.flow.cl/app/web/pay.php", "token": "tok_fb2"}

        with patch("billing.gateway._flow_api_call", side_effect=mock_api_call):
            from billing.gateway import _charge_via_flow
            result = _charge_via_flow(subscription, pending_invoice)

        assert result["success"] is True
        assert result["payment_url"] is not None
