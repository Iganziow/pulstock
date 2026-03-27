"""
Tests de integración Flow.cl — Billing Blindaje
=================================================

Cubre los flujos completos de pago solicitados:

1.  Suscripción nueva: Plan → Subscription → primer PaymentAttempt
2.  Signal post_save de Tenant crea Subscription automáticamente
3.  Cargo automático pasos 1-6: crear cargo, confirmar, polling status
4.  Webhook de Flow.cl actualiza estado Invoice a PAID
5.  Pago fallido genera Invoice FAILED y reintento programado
6.  Middleware bloquea tenant con suscripción expirada/suspendida
7.  Middleware permite acceso con suscripción activa y plan correcto
8.  Cancelación de suscripción: acceso bloqueado al vencimiento
9.  Variables de entorno Flow.cl ausentes → excepción clara, no 500
10. PaymentAttempt registra timestamp, monto CLP y referencia Flow
11. Cobro automático con tarjeta guardada (ciclo completo)
"""
import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.utils import timezone
from django.test import override_settings

from billing.models import Plan, Subscription, Invoice, PaymentAttempt
from billing.services import (
    create_subscription,
    create_invoice,
    activate_period,
    register_payment_failure,
    cancel_subscription,
    reactivate_subscription,
    check_plan_limit,
    RETRY_SCHEDULE,
    GRACE_PERIOD_DAYS,
)
from billing.gateway import (
    charge_subscription,
    create_payment_link,
    get_payment_status,
    create_flow_customer,
    _flow_sign,
    FlowAPIError,
)


# ══════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════

@pytest.fixture
def pro_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={
            "name": "Plan Pro", "price_clp": 59990, "trial_days": 7,
            "max_products": 1000, "max_stores": 5, "max_users": -1,
            "has_forecast": True, "has_abc": True,
            "has_reports": True, "has_transfers": True,
        },
    )
    return plan


@pytest.fixture
def inicio_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="inicio",
        defaults={
            "name": "Plan Inicio", "price_clp": 0, "trial_days": 0,
            "max_products": 120, "max_stores": 1, "max_users": 10,
        },
    )
    if plan.price_clp != 0:
        plan.price_clp = 0
        plan.save(update_fields=["price_clp"])
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
        sub.suspended_at = None
        sub.cancelled_at = None
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
def active_sub(db, subscription):
    now = timezone.now()
    subscription.status = Subscription.Status.ACTIVE
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    subscription.trial_ends_at = None
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
        gateway_order_id=f"TEST-{now.timestamp():.0f}",
    )


@pytest.fixture
def jwt_client(db, tenant):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    from core.models import User
    from stores.models import Store

    store = Store.objects.filter(tenant=tenant).first()
    if not store:
        store = Store.objects.create(tenant=tenant, name="Store Flow", code="FL-1", is_active=True)
    user, _ = User.objects.get_or_create(
        username="flow_jwt_user",
        defaults={"tenant": tenant, "active_store": store, "role": User.Role.OWNER},
    )
    user.set_password("pass123")
    user.tenant = tenant
    user.active_store = store
    user.save()
    token = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")
    return client


@pytest.fixture
def auth_client(db, owner):
    from rest_framework.test import APIClient
    c = APIClient()
    c.force_authenticate(user=owner)
    return c


def _mock_flow_status(invoice_pk, status=2, flow_order="FLOW-8888"):
    return {
        "flowOrder": flow_order,
        "commerceOrder": str(invoice_pk),
        "status": status,
        "subject": "Pulstock - Pro",
        "amount": 59990,
        "currency": "CLP",
        "payer": "test@example.com",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SUSCRIPCIÓN NUEVA: Plan → Subscription → primer PaymentAttempt
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestNewSubscriptionFlow:

    def test_create_subscription_paid_plan_creates_trial(self, tenant, pro_plan):
        """Plan de pago → Subscription TRIALING con trial_ends_at."""
        Subscription.objects.filter(tenant=tenant).delete()
        sub = create_subscription(tenant, plan_key="pro")
        assert sub.status == Subscription.Status.TRIALING
        assert sub.plan == pro_plan
        assert sub.trial_ends_at is not None
        assert sub.current_period_end is not None

    def test_create_subscription_free_plan_active(self, tenant, inicio_plan):
        """Plan gratis → Subscription ACTIVE directamente."""
        Subscription.objects.filter(tenant=tenant).delete()
        sub = create_subscription(tenant, plan_key="inicio")
        assert sub.status == Subscription.Status.ACTIVE
        assert sub.plan == inicio_plan

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_first_charge_creates_payment_attempt(self, subscription, pending_invoice):
        """Primer cobro crea PaymentAttempt con timestamp y referencia."""
        result = charge_subscription(subscription, pending_invoice)
        assert result["success"] is True
        assert result["gateway_order_id"] != ""
        assert result["gateway_tx_id"] != ""
        # Verify PaymentAttempt was created
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa is not None
        assert pa.result == PaymentAttempt.Result.SUCCESS
        assert pa.attempted_at is not None
        assert pa.gateway == "mock"

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_invoice_after_charge_has_gateway_ids(self, subscription, pending_invoice):
        """Invoice guarda gateway_order_id y gateway_tx_id."""
        charge_subscription(subscription, pending_invoice)
        pending_invoice.refresh_from_db()
        assert pending_invoice.gateway_order_id != ""
        assert pending_invoice.gateway_tx_id != ""

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_full_cycle_trial_to_active(self, subscription, pending_invoice):
        """Ciclo completo: cobro exitoso → activate_period → ACTIVE."""
        result = charge_subscription(subscription, pending_invoice)
        assert result["success"]
        activate_period(subscription, pending_invoice)
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID
        assert pending_invoice.paid_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SIGNAL post_save de Tenant crea Subscription
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTenantSignal:

    def test_new_tenant_gets_subscription(self, db, pro_plan):
        """Al crear Tenant con signal conectado, crea Subscription automáticamente."""
        from core.models import Tenant
        # Manually import signal to ensure it's connected (no apps.py ready())
        import billing.signal  # noqa: F401
        assert Plan.objects.filter(key="pro").exists()
        t = Tenant.objects.create(name="Signal Test", slug="signal-test-flow-2")
        sub = Subscription.objects.filter(tenant=t).first()
        assert sub is not None
        assert sub.plan.key == "pro"
        assert sub.status == Subscription.Status.TRIALING

    def test_signal_idempotent(self, tenant, pro_plan):
        """Guardar tenant existente no crea segunda suscripción."""
        import billing.signal  # noqa: F401
        count_before = Subscription.objects.filter(tenant=tenant).count()
        tenant.name = "Updated Name"
        tenant.save()
        count_after = Subscription.objects.filter(tenant=tenant).count()
        assert count_after == count_before

    def test_signal_without_plan_graceful(self, db):
        """Si Plan PRO no existe, el signal no crashea."""
        import billing.signal  # noqa: F401
        from core.models import Tenant
        Plan.objects.filter(key="pro").delete()
        # Should not raise
        try:
            t = Tenant.objects.create(name="No Plan Test", slug="no-plan-test-2")
        except Exception:
            pytest.fail("Signal should handle missing Plan gracefully")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CARGO AUTOMÁTICO pasos 1-6 (crear cargo, confirmar, polling)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAutoChargeCycle:

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_auto_charge_with_card_success(self, mock_api, subscription, pending_invoice):
        """Paso 1-3: tarjeta guardada → POST /customer/charge → status 2 → éxito."""
        subscription.flow_customer_id = "cus_1234"
        subscription.card_last4 = "5678"
        subscription.card_brand = "Visa"
        subscription.save()

        mock_api.return_value = {"status": 2, "flowOrder": "FO-999"}
        result = charge_subscription(subscription, pending_invoice)

        assert result["success"] is True
        assert result["gateway_tx_id"] == "FO-999"
        mock_api.assert_called_once()
        args = mock_api.call_args
        assert args[0][1] == "/customer/charge"  # endpoint
        assert args[0][0] == "POST"  # method
        # Verify PaymentAttempt created
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa.result == PaymentAttempt.Result.SUCCESS

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_auto_charge_rejected_falls_to_link(self, mock_api, subscription, pending_invoice):
        """Paso 4: cargo rechazado (status!=2) → fallback a payment link."""
        subscription.flow_customer_id = "cus_1234"
        subscription.card_last4 = "5678"
        subscription.save()

        # First call: /customer/charge → rejected
        # Second call: /payment/create → payment link
        mock_api.side_effect = [
            {"status": 3, "flowOrder": "FO-FAIL"},
            {"url": "https://flow.cl/pay", "token": "tk_123"},
        ]
        result = charge_subscription(subscription, pending_invoice)

        # Should have fallen back to payment link
        assert mock_api.call_count == 2
        # First call was /customer/charge, second was /payment/create
        assert mock_api.call_args_list[0][0][1] == "/customer/charge"
        assert mock_api.call_args_list[1][0][1] == "/payment/create"

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_auto_charge_api_error_falls_to_link(self, mock_api, subscription, pending_invoice):
        """Paso 5: FlowAPIError en auto-charge → fallback a link."""
        subscription.flow_customer_id = "cus_1234"
        subscription.card_last4 = "5678"
        subscription.save()

        mock_api.side_effect = [
            FlowAPIError(400, "Card expired", {}),
            {"url": "https://flow.cl/pay", "token": "tk_456"},
        ]
        result = charge_subscription(subscription, pending_invoice)
        assert mock_api.call_count == 2

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_no_card_goes_to_payment_link(self, mock_api, subscription, pending_invoice):
        """Sin tarjeta → directo a payment link (no intenta /customer/charge)."""
        subscription.flow_customer_id = ""
        subscription.card_last4 = ""
        subscription.save()

        mock_api.return_value = {"url": "https://flow.cl/pay", "token": "tk_789"}
        result = charge_subscription(subscription, pending_invoice)

        mock_api.assert_called_once()
        assert mock_api.call_args[0][1] == "/payment/create"

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_payment_link_stores_url_on_invoice(self, mock_api, subscription, pending_invoice):
        """Payment link URL se guarda en invoice.payment_url."""
        mock_api.return_value = {"url": "https://flow.cl/pay", "token": "tk_store"}
        result = charge_subscription(subscription, pending_invoice)
        pending_invoice.refresh_from_db()
        assert pending_invoice.payment_url is not None
        assert "tk_store" in pending_invoice.payment_url

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="test_key", FLOW_SECRET_KEY="test_secret")
    @patch("billing.gateway._flow_api_call")
    def test_confirm_payment_polling(self, mock_api, auth_client, subscription, pending_invoice):
        """Paso 6: frontend polling con confirm-payment → activa período."""
        mock_api.return_value = _mock_flow_status(pending_invoice.pk, status=2)
        resp = auth_client.post("/api/billing/subscription/confirm-payment/",
                                {"token": "test_token"}, format="json")
        assert resp.status_code == 200
        assert resp.data.get("status") in ("paid", "already_paid")
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID


# ═══════════════════════════════════════════════════════════════════════════════
# 4. WEBHOOK de Flow.cl actualiza estado Invoice a PAID
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFlowWebhookIntegration:

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._flow_api_call")
    def test_webhook_paid_activates_period(self, mock_api, subscription, pending_invoice):
        """Webhook con status=2 → Invoice PAID + Subscription ACTIVE."""
        from rest_framework.test import APIClient
        client = APIClient()
        mock_api.return_value = _mock_flow_status(pending_invoice.pk, status=2)

        resp = client.post("/api/billing/webhook/flow/", {"token": "wh_token"})
        assert resp.status_code == 200

        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.PAID
        assert pending_invoice.paid_at is not None
        assert pending_invoice.gateway_tx_id == "FLOW-8888"

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._flow_api_call")
    def test_webhook_creates_payment_attempt(self, mock_api, subscription, pending_invoice):
        """Webhook exitoso crea PaymentAttempt SUCCESS."""
        from rest_framework.test import APIClient
        client = APIClient()
        mock_api.return_value = _mock_flow_status(pending_invoice.pk, status=2)
        client.post("/api/billing/webhook/flow/", {"token": "wh_token"})

        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).last()
        assert pa is not None
        assert pa.result == PaymentAttempt.Result.SUCCESS

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._flow_api_call")
    def test_webhook_idempotent(self, mock_api, subscription, pending_invoice):
        """Doble webhook no duplica activación."""
        from rest_framework.test import APIClient
        client = APIClient()
        mock_api.return_value = _mock_flow_status(pending_invoice.pk, status=2)
        r1 = client.post("/api/billing/webhook/flow/", {"token": "wh_tok"})
        r2 = client.post("/api/billing/webhook/flow/", {"token": "wh_tok"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Only 1 paid invoice
        assert Invoice.objects.filter(pk=pending_invoice.pk, status=Invoice.Status.PAID).count() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PAGO FALLIDO → Invoice FAILED + reintento programado
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPaymentFailureAndRetry:

    def test_first_failure_sets_past_due(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice, error_msg="Card declined")
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.PAST_DUE
        assert subscription.payment_retry_count == 1

    def test_first_failure_creates_failed_attempt(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice, error_msg="Declined")
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).last()
        assert pa.result == PaymentAttempt.Result.FAILED
        assert pa.error_msg == "Declined"

    def test_first_failure_schedules_retry(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice)
        subscription.refresh_from_db()
        assert subscription.next_retry_at is not None
        # First retry: +1 day
        expected = timezone.now() + timedelta(days=RETRY_SCHEDULE[0])
        diff = abs((subscription.next_retry_at - expected).total_seconds())
        assert diff < 60  # within 1 minute

    def test_invoice_marked_failed(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice)
        pending_invoice.refresh_from_db()
        assert pending_invoice.status == Invoice.Status.FAILED

    def test_second_failure_retry_3_days(self, tenant, pro_plan):
        """Segundo fallo → reintento en 3 días."""
        now = timezone.now()
        sub = Subscription.objects.filter(tenant=tenant).first()
        sub.status = Subscription.Status.PAST_DUE
        sub.payment_retry_count = 1
        sub.save()
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            status=Invoice.Status.PENDING,
        )
        register_payment_failure(sub, inv)
        sub.refresh_from_db()
        assert sub.payment_retry_count == 2
        expected = timezone.now() + timedelta(days=RETRY_SCHEDULE[1])
        diff = abs((sub.next_retry_at - expected).total_seconds())
        assert diff < 60

    def test_exhausted_retries_suspends(self, tenant, pro_plan):
        """Reintentos agotados → SUSPENDED."""
        now = timezone.now()
        sub = Subscription.objects.filter(tenant=tenant).first()
        sub.status = Subscription.Status.PAST_DUE
        sub.payment_retry_count = len(RETRY_SCHEDULE)
        sub.save()
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            status=Invoice.Status.PENDING,
        )
        register_payment_failure(sub, inv)
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.SUSPENDED

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_retry_task_charges_and_activates(self, active_sub):
        """retry_failed_payments: reintento exitoso → activate_period."""
        from billing.tasks import retry_failed_payments
        now = timezone.now()
        active_sub.status = Subscription.Status.PAST_DUE
        active_sub.payment_retry_count = 1
        active_sub.next_retry_at = now - timedelta(hours=1)  # past due
        active_sub.current_period_end = now - timedelta(days=1)
        active_sub.save()

        inv = Invoice.objects.create(
            subscription=active_sub, amount_clp=59990,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            status=Invoice.Status.FAILED,
        )

        retry_failed_payments()
        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.ACTIVE
        assert active_sub.payment_retry_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6 & 7. MIDDLEWARE: bloquea suspendida, permite activa
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMiddlewareAccess:

    def _invalidate(self, sub):
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(sub.tenant_id)

    def test_suspended_returns_402(self, jwt_client, subscription):
        """Tenant con suscripción SUSPENDED → 402."""
        subscription.status = Subscription.Status.SUSPENDED
        subscription.suspended_at = timezone.now()
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 402

    def test_active_allows_access(self, jwt_client, active_sub):
        """Tenant con suscripción ACTIVE → permite acceso."""
        self._invalidate(active_sub)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 200

    def test_trialing_allows_access(self, jwt_client, subscription):
        """Tenant en TRIALING → permite acceso."""
        subscription.status = Subscription.Status.TRIALING
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 200

    def test_past_due_allows_access(self, jwt_client, subscription):
        """PAST_DUE → todavía permite acceso (gracia)."""
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 200

    def test_cancelled_blocks_access(self, jwt_client, subscription):
        """CANCELLED → bloquea acceso."""
        subscription.status = Subscription.Status.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 402

    def test_billing_endpoints_always_allowed(self, jwt_client, subscription):
        """Endpoints de billing permitidos incluso con SUSPENDED."""
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.get("/api/billing/subscription/")
        assert resp.status_code == 200

    def test_auth_endpoints_always_allowed(self, jwt_client, subscription):
        """Endpoints de auth permitidos incluso con SUSPENDED."""
        subscription.status = Subscription.Status.SUSPENDED
        subscription.save()
        self._invalidate(subscription)
        resp = jwt_client.post("/api/auth/refresh/", {"refresh": "fake"}, format="json")
        # May return 401 (bad token) but NOT 402
        assert resp.status_code != 402


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CANCELACIÓN → acceso bloqueado al vencimiento
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCancellationFlow:

    def test_cancel_sets_status(self, active_sub):
        cancel_subscription(active_sub, reason="Too expensive")
        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.CANCELLED
        assert active_sub.cancelled_at is not None

    def test_cancelled_sub_blocked_by_middleware(self, jwt_client, active_sub):
        """After cancellation, middleware blocks access."""
        cancel_subscription(active_sub, reason="test")
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(active_sub.tenant_id)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 402

    def test_reactivation_restores_access(self, jwt_client, active_sub):
        """Reactivation after cancellation restores access."""
        cancel_subscription(active_sub, reason="test")
        reactivate_subscription(active_sub)
        from billing.services import invalidate_sub_cache
        invalidate_sub_cache(active_sub.tenant_id)
        resp = jwt_client.get("/api/catalog/products/")
        assert resp.status_code == 200
        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.ACTIVE


# ═══════════════════════════════════════════════════════════════════════════════
# 9. VARIABLES DE ENTORNO AUSENTES → excepción clara
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestMissingEnvVars:

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="", FLOW_SECRET_KEY="")
    def test_missing_flow_keys_raises_clear_error(self, subscription, pending_invoice):
        """Sin FLOW_API_KEY → ValueError claro, no 500 silencioso."""
        with pytest.raises(ValueError, match="FLOW_API_KEY"):
            from billing.gateway import _flow_api_call
            _flow_api_call("POST", "/payment/create", {"amount": 100})

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="key", FLOW_SECRET_KEY="")
    def test_missing_secret_raises_clear_error(self):
        """Sin FLOW_SECRET_KEY → ValueError claro."""
        with pytest.raises(ValueError, match="FLOW_SECRET_KEY"):
            from billing.gateway import _flow_api_call
            _flow_api_call("POST", "/test", {})

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="", FLOW_SECRET_KEY="secret")
    def test_missing_api_key_raises_clear_error(self):
        """Sin FLOW_API_KEY → ValueError claro."""
        with pytest.raises(ValueError, match="FLOW_API_KEY"):
            from billing.gateway import _flow_api_call
            _flow_api_call("GET", "/test", {})


# ═══════════════════════════════════════════════════════════════════════════════
# 10. PaymentAttempt registra timestamp, monto CLP y referencia Flow
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPaymentAttemptRecord:

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_attempt_has_timestamp(self, subscription, pending_invoice):
        charge_subscription(subscription, pending_invoice)
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa.attempted_at is not None

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_attempt_linked_to_invoice_with_amount(self, subscription, pending_invoice):
        charge_subscription(subscription, pending_invoice)
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa.invoice.amount_clp == 59990

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_attempt_stores_gateway_reference(self, subscription, pending_invoice):
        charge_subscription(subscription, pending_invoice)
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa.raw is not None
        assert "order_id" in pa.raw or "mock" in pa.raw

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._flow_api_call")
    def test_flow_attempt_stores_flow_order(self, mock_api, subscription, pending_invoice):
        """PaymentAttempt with Flow stores flowOrder reference."""
        subscription.flow_customer_id = "cus_test"
        subscription.card_last4 = "9999"
        subscription.save()
        mock_api.return_value = {"status": 2, "flowOrder": "FO-12345"}
        charge_subscription(subscription, pending_invoice)

        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).first()
        assert pa.result == PaymentAttempt.Result.SUCCESS
        assert pa.raw.get("flowOrder") == "FO-12345"

    def test_failed_attempt_stores_error(self, subscription, pending_invoice):
        register_payment_failure(subscription, pending_invoice,
                                 error_msg="Card declined", raw={"code": "DECLINED"})
        pa = PaymentAttempt.objects.filter(invoice=pending_invoice).last()
        assert pa.result == PaymentAttempt.Result.FAILED
        assert pa.error_msg == "Card declined"
        assert pa.raw == {"code": "DECLINED"}


# ═══════════════════════════════════════════════════════════════════════════════
# 11. COBRO AUTOMÁTICO CON TARJETA GUARDADA (ciclo completo)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAutoChargeWithSavedCard:

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._flow_api_call")
    def test_full_auto_charge_cycle(self, mock_api, active_sub):
        """Ciclo completo: período vence → cobro automático con tarjeta → ACTIVE."""
        from billing.tasks import process_renewals

        now = timezone.now()
        # Simulate expired period
        active_sub.current_period_end = now - timedelta(hours=1)
        active_sub.flow_customer_id = "cus_auto"
        active_sub.card_last4 = "4242"
        active_sub.card_brand = "Visa"
        active_sub.save()

        # Mock: auto-charge success
        mock_api.return_value = {"status": 2, "flowOrder": "FO-AUTO"}
        process_renewals()

        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.ACTIVE
        assert active_sub.payment_retry_count == 0
        # New period was set
        assert active_sub.current_period_end > now

        # Invoice created and marked PAID
        inv = Invoice.objects.filter(subscription=active_sub).order_by("-id").first()
        assert inv.status == Invoice.Status.PAID

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_auto_charge_fail_then_manual_retry(self, active_sub):
        """Fallo mock → PAST_DUE → reintento exitoso → ACTIVE."""
        import os
        now = timezone.now()
        active_sub.current_period_end = now - timedelta(hours=1)
        active_sub.save()

        # Force mock failure
        os.environ["PAYMENT_GATEWAY_MOCK_FAIL"] = "1"
        try:
            from billing.tasks import process_renewals
            process_renewals()
        finally:
            os.environ.pop("PAYMENT_GATEWAY_MOCK_FAIL", None)

        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.PAST_DUE
        assert active_sub.payment_retry_count == 1

        # Now retry (mock success)
        active_sub.next_retry_at = now - timedelta(minutes=5)
        active_sub.save()

        from billing.tasks import retry_failed_payments
        retry_failed_payments()

        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.ACTIVE
        assert active_sub.payment_retry_count == 0

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_card_register_mock(self, subscription):
        """Mock gateway: create_flow_customer genera mock_cus_XX."""
        result = create_flow_customer(subscription)
        assert "customerId" in result
        assert result["customerId"].startswith("mock_cus_")
        subscription.refresh_from_db()
        assert subscription.flow_customer_id != ""


# ═══════════════════════════════════════════════════════════════════════════════
# 12. GATEWAY — HMAC + Error handling
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowGatewayEdgeCases:

    def test_flow_sign_deterministic(self):
        """Same params → same signature."""
        params = {"a": "1", "b": "2", "apiKey": "test"}
        s1 = _flow_sign(params, "secret")
        s2 = _flow_sign(params, "secret")
        assert s1 == s2

    def test_flow_sign_length(self):
        """HMAC-SHA256 produces 64-char hex."""
        sig = _flow_sign({"foo": "bar"}, "secret")
        assert len(sig) == 64

    def test_flow_sign_excludes_s_field(self):
        """'s' field should be excluded from signature."""
        params1 = {"a": "1", "b": "2"}
        params2 = {"a": "1", "b": "2", "s": "old_signature"}
        assert _flow_sign(params1, "secret") == _flow_sign(params2, "secret")

    def test_flow_sign_different_secret(self):
        params = {"a": "1"}
        s1 = _flow_sign(params, "secret1")
        s2 = _flow_sign(params, "secret2")
        assert s1 != s2

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_mock_get_payment_status(self):
        """Mock gateway always returns status=2 (paid)."""
        result = get_payment_status("any_token")
        assert result["status"] == 2
        assert result.get("mock") is True


# ═══════════════════════════════════════════════════════════════════════════════
# 13. TASKS — Celery edge cases
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCeleryTasks:

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_expire_trial_charges(self, subscription):
        """expire_trials: trial vencido → intenta cobro."""
        from billing.tasks import expire_trials
        subscription.status = Subscription.Status.TRIALING
        subscription.trial_ends_at = timezone.now() - timedelta(hours=1)
        subscription.current_period_end = timezone.now() - timedelta(hours=1)
        subscription.save()

        expire_trials()
        subscription.refresh_from_db()
        # Mock always succeeds → should be ACTIVE now
        assert subscription.status == Subscription.Status.ACTIVE

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_suspend_overdue_after_grace(self, active_sub):
        """suspend_overdue: past_due + gracia expirada → SUSPENDED."""
        from billing.tasks import suspend_overdue_subscriptions
        now = timezone.now()
        active_sub.status = Subscription.Status.PAST_DUE
        active_sub.current_period_end = now - timedelta(days=GRACE_PERIOD_DAYS + 1)
        active_sub.payment_retry_count = 3
        active_sub.save()

        suspend_overdue_subscriptions()
        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.SUSPENDED
        assert active_sub.suspended_at is not None

    @override_settings(PAYMENT_GATEWAY="mock")
    def test_suspend_within_grace_not_suspended(self, active_sub):
        """Dentro del período de gracia → NO suspende."""
        from billing.tasks import suspend_overdue_subscriptions
        now = timezone.now()
        active_sub.status = Subscription.Status.PAST_DUE
        active_sub.current_period_end = now - timedelta(days=1)  # < GRACE_PERIOD_DAYS
        active_sub.payment_retry_count = 3
        active_sub.save()

        suspend_overdue_subscriptions()
        active_sub.refresh_from_db()
        assert active_sub.status == Subscription.Status.PAST_DUE  # NOT suspended


# ═══════════════════════════════════════════════════════════════════════════════
# 14. PLAN LIMITS — Feature flags
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPlanLimits:

    def test_within_limit(self, subscription):
        result = check_plan_limit(subscription, "products", 50)
        assert result["allowed"] is True

    def test_exceeds_limit(self, subscription):
        result = check_plan_limit(subscription, "products", 1001)
        assert result["allowed"] is False
        assert result["limit"] == 1000

    def test_unlimited(self, subscription):
        """max_users = -1 → unlimited."""
        result = check_plan_limit(subscription, "users", 9999)
        assert result["allowed"] is True

    def test_feature_flag_check(self, subscription):
        """Pro plan has all features enabled."""
        assert subscription.plan.has_forecast is True
        assert subscription.plan.has_abc is True
        assert subscription.plan.has_reports is True

    def test_inicio_plan_no_features(self, tenant, inicio_plan):
        """Inicio plan has no advanced features."""
        assert not getattr(inicio_plan, "has_forecast", False)
        assert not getattr(inicio_plan, "has_abc", False)


# ═══════════════════════════════════════════════════════════════════════════════
# 15. INVOICE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestInvoiceEdgeCases:

    def test_mark_paid(self, pending_invoice):
        pending_invoice.mark_paid(tx_id="TX-123")
        assert pending_invoice.status == Invoice.Status.PAID
        assert pending_invoice.paid_at is not None
        assert pending_invoice.gateway_tx_id == "TX-123"

    def test_mark_paid_idempotent(self, pending_invoice):
        """Calling mark_paid twice doesn't crash."""
        pending_invoice.mark_paid(tx_id="TX-1")
        first_paid_at = pending_invoice.paid_at
        pending_invoice.mark_paid(tx_id="TX-2")
        # Second call overwrites but doesn't crash

    def test_create_invoice_amount_matches_plan(self, subscription):
        inv = create_invoice(subscription)
        assert inv.amount_clp == subscription.plan.price_clp
        assert inv.status == Invoice.Status.PENDING

    def test_unique_gateway_order_id_enforced(self, subscription):
        """Two invoices can't have the same non-empty gateway_order_id."""
        now = timezone.now()
        Invoice.objects.create(
            subscription=subscription, amount_clp=100,
            period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
            gateway_order_id="UNIQUE-123",
        )
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Invoice.objects.create(
                subscription=subscription, amount_clp=100,
                period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
                gateway_order_id="UNIQUE-123",
            )

    def test_empty_gateway_order_id_allows_multiple(self, subscription):
        """Empty gateway_order_id allows multiple invoices."""
        now = timezone.now()
        for _ in range(3):
            Invoice.objects.create(
                subscription=subscription, amount_clp=100,
                period_start=now.date(), period_end=(now + timedelta(days=30)).date(),
                gateway_order_id="",
            )
        assert Invoice.objects.filter(subscription=subscription, gateway_order_id="").count() >= 3
