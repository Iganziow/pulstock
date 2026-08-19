"""
tests/test_b21_b25_billing.py — los dos bugs que faltaban antes de cobrar de verdad.

B21 — La cancelación mentía
    La API respondía "tu acceso continúa hasta el fin del período actual" y el
    código ponía status=CANCELLED al instante e invalidaba el caché: 402
    inmediato. El cliente pagaba el mes y perdía el servicio el mismo día.

B25 — Sin reconciliación contra Flow
    `flow_token` se guardaba desde el primer día y nunca se leía. Si el webhook
    se perdía, la sesión quedaba PENDING para siempre: el cliente pagó y se
    queda sin cuenta.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from billing.models import CheckoutSession, Plan, Subscription

D = Decimal


@pytest.fixture
def plan(db):
    return Plan.objects.create(name="Plan Pro", price_clp=D("35000"), is_active=True)


@pytest.fixture
def sub_activa(db, tenant, plan):
    ahora = timezone.now()
    return Subscription.objects.create(
        tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
        current_period_start=ahora - timezone.timedelta(days=5),
        current_period_end=ahora + timezone.timedelta(days=25),
    )


# ══════════════════════════════════════════════════════════════════════
# B21 — la baja se agenda, no corta al instante
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestB21CancelacionAgendada:
    def test_cancelar_NO_corta_el_acceso_de_inmediato(self, sub_activa):
        """EL BUG: pagó el mes y lo perdía el mismo día."""
        from billing.services import cancel_subscription

        cancel_subscription(sub_activa, reason="muy caro")
        sub_activa.refresh_from_db()

        assert sub_activa.cancel_at_period_end is True
        assert sub_activa.status == Subscription.Status.ACTIVE, (
            "sigue activa hasta que venza lo que ya pagó"
        )
        assert sub_activa.is_access_allowed is True, (
            "el acceso NO puede cortarse el día que cancela"
        )

    def test_al_vencer_el_periodo_la_baja_se_hace_efectiva(self, sub_activa):
        """Y no se le cobra otro mes."""
        from billing.services import cancel_subscription
        from billing.tasks import process_renewals

        cancel_subscription(sub_activa, reason="cierro el local")
        # El período vence
        Subscription.objects.filter(pk=sub_activa.pk).update(
            current_period_end=timezone.now() - timezone.timedelta(minutes=1)
        )

        with patch("billing.gateway.charge_subscription") as mock_cobro:
            process_renewals()
            assert not mock_cobro.called, "no se le cobra a quien pidió la baja"

        sub_activa.refresh_from_db()
        assert sub_activa.status == Subscription.Status.CANCELLED
        assert sub_activa.is_access_allowed is False

    def test_se_puede_arrepentir_antes_de_que_venza(self, sub_activa):
        from billing.services import cancel_subscription, resume_subscription

        cancel_subscription(sub_activa, reason="lo pensé mejor")
        resume_subscription(sub_activa)
        sub_activa.refresh_from_db()

        assert sub_activa.cancel_at_period_end is False
        assert sub_activa.cancelled_at is None
        assert sub_activa.status == Subscription.Status.ACTIVE

    def test_sin_periodo_vigente_la_baja_es_inmediata(self, tenant, plan):
        """Trial sin pagar o período ya vencido: no hay nada que respetar, y
        prometerle acceso sería la misma mentira al revés."""
        from billing.services import cancel_subscription
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            current_period_end=timezone.now() - timezone.timedelta(days=1),
        )
        cancel_subscription(sub)
        sub.refresh_from_db()
        assert sub.status == Subscription.Status.CANCELLED
        assert sub.cancel_at_period_end is False

    def test_immediate_corta_ya(self, sub_activa):
        """Soporte/superadmin sí necesita cortar en el momento."""
        from billing.services import cancel_subscription
        cancel_subscription(sub_activa, reason="fraude", immediate=True)
        sub_activa.refresh_from_db()
        assert sub_activa.status == Subscription.Status.CANCELLED
        assert sub_activa.is_access_allowed is False

    def test_la_api_dice_la_verdad(self, api_client, sub_activa):
        r = api_client.post("/api/billing/subscription/cancel/",
                            {"reason": "test"}, format="json")
        assert r.status_code == 200, r.content
        data = r.json()
        assert data["cancel_at_period_end"] is True
        assert data["access_until"] is not None, (
            "si promete acceso hasta cierta fecha, la fecha tiene que venir"
        )


    def test_el_endpoint_resume_revierte_la_baja(self, api_client, sub_activa):
        """Si la baja se agenda pero no hay forma de deshacerla, el cliente que
        se arrepiente tiene que llamar a soporte."""
        api_client.post("/api/billing/subscription/cancel/",
                        {"reason": "test"}, format="json")
        r = api_client.post("/api/billing/subscription/resume/", {}, format="json")
        assert r.status_code == 200, r.content
        sub_activa.refresh_from_db()
        assert sub_activa.cancel_at_period_end is False
        assert sub_activa.status == Subscription.Status.ACTIVE

    def test_el_estado_expone_la_baja_agendada(self, api_client, sub_activa):
        """El estado sigue siendo 'active', así que sin este campo la UI no
        tiene cómo saber —ni mostrar— que la suscripción ya está de baja."""
        from billing.services import cancel_subscription
        cancel_subscription(sub_activa, reason="test")

        r = api_client.get("/api/billing/subscription/")
        assert r.status_code == 200, r.content
        data = r.json()
        assert data["status"] == "active"
        assert data["cancel_at_period_end"] is True


# ══════════════════════════════════════════════════════════════════════
# B25 — reconciliación: el webhook no es el único canal
# ══════════════════════════════════════════════════════════════════════

def _sesion_pendiente(plan, minutos_atras=30, token="tok-flow-1"):
    s = CheckoutSession.objects.create(
        plan=plan, email="nuevo@cafe.cl", status=CheckoutSession.STATUS_PENDING,
        amount_clp=plan.price_clp, flow_token=token,
        expires_at=timezone.now() + timezone.timedelta(hours=2),
    )
    CheckoutSession.objects.filter(pk=s.pk).update(
        created_at=timezone.now() - timezone.timedelta(minutes=minutos_atras)
    )
    s.refresh_from_db()
    return s


@pytest.mark.django_db
class TestB25Reconciliacion:
    def test_recupera_un_pago_cuyo_webhook_se_perdio(self, plan):
        """EL BUG: Flow cobró, el webhook no llegó, el cliente quedó sin cuenta."""
        from billing.reconcile import reconcile_pending_checkouts
        sesion = _sesion_pendiente(plan)

        with patch("billing.gateway.get_payment_status",
                   return_value={"status": 2, "flowOrder": 12345}), \
             patch("billing.views._auto_create_checkout_account") as mock_crear:
            r = reconcile_pending_checkouts()

        assert r["recuperadas"] == 1
        assert mock_crear.called, "tiene que crear la cuenta que el webhook no creó"
        assert mock_crear.call_args[0][0].pk == sesion.pk

    def test_no_toca_pagos_que_de_verdad_estan_pendientes(self, plan):
        """status != 2 en Flow: el cliente todavía no pagó. No inventamos nada."""
        from billing.reconcile import reconcile_pending_checkouts
        _sesion_pendiente(plan)

        with patch("billing.gateway.get_payment_status",
                   return_value={"status": 1}), \
             patch("billing.views._auto_create_checkout_account") as mock_crear:
            r = reconcile_pending_checkouts()

        assert r["recuperadas"] == 0
        assert not mock_crear.called

    def test_espera_antes_de_dudar_del_webhook(self, plan):
        """Flow reintenta unos minutos; consultar de inmediato sería ruido."""
        from billing.reconcile import reconcile_pending_checkouts
        _sesion_pendiente(plan, minutos_atras=2)

        with patch("billing.gateway.get_payment_status") as mock_estado:
            r = reconcile_pending_checkouts()

        assert r["revisadas"] == 0
        assert not mock_estado.called

    def test_ignora_sesiones_sin_token(self, plan):
        """Sin flow_token no hay a qué preguntarle."""
        from billing.reconcile import reconcile_pending_checkouts
        _sesion_pendiente(plan, token="")

        with patch("billing.gateway.get_payment_status") as mock_estado:
            r = reconcile_pending_checkouts()

        assert r["revisadas"] == 0
        assert not mock_estado.called

    def test_un_error_de_flow_no_tumba_la_corrida(self, plan):
        """Si Flow no responde para una sesión, seguimos con las demás."""
        from billing.reconcile import reconcile_pending_checkouts
        _sesion_pendiente(plan, token="tok-a")
        _sesion_pendiente(plan, token="tok-b")

        def flaky(token):
            if token == "tok-a":
                raise RuntimeError("timeout con Flow")
            return {"status": 2, "flowOrder": 999}

        with patch("billing.gateway.get_payment_status", side_effect=flaky), \
             patch("billing.views._auto_create_checkout_account"):
            r = reconcile_pending_checkouts()

        assert r["revisadas"] == 2
        assert r["errores"] == 1
        assert r["recuperadas"] == 1

    def test_no_revive_sesiones_muy_viejas(self, plan):
        """Más de 72h es caso de soporte, no de cron."""
        from billing.reconcile import reconcile_pending_checkouts
        _sesion_pendiente(plan, minutos_atras=60 * 24 * 5)

        with patch("billing.gateway.get_payment_status") as mock_estado:
            r = reconcile_pending_checkouts()

        assert r["revisadas"] == 0
        assert not mock_estado.called
