"""
Tests regresión para los fixes de hardening del flujo Flow.cl.
Cubren los bugs encontrados en la auditoría pre-producción:
  - BUG-2: validación amount+currency en webhooks
  - BUG-3: FlowCheckoutWebhook expires_at + flow_status handling
  - BUG-4: race-safe _auto_create_checkout_account
  - BUG-6: ConfirmPaymentView lock + amount check
  - BUG-15: CardRegister multi-customer guard
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Tenant, User
from billing.models import (
    Plan, Subscription, Invoice, PaymentAttempt, CheckoutSession,
)


# ─────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def plan():
    p, _ = Plan.objects.get_or_create(
        key="pro_hardening_test",
        defaults={
            "name": "Plan Pro HT", "price_clp": 29990,
            "max_products": -1, "max_stores": -1, "max_users": -1,
        },
    )
    return p


@pytest.fixture
def sub(tenant, plan):
    now = timezone.now()
    return Subscription.objects.create(
        tenant=tenant, plan=plan,
        status=Subscription.Status.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )


@pytest.fixture
def invoice(sub, plan):
    now = timezone.now()
    return Invoice.objects.create(
        subscription=sub,
        status=Invoice.Status.PENDING,
        amount_clp=plan.price_clp,  # 29990
        period_start=now.date(),
        period_end=(now + timedelta(days=30)).date(),
        gateway="flow",
        gateway_order_id="test-order",
    )


@pytest.fixture
def jwt_client(user):
    c = APIClient()
    token = RefreshToken.for_user(user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return c


@pytest.fixture
def checkout_session(plan):
    return CheckoutSession.objects.create(
        email="nuevo@test.cl", plan=plan,
        amount_clp=plan.price_clp,  # 29990
        expires_at=timezone.now() + timedelta(hours=2),
        business_name="Nuevo Negocio",
        owner_name="Juan Pérez",
        owner_username="juanperez",
        owner_password_hash="pbkdf2_sha256$fake$hash",
    )


# ─────────────────────────────────────────────────────────────
# BUG-2: amount/currency mismatch → rechazo
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_flow_webhook_rechaza_amount_mismatch(invoice):
    c = APIClient()
    # Flow devuelve amount=100 pero invoice espera 29990
    fake_response = {
        "status": 2,
        "commerceOrder": str(invoice.pk),
        "flowOrder": 12345,
        "amount": 100,         # ← mismatch
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow/", {"token": "any_token"})
    assert r.status_code == 400
    invoice.refresh_from_db()
    assert invoice.status != Invoice.Status.PAID
    # Se dejó registro del intento fallido
    assert PaymentAttempt.objects.filter(
        invoice=invoice, result=PaymentAttempt.Result.FAILED,
    ).exists()


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_flow_webhook_rechaza_currency_mismatch(invoice):
    c = APIClient()
    fake_response = {
        "status": 2,
        "commerceOrder": str(invoice.pk),
        "flowOrder": 12345,
        "amount": 29990,
        "currency": "USD",  # ← mismatch
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow/", {"token": "any_token"})
    assert r.status_code == 400
    invoice.refresh_from_db()
    assert invoice.status != Invoice.Status.PAID


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_flow_webhook_acepta_amount_correcto(invoice):
    c = APIClient()
    fake_response = {
        "status": 2,
        "commerceOrder": str(invoice.pk),
        "flowOrder": 99999,
        "amount": 29990,
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow/", {"token": "any_token"})
    assert r.status_code == 200
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PAID
    assert invoice.gateway_tx_id == "99999"


# ─────────────────────────────────────────────────────────────
# BUG-3: checkout webhook con sesión expirada
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_checkout_webhook_rechaza_sesion_expirada(checkout_session):
    # Expirar la sesión manualmente
    checkout_session.expires_at = timezone.now() - timedelta(minutes=5)
    checkout_session.save()

    c = APIClient()
    fake_response = {
        "status": 2,
        "commerceOrder": f"CS-{checkout_session.pk}",
        "flowOrder": 55555,
        "amount": 29990,
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow-checkout/", {"token": "any_token"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("detail") == "expired"
    checkout_session.refresh_from_db()
    assert checkout_session.status == CheckoutSession.STATUS_EXPIRED


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_checkout_webhook_amount_mismatch(checkout_session):
    c = APIClient()
    fake_response = {
        "status": 2,
        "commerceOrder": f"CS-{checkout_session.pk}",
        "flowOrder": 55555,
        "amount": 100,   # ← mismatch
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow-checkout/", {"token": "any_token"})
    assert r.status_code == 400
    checkout_session.refresh_from_db()
    assert checkout_session.status != CheckoutSession.STATUS_PAID


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_checkout_webhook_status_error_gateway(checkout_session):
    c = APIClient()
    with patch("billing.gateway._flow_api_call",
               side_effect=__import__("billing.gateway", fromlist=["FlowAPIError"]).FlowAPIError(
                   400, "Token inválido", {}
               )):
        r = c.post("/api/billing/webhook/flow-checkout/", {"token": "any_token"})
    assert r.status_code == 502


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_checkout_webhook_status_pendiente_no_cambia_estado(checkout_session):
    c = APIClient()
    fake_response = {
        "status": 1,  # pendiente
        "commerceOrder": f"CS-{checkout_session.pk}",
        "flowOrder": 55555,
        "amount": 29990,
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = c.post("/api/billing/webhook/flow-checkout/", {"token": "any_token"})
    assert r.status_code == 200
    checkout_session.refresh_from_db()
    assert checkout_session.status == CheckoutSession.STATUS_PENDING


# ─────────────────────────────────────────────────────────────
# BUG-4: auto_create es idempotente (no crea 2 cuentas)
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_auto_create_es_idempotente(checkout_session):
    """Llamar 2 veces a _auto_create_checkout_account con el mismo CheckoutSession
    debe crear UN solo tenant/user (protección por select_for_update + status check)."""
    from billing.views import _auto_create_checkout_account

    checkout_session.status = CheckoutSession.STATUS_PAID
    checkout_session.gateway_tx_id = "TX-123"
    checkout_session.save()

    # Primera llamada: crea todo
    _auto_create_checkout_account(checkout_session)
    checkout_session.refresh_from_db()
    assert checkout_session.status == CheckoutSession.STATUS_COMPLETED
    assert Tenant.objects.filter(name="Nuevo Negocio").count() == 1
    assert User.objects.filter(username="juanperez").count() == 1

    # Segunda llamada: no hace nada (session ya COMPLETED)
    _auto_create_checkout_account(checkout_session)
    assert Tenant.objects.filter(name="Nuevo Negocio").count() == 1
    assert User.objects.filter(username="juanperez").count() == 1


# ─────────────────────────────────────────────────────────────
# BUG-6: ConfirmPayment con tenant mismatch → 404
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_confirm_payment_bloquea_cross_tenant(jwt_client, invoice, tenant):
    """Usuario de tenant A no puede confirmar pago de invoice de tenant B."""
    # Crear tenant B con otro invoice
    other_tenant = Tenant(name="Otro", slug="otro-hardening")
    other_tenant._skip_subscription = True
    other_tenant.save()
    other_plan, _ = Plan.objects.get_or_create(
        key="basic",
        defaults={"name": "Basic", "price_clp": 9990, "max_products": 100,
                  "max_stores": 1, "max_users": 2},
    )
    other_sub = Subscription.objects.create(
        tenant=other_tenant, plan=other_plan,
        status=Subscription.Status.ACTIVE,
        current_period_start=timezone.now(),
        current_period_end=timezone.now() + timedelta(days=30),
    )
    other_invoice = Invoice.objects.create(
        subscription=other_sub,
        status=Invoice.Status.PENDING,
        amount_clp=9990,
        period_start=timezone.now().date(),
        period_end=(timezone.now() + timedelta(days=30)).date(),
    )

    fake_response = {
        "status": 2,
        "commerceOrder": str(other_invoice.pk),
        "flowOrder": 77777,
        "amount": 9990,
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = jwt_client.post("/api/billing/subscription/confirm-payment/", {"token": "any"})
    assert r.status_code == 404
    other_invoice.refresh_from_db()
    assert other_invoice.status != Invoice.Status.PAID


@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_confirm_payment_bloquea_amount_tampering(jwt_client, invoice):
    """Aun siendo del mismo tenant, si Flow devuelve amount distinto → 400."""
    fake_response = {
        "status": 2,
        "commerceOrder": str(invoice.pk),
        "flowOrder": 88888,
        "amount": 100,    # mismatch
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r = jwt_client.post("/api/billing/subscription/confirm-payment/", {"token": "any"})
    assert r.status_code == 400
    invoice.refresh_from_db()
    assert invoice.status != Invoice.Status.PAID


# ─────────────────────────────────────────────────────────────
# BUG-15: CardRegister con múltiples subs vacías no confunde
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_card_register_sin_customer_id_no_rompe(db):
    """Webhook de Card Register con customerId vacío no crashea.

    Anteriormente, si múltiples subs tenían flow_customer_id="", el get
    levantaba MultipleObjectsReturned.
    """
    from core.models import Tenant as T
    from billing.models import Plan as P, Subscription as S
    # 2 subs con flow_customer_id vacío (situación típica de tenants nuevos)
    p, _ = P.objects.get_or_create(
        key="free",
        defaults={"name": "Free", "price_clp": 0, "max_products": 10,
                  "max_stores": 1, "max_users": 1},
    )
    for i in range(2):
        t = T(name=f"T{i}_card", slug=f"t{i}-card-test")
        t._skip_subscription = True
        t.save()
        S.objects.create(
            tenant=t, plan=p,
            status=S.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )

    c = APIClient()
    with patch(
        "billing.gateway._flow_api_call",
        return_value={"status": "1", "customerId": "", "creditCardType": "Visa",
                      "last4CardDigits": "4242"},
    ):
        # NO debe crashear con MultipleObjectsReturned
        r = c.post("/api/billing/webhook/flow-card-register/", {"token": "any"})
    # Response puede ser redirect (302) o 200, lo importante es que no crashea
    assert r.status_code in (200, 302)


# ─────────────────────────────────────────────────────────────
# Idempotencia general del webhook principal (Flow reenvía)
# ─────────────────────────────────────────────────────────────
@pytest.mark.django_db
@override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
def test_flow_webhook_idempotente_mismo_flow_order(invoice):
    c = APIClient()
    fake_response = {
        "status": 2,
        "commerceOrder": str(invoice.pk),
        "flowOrder": 11111,
        "amount": 29990,
        "currency": "CLP",
    }
    with patch("billing.gateway._flow_api_call", return_value=fake_response):
        r1 = c.post("/api/billing/webhook/flow/", {"token": "any"})
        r2 = c.post("/api/billing/webhook/flow/", {"token": "any"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Solo UN PaymentAttempt exitoso (idempotente)
    assert PaymentAttempt.objects.filter(
        invoice=invoice, result=PaymentAttempt.Result.SUCCESS,
    ).count() == 1
