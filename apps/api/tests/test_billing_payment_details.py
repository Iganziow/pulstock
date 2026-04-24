"""
Tests de los campos extendidos de Invoice (card_last4, card_brand, payment_media,
failure_message, etc.) capturados desde Flow /payment/getStatusExtended.

Cubre:

1. `billing.gateway.extract_payment_details()` — parseo defensivo del response
   de Flow, con casos borde (None, tipos inconsistentes, BINs varios).

2. Webhook `/api/billing/webhook/flow/` — que guarde los 8 campos nuevos en
   el Invoice cuando status=2, y failure_code/failure_message cuando
   status in (3, 4).

3. Helpers de `billing.tasks`:
      - `_sub_payment_method(sub)`       → "Visa ···· 4242"
      - `_invoice_payment_method(inv)`   → idem desde Invoice
      - `_latest_paid_invoice(sub)`
      - `_latest_invoice_failure_message(sub)`

4. Renderers `billing.email_renderers`:
      - `render_payment_recovered` con/sin payment_method
      - `render_payment_failed` con/sin failure_reason
      - `render_renewal_reminder` con/sin payment_method

Estos tests aseguran que el flujo de pago con los nuevos campos no se rompa
silenciosamente ante un refactor futuro. No dependen de Flow real — usan
mocks de payload según el OpenAPI spec de Flow (getStatusExtended).
"""
import pytest
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django.test import override_settings

from billing.models import Plan, Subscription, Invoice, PaymentAttempt
from billing.gateway import extract_payment_details


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures (reusan las de test_billing_flow.py pero locales para independencia)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def pro_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={
            "name": "Plan Pro", "price_clp": 29990, "trial_days": 7,
            "max_products": 1000, "max_stores": 5, "max_users": -1,
            "has_forecast": True, "has_abc": True,
            "has_reports": True, "has_transfers": True,
        },
    )
    return plan


@pytest.fixture
def active_sub(db, tenant, pro_plan):
    """Subscription ACTIVA con período por vencer (para probar renewal/retry)."""
    now = timezone.now()
    sub = Subscription.objects.filter(tenant=tenant).first()
    if sub:
        sub.plan = pro_plan
        sub.status = Subscription.Status.ACTIVE
        sub.current_period_start = now - timedelta(days=30)
        sub.current_period_end = now - timedelta(hours=1)
        sub.payment_retry_count = 0
        sub.next_retry_at = None
        sub.card_brand = ""
        sub.card_last4 = ""
        sub.save()
        return sub
    return Subscription.objects.create(
        tenant=tenant, plan=pro_plan,
        status=Subscription.Status.ACTIVE,
        current_period_start=now - timedelta(days=30),
        current_period_end=now - timedelta(hours=1),
    )


@pytest.fixture
def pending_invoice(db, active_sub):
    now = timezone.now()
    return Invoice.objects.create(
        subscription=active_sub,
        amount_clp=active_sub.plan.price_clp,
        period_start=active_sub.current_period_start.date(),
        period_end=active_sub.current_period_end.date(),
        status=Invoice.Status.PENDING,
        gateway="flow",
        gateway_order_id=f"TEST-{now.timestamp():.0f}",
    )


def _flow_response_paid(invoice_pk, *, amount, card_last4="6623",
                       card_number=None, media="Webpay", installments=None,
                       auth_code=None):
    """Build a Flow getStatusExtended response for status=2 (paid).

    `amount` es obligatorio para que el caller pase exactamente el amount_clp
    del Invoice y evitar falsos amount_mismatch.
    """
    return {
        "status": 2,
        "flowOrder": 99999999,
        "commerceOrder": str(invoice_pk),
        "amount": amount,
        "currency": "CLP",
        "paymentData": {
            "date": "2026-04-24 12:00:00",
            "media": media,
            "mediaType": "Credito",
            "cardLast4Numbers": card_last4,
            "cardNumber": card_number,
            "installments": installments,
            "autorizationCode": auth_code,
        },
        "lastError": None,
        "s": "mock_signature",
    }


def _flow_response_rejected(invoice_pk, *, code="05", message="Tarjeta vencida"):
    return {
        "status": 3,
        "flowOrder": 88888888,
        "commerceOrder": str(invoice_pk),
        "amount": 29990,
        "currency": "CLP",
        "paymentData": None,
        "lastError": {"code": code, "message": message, "medioCode": "005"},
        "s": "mock_signature",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. extract_payment_details — unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractPaymentDetails:
    """Parseo defensivo del response de /payment/getStatusExtended."""

    def test_paid_with_visa_bin_infers_brand(self):
        r = {"paymentData": {
            "cardLast4Numbers": "6623",
            "cardNumber": "405188 **** **** 6623",
            "media": "Webpay",
        }, "lastError": None}
        d = extract_payment_details(r)
        assert d["card_last4"] == "6623"
        assert d["card_brand"] == "Visa"
        assert d["payment_media"] == "Webpay"

    def test_mastercard_bin(self):
        r = {"paymentData": {
            "cardLast4Numbers": "4242",
            "cardNumber": "512345 **** **** 4242",
        }}
        assert extract_payment_details(r)["card_brand"] == "Mastercard"

    def test_amex_bin(self):
        r = {"paymentData": {"cardLast4Numbers": "1000", "cardNumber": "341111 **** 1000"}}
        assert extract_payment_details(r)["card_brand"] == "American Express"

    def test_unionpay_bin(self):
        r = {"paymentData": {"cardLast4Numbers": "5555", "cardNumber": "625888 **** 5555"}}
        assert extract_payment_details(r)["card_brand"] == "UnionPay"

    def test_discover_bin(self):
        r = {"paymentData": {"cardLast4Numbers": "7777", "cardNumber": "601100 **** 7777"}}
        assert extract_payment_details(r)["card_brand"] == "Discover"

    def test_sandbox_no_card_number_falls_back_to_generic(self):
        """Flow sandbox no manda cardNumber — debe usar 'Tarjeta'."""
        r = {"paymentData": {"cardLast4Numbers": "6623", "cardNumber": None}}
        d = extract_payment_details(r)
        assert d["card_last4"] == "6623"
        assert d["card_brand"] == "Tarjeta"

    def test_no_card_data_leaves_brand_empty(self):
        """Si no hay last4 ni cardNumber, brand queda vacío (pago no fue con tarjeta)."""
        r = {"paymentData": {"media": "Servipag", "cardLast4Numbers": None, "cardNumber": None}}
        d = extract_payment_details(r)
        assert d["card_last4"] == ""
        assert d["card_brand"] == ""
        assert d["payment_media"] == "Servipag"

    def test_rejected_captures_failure_code_and_message(self):
        r = _flow_response_rejected(123, code="05", message="Tarjeta vencida")
        d = extract_payment_details(r)
        assert d["failure_code"] == "05"
        assert d["failure_message"] == "Tarjeta vencida"
        # Success fields deben quedar vacíos
        assert d["card_last4"] == ""
        assert d["authorization_code"] == ""

    def test_empty_payment_data_does_not_crash(self):
        """paymentData = None es común en rechazos sin attempt — no debe crashear."""
        r = {"status": 3, "paymentData": None, "lastError": None}
        d = extract_payment_details(r)
        assert d["card_last4"] == ""
        assert d["card_brand"] == ""
        assert d["installments"] is None

    def test_last4_as_int_casts_to_str(self):
        """Edge case: Flow puede mandar cardLast4Numbers como int."""
        r = {"paymentData": {"cardLast4Numbers": 6623, "cardNumber": None}}
        d = extract_payment_details(r)
        assert d["card_last4"] == "6623"

    def test_installments_string_casts_to_int(self):
        """Flow a veces devuelve installments como string — castear a int."""
        r = {"paymentData": {"cardLast4Numbers": "1234", "installments": "3"}}
        d = extract_payment_details(r)
        assert d["installments"] == 3

    def test_installments_zero_becomes_none(self):
        """installments=0 no tiene sentido — normalizar a None."""
        r = {"paymentData": {"cardLast4Numbers": "1234", "installments": 0}}
        d = extract_payment_details(r)
        assert d["installments"] is None

    def test_installments_invalid_string_becomes_none(self):
        """Si installments viene como 'abc', no crashear."""
        r = {"paymentData": {"cardLast4Numbers": "1234", "installments": "abc"}}
        d = extract_payment_details(r)
        assert d["installments"] is None

    def test_truncates_long_strings_to_model_max(self):
        """payment_media está limitado a 40 chars — si Flow devuelve algo largo,
        truncamos para no romper el insert."""
        long = "X" * 200
        r = {"paymentData": {"cardLast4Numbers": "1", "media": long,
                             "mediaType": long, "autorizationCode": long}}
        d = extract_payment_details(r)
        assert len(d["payment_media"]) == 40
        assert len(d["payment_media_type"]) == 20
        assert len(d["authorization_code"]) == 40

    def test_completely_empty_response_is_safe(self):
        """Respuesta mínima: no hay paymentData ni lastError. No debe crashear."""
        d = extract_payment_details({})
        assert d["card_last4"] == ""
        assert d["card_brand"] == ""
        assert d["failure_code"] == ""
        assert d["installments"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Webhook Flow — guardado de los 8 campos nuevos
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestWebhookSavesPaymentDetails:
    """Asegurar que el webhook /api/billing/webhook/flow/ persiste los nuevos
    campos en Invoice y syncea Subscription.card_*."""

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._verify_flow_token_signature", return_value=True)
    @patch("billing.gateway._flow_api_call")
    def test_paid_saves_card_last4_and_brand(self, mock_api, _mock_sig, pending_invoice):
        from rest_framework.test import APIClient
        mock_api.return_value = _flow_response_paid(
            pending_invoice.pk, amount=pending_invoice.amount_clp,
            card_last4="6623",
            card_number="405188 **** **** 6623", installments=3, auth_code="AUTH123",
        )
        client = APIClient()
        resp = client.post("/api/billing/webhook/flow/", {"token": "tk"})
        assert resp.status_code == 200

        pending_invoice.refresh_from_db()
        assert pending_invoice.card_last4 == "6623"
        assert pending_invoice.card_brand == "Visa"
        assert pending_invoice.payment_media == "Webpay"
        assert pending_invoice.payment_media_type == "Credito"
        assert pending_invoice.installments == 3
        assert pending_invoice.authorization_code == "AUTH123"

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._verify_flow_token_signature", return_value=True)
    @patch("billing.gateway._flow_api_call")
    def test_paid_syncs_subscription_mirror(self, mock_api, _mock_sig, pending_invoice):
        """Al pagar, Subscription.card_last4/brand se actualiza con los del Invoice."""
        from rest_framework.test import APIClient
        mock_api.return_value = _flow_response_paid(
            pending_invoice.pk, amount=pending_invoice.amount_clp,
            card_last4="9999",
            card_number="555555 **** **** 9999",
        )
        APIClient().post("/api/billing/webhook/flow/", {"token": "tk"})

        pending_invoice.refresh_from_db()
        pending_invoice.subscription.refresh_from_db()
        assert pending_invoice.subscription.card_last4 == "9999"
        assert pending_invoice.subscription.card_brand == "Mastercard"

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._verify_flow_token_signature", return_value=True)
    @patch("billing.gateway._flow_api_call")
    def test_rejected_saves_failure_code_and_message(self, mock_api, _mock_sig,
                                                     pending_invoice):
        from rest_framework.test import APIClient
        mock_api.return_value = _flow_response_rejected(
            pending_invoice.pk, code="05", message="Tarjeta vencida",
        )
        APIClient().post("/api/billing/webhook/flow/", {"token": "tk"})

        pending_invoice.refresh_from_db()
        assert pending_invoice.failure_code == "05"
        assert pending_invoice.failure_message == "Tarjeta vencida"
        assert pending_invoice.status == Invoice.Status.FAILED

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._verify_flow_token_signature", return_value=True)
    @patch("billing.gateway._flow_api_call")
    def test_rejected_without_lasterror_uses_generic_message(self, mock_api,
                                                             _mock_sig, pending_invoice):
        """Si Flow no manda lastError, usamos mensaje genérico (no 'fondos
        insuficientes' hardcoded)."""
        from rest_framework.test import APIClient
        resp = _flow_response_rejected(pending_invoice.pk)
        resp["lastError"] = None
        mock_api.return_value = resp
        APIClient().post("/api/billing/webhook/flow/", {"token": "tk"})

        pending_invoice.refresh_from_db()
        # Fallback: "Pago rechazado por Flow" — NO "fondos insuficientes"
        assert "rechazado" in pending_invoice.failure_message.lower()
        assert pending_invoice.failure_code == ""

    @override_settings(PAYMENT_GATEWAY="flow", FLOW_API_KEY="k", FLOW_SECRET_KEY="s")
    @patch("billing.gateway._verify_flow_token_signature", return_value=True)
    @patch("billing.gateway._flow_api_call")
    def test_amount_mismatch_does_not_save_card_data(self, mock_api, _mock_sig,
                                                     pending_invoice):
        """Amount tampering bloquea: Invoice NO queda PAID y card_last4 NO se persiste."""
        from rest_framework.test import APIClient
        bad = _flow_response_paid(
            pending_invoice.pk, amount=pending_invoice.amount_clp,
            card_last4="6623", card_number="405188 **** **** 6623",
        )
        bad["amount"] = 1  # tampered: Flow dice 1 CLP, nosotros esperamos el real
        mock_api.return_value = bad
        resp = APIClient().post("/api/billing/webhook/flow/", {"token": "tk"})

        pending_invoice.refresh_from_db()
        # El webhook devuelve 400 Bad Request por amount mismatch
        assert resp.status_code == 400
        assert pending_invoice.status != Invoice.Status.PAID
        # Los campos de card NO se guardaron (no se ejecutó el save en webhook)
        assert pending_invoice.card_last4 == ""


# ══════════════════════════════════════════════════════════════════════════════
# 3. Helpers de billing.tasks
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestTaskHelpers:
    """Helpers que construyen strings 'Visa ···· 4242' y lookups de Invoice
    para los emails de billing."""

    def test_sub_payment_method_with_brand_and_last4(self, active_sub):
        from billing.tasks import _sub_payment_method
        active_sub.card_brand = "Visa"
        active_sub.card_last4 = "4242"
        active_sub.save()
        assert _sub_payment_method(active_sub) == "Visa ···· 4242"

    def test_sub_payment_method_without_card_returns_none(self, active_sub):
        from billing.tasks import _sub_payment_method
        active_sub.card_brand = ""
        active_sub.card_last4 = ""
        active_sub.save()
        assert _sub_payment_method(active_sub) is None

    def test_sub_payment_method_only_last4_uses_generic_brand(self, active_sub):
        """Flow sandbox escenario: tenemos last4 pero no brand."""
        from billing.tasks import _sub_payment_method
        active_sub.card_brand = ""
        active_sub.card_last4 = "6623"
        active_sub.save()
        assert _sub_payment_method(active_sub) == "Tarjeta ···· 6623"

    def test_invoice_payment_method_from_invoice_fields(self, pending_invoice):
        from billing.tasks import _invoice_payment_method
        pending_invoice.card_brand = "Mastercard"
        pending_invoice.card_last4 = "1111"
        pending_invoice.save()
        assert _invoice_payment_method(pending_invoice) == "Mastercard ···· 1111"

    def test_invoice_payment_method_none_invoice_returns_none(self):
        from billing.tasks import _invoice_payment_method
        assert _invoice_payment_method(None) is None

    def test_latest_paid_invoice_returns_most_recent(self, active_sub, db):
        """Con múltiples invoices, debe devolver el más reciente en estado PAID."""
        from billing.tasks import _latest_paid_invoice
        now = timezone.now()
        # Orden: 1 pagada vieja, 1 fallida, 1 pagada reciente
        old_paid = Invoice.objects.create(
            subscription=active_sub, amount_clp=1000,
            period_start=now.date(), period_end=now.date(),
            status=Invoice.Status.PAID, paid_at=now - timedelta(days=60),
            gateway="flow", gateway_order_id="OLD",
        )
        Invoice.objects.create(
            subscription=active_sub, amount_clp=1000,
            period_start=now.date(), period_end=now.date(),
            status=Invoice.Status.FAILED,
            gateway="flow", gateway_order_id="FAIL",
        )
        new_paid = Invoice.objects.create(
            subscription=active_sub, amount_clp=1000,
            period_start=now.date(), period_end=now.date(),
            status=Invoice.Status.PAID, paid_at=now,
            gateway="flow", gateway_order_id="NEW",
        )
        result = _latest_paid_invoice(active_sub)
        assert result.pk == new_paid.pk

    def test_latest_paid_invoice_returns_none_if_no_paid(self, active_sub):
        from billing.tasks import _latest_paid_invoice
        assert _latest_paid_invoice(active_sub) is None

    def test_latest_invoice_failure_message_ignores_empty(self, active_sub):
        """Debe ignorar invoices con failure_message vacío y encontrar uno con
        mensaje real."""
        from billing.tasks import _latest_invoice_failure_message
        now = timezone.now()
        # Un invoice failed sin mensaje
        Invoice.objects.create(
            subscription=active_sub, amount_clp=1000,
            period_start=now.date(), period_end=now.date(),
            status=Invoice.Status.FAILED, failure_message="",
            gateway="flow", gateway_order_id="EMPTY",
        )
        # Uno failed con mensaje
        Invoice.objects.create(
            subscription=active_sub, amount_clp=1000,
            period_start=now.date(), period_end=now.date(),
            status=Invoice.Status.FAILED,
            failure_message="CVV incorrecto",
            gateway="flow", gateway_order_id="MSG",
        )
        assert _latest_invoice_failure_message(active_sub) == "CVV incorrecto"

    def test_latest_invoice_failure_message_none_when_all_empty(self, active_sub):
        from billing.tasks import _latest_invoice_failure_message
        assert _latest_invoice_failure_message(active_sub) is None

    def test_latest_invoice_number_format(self, active_sub, pending_invoice):
        from billing.tasks import _latest_invoice_number
        num = _latest_invoice_number(active_sub)
        assert num.startswith("INV-")
        assert len(num.split("-")[1]) >= 5  # zero-padded


# ══════════════════════════════════════════════════════════════════════════════
# 4. Renderers — con datos reales y fallbacks
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEmailRenderersWithRealData:
    """Los renderers deben mostrar datos reales cuando se les pasa, y fallback
    genéricos cuando son None (nunca el placeholder fake 'Visa ···· 4829')."""

    def test_render_payment_recovered_shows_real_card(self, active_sub):
        from billing.email_renderers import render_payment_recovered
        subject, plain, html = render_payment_recovered(
            active_sub, "INV-00042",
            payment_method="Visa ···· 6623",
            charged_at=timezone.now(),
        )
        assert "Visa ···· 6623" in html
        # Nunca debe aparecer el placeholder viejo
        assert "4829" not in html

    def test_render_payment_recovered_without_method_omits_card_line(self, active_sub):
        from billing.email_renderers import render_payment_recovered
        _, _, html = render_payment_recovered(
            active_sub, "INV-00042",
            payment_method=None,  # <-- cliente sin tarjeta registrada
            charged_at=timezone.now(),
        )
        # No debe aparecer ningún placeholder fake
        assert "4829" not in html
        assert "Visa ···· " not in html
        # Body usa fallback "Cobro procesado el ..."
        assert "Cobro procesado" in html

    def test_render_payment_failed_shows_real_reason(self, active_sub):
        from billing.email_renderers import render_payment_failed
        _, _, html = render_payment_failed(
            active_sub, "INV-00042",
            failure_reason="Tarjeta vencida",
            payment_method="Visa ···· 6623",
        )
        assert "Tarjeta vencida" in html
        assert "Visa ···· 6623" in html
        # Antes había "fondos insuficientes" hardcoded — verificamos que NO aparezca
        assert "fondos insuficientes" not in html

    def test_render_payment_failed_without_reason_uses_generic(self, active_sub):
        from billing.email_renderers import render_payment_failed
        _, _, html = render_payment_failed(
            active_sub, "INV-00042",
            failure_reason=None,
            payment_method=None,
        )
        # No debe aparecer el placeholder anterior
        assert "fondos insuficientes" not in html
        assert "4829" not in html
        # Sí debe aparecer el fallback genérico
        assert ("no autorizó" in html) or ("El cobro fue rechazado" in html)

    def test_render_renewal_reminder_shows_real_method(self, active_sub):
        from billing.email_renderers import render_renewal_reminder
        # active_sub fixture tiene current_period_end en el pasado (-1h).
        # Fix temporal para que la fecha del email no sea negativa.
        active_sub.current_period_end = timezone.now() + timedelta(days=7)
        active_sub.save()
        _, _, html = render_renewal_reminder(
            active_sub, 7, payment_method="Mastercard ···· 1111",
        )
        assert "Mastercard ···· 1111" in html

    def test_render_renewal_reminder_without_method_uses_generic(self, active_sub):
        from billing.email_renderers import render_renewal_reminder
        active_sub.current_period_end = timezone.now() + timedelta(days=7)
        active_sub.save()
        _, _, html = render_renewal_reminder(active_sub, 7, payment_method=None)
        assert "Tu método de pago registrado" in html
        assert "4829" not in html
