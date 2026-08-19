"""
tests/test_b20_link_no_es_pago.py — B20, el hallazgo más grave de la auditoría.

Cuando la renovación mensual corría y el tenant no tenía tarjeta registrada
(o el cargo era rechazado), Flow devolvía un LINK DE PAGO. Esa operación es un
éxito técnico —el link se creó bien— pero un cobro PENDIENTE. El gateway
devolvía `success: True` y las tres tareas de billing hacían:

    if result["success"]:
        activate_period(sub, invoice)   # ← marca la factura PAGADA y regala 30 días

Resultado: el cliente no paga, el sistema le da un mes gratis, y la factura
queda como "paid" sin transacción real.

El arreglo separa dos cosas que estaban pegadas:
    success = la operación con Flow salió bien
    paid    = hay plata efectivamente cobrada  ← lo único que activa el período
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from billing.models import Invoice, Plan, Subscription

D = Decimal


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        name="Plan Pro", price_clp=D("35000"), is_active=True,
    )


@pytest.fixture
def sub_por_renovar(db, tenant, plan):
    """Suscripción activa cuyo período ya venció → toca renovar."""
    ahora = timezone.now()
    return Subscription.objects.create(
        tenant=tenant, plan=plan,
        status=Subscription.Status.ACTIVE,
        current_period_start=ahora - timezone.timedelta(days=31),
        current_period_end=ahora - timezone.timedelta(minutes=5),
    )


def _resultado_link():
    """Lo que devuelve Flow cuando NO hay tarjeta: link creado, nada cobrado."""
    return {
        "success": True,
        "paid": False,
        "payment_url": "https://sandbox.flow.cl/pay?token=abc123",
        "gateway_order_id": "42",
        "gateway_tx_id": "",
        "error": "",
        "raw": {},
    }


def _resultado_cobrado():
    """Cargo real aprobado en la tarjeta registrada."""
    return {
        "success": True,
        "paid": True,
        "payment_url": None,
        "gateway_order_id": "42",
        "gateway_tx_id": "FLOW-999",
        "error": "",
        "raw": {},
    }


@pytest.mark.django_db
class TestB20LinkNoActivaPeriodo:
    def test_un_link_de_pago_NO_regala_el_periodo(self, sub_por_renovar):
        """EL BUG. Sin tarjeta → link → antes activaba 30 días gratis."""
        from billing.tasks import process_renewals
        fin_antes = sub_por_renovar.current_period_end

        with patch("billing.gateway.charge_subscription", return_value=_resultado_link()):
            process_renewals()

        sub_por_renovar.refresh_from_db()
        assert sub_por_renovar.current_period_end == fin_antes, (
            "un link de pago NO puede extender el período: no se cobró nada"
        )
        assert not Invoice.objects.filter(
            subscription=sub_por_renovar, status=Invoice.Status.PAID,
        ).exists(), "la factura no puede quedar PAGADA sin transacción"

    def test_un_cobro_real_SI_activa_el_periodo(self, sub_por_renovar):
        """Control: el camino bueno sigue funcionando."""
        from billing.tasks import process_renewals
        fin_antes = sub_por_renovar.current_period_end

        with patch("billing.gateway.charge_subscription", return_value=_resultado_cobrado()):
            process_renewals()

        sub_por_renovar.refresh_from_db()
        assert sub_por_renovar.current_period_end > fin_antes, (
            "con cobro efectivo el período debe extenderse"
        )
        assert Invoice.objects.filter(
            subscription=sub_por_renovar, status=Invoice.Status.PAID,
        ).exists()

    def test_al_generar_link_se_le_avisa_al_cliente(self, sub_por_renovar):
        """Si un link ya no activa el período, mandarlo deja de ser opcional:
        sin aviso el cliente se queda sin servicio sin saber por qué."""
        from billing.tasks import process_renewals

        with patch("billing.gateway.charge_subscription", return_value=_resultado_link()), \
             patch("billing.tasks._send_email_safe") as mock_mail:
            process_renewals()

        assert mock_mail.called, "hay que avisarle al cliente con el link"
        cuerpo = " ".join(str(a) for a in mock_mail.call_args[0])
        assert "sandbox.flow.cl/pay?token=abc123" in cuerpo, (
            "el correo tiene que llevar el link de pago"
        )


@pytest.mark.django_db
class TestGatewayDistingueLinkDeCobro:
    """El gateway es la fuente de la distinción: si acá se mezcla, todo lo
    demás vuelve a fallar."""

    def test_link_de_flow_marca_paid_false(self, tenant, plan, monkeypatch):
        from billing import gateway
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
        )
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=D("35000"), status=Invoice.Status.PENDING,
            period_start=timezone.now(),
            period_end=timezone.now() + timezone.timedelta(days=30),
        )
        monkeypatch.setattr(
            gateway, "_flow_api_call",
            lambda *a, **k: {"url": "https://flow.cl/pay", "token": "tok1"},
        )
        r = gateway._create_flow_payment_link(sub, inv)
        assert r["success"] is True, "crear el link es un éxito técnico"
        assert r["paid"] is False, "…pero NO es un pago"
        assert r["gateway_tx_id"] == ""

    def test_cargo_aprobado_marca_paid_true(self, tenant, plan, monkeypatch):
        from billing import gateway
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            flow_customer_id="cus_1", card_last4="4242",
        )
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=D("35000"), status=Invoice.Status.PENDING,
            period_start=timezone.now(),
            period_end=timezone.now() + timezone.timedelta(days=30),
        )
        monkeypatch.setattr(
            gateway, "_flow_api_call",
            lambda *a, **k: {"status": 2, "flowOrder": 777},
        )
        r = gateway._flow_charge_customer(sub, inv)
        assert r["paid"] is True
        assert r["gateway_tx_id"] == "777"

    def test_cargo_rechazado_cae_a_link_y_no_queda_pagado(self, tenant, plan, monkeypatch):
        """Tarjeta rechazada → fallback a link. Ese fallback NO puede
        colarse como pago (era la segunda puerta del mismo bug)."""
        from billing import gateway
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            flow_customer_id="cus_2", card_last4="0000",
        )
        inv = Invoice.objects.create(
            subscription=sub, amount_clp=D("35000"), status=Invoice.Status.PENDING,
            period_start=timezone.now(),
            period_end=timezone.now() + timezone.timedelta(days=30),
        )

        def fake_call(method, endpoint, params):
            if endpoint == "/customer/charge":
                return {"status": 3}          # rechazado
            return {"url": "https://flow.cl/pay", "token": "tok2"}

        monkeypatch.setattr(gateway, "_flow_api_call", fake_call)
        r = gateway._flow_charge_customer(sub, inv)
        assert r["paid"] is False, "un rechazo no puede terminar en 'pagado'"
        assert r["payment_url"]
