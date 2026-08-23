"""
tests/test_b22_aviso_pago_fallido.py — el correo que avisaba nada.

`send_payment_reminders` busca suscripciones con `notified_past_due=False`
para saber a quién avisar. Pero al fallar el cobro, `services.py` ponía ese
flag en True de inmediato — con el comentario "trigger en task de
notificaciones". Quien lo escribió lo entendió como "disparar el aviso"; la
tarea lo lee como "ya avisado".

Resultado: el correo de "no pudimos procesar tu pago" no se enviaba nunca.

Con B20 desplegado esto pasó de molesto a grave. Antes, un cobro fallido
generaba un link Y activaba el período igual, así que el cliente no notaba
nada. Ahora el link no activa nada: **pierde el servicio y nadie le dice por
qué**.
"""
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.utils import timezone

from billing.models import Invoice, Plan, Subscription

D = Decimal


@pytest.fixture
def plan(db):
    return Plan.objects.create(name="Plan Pro", price_clp=D("35000"), is_active=True)


@pytest.fixture
def sub(db, tenant, plan, owner):
    owner.email = "mario@marbrava.cl"
    owner.save(update_fields=["email"])
    ahora = timezone.now()
    return Subscription.objects.create(
        tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
        current_period_start=ahora - timezone.timedelta(days=30),
        current_period_end=ahora - timezone.timedelta(minutes=5),
    )


@pytest.fixture
def factura(db, sub):
    ahora = timezone.now()
    return Invoice.objects.create(
        subscription=sub, amount_clp=D("35000"), status=Invoice.Status.PENDING,
        period_start=ahora, period_end=ahora + timezone.timedelta(days=30),
    )


@pytest.mark.django_db
class TestAvisoDePagoFallido:
    def test_al_fallar_el_cobro_queda_pendiente_de_avisar(self, sub, factura):
        """EL BUG: se marcaba como 'ya avisado' antes de avisar."""
        from billing.services import register_payment_failure

        register_payment_failure(sub, factura)
        sub.refresh_from_db()

        assert sub.status == Subscription.Status.PAST_DUE
        assert sub.notified_past_due is False, (
            "quedó marcado como avisado sin haber enviado nada: la tarea de "
            "recordatorios ya no lo va a encontrar nunca"
        )

    def test_la_tarea_encuentra_y_avisa(self, sub, factura):
        """El caso completo: falla el cobro y el cliente se entera."""
        from billing.services import register_payment_failure
        from billing.tasks import send_payment_reminders

        register_payment_failure(sub, factura)

        mail.outbox.clear()
        send_payment_reminders()

        assert len(mail.outbox) >= 1, (
            "el cliente perdió el servicio y no recibió ningún aviso"
        )
        asuntos = " ".join(m.subject for m in mail.outbox)
        assert "pago" in asuntos.lower()

    def test_no_avisa_dos_veces(self, sub, factura):
        """Después de enviar sí se marca — un aviso diario del mismo problema
        se lee como sistema roto."""
        from billing.services import register_payment_failure
        from billing.tasks import send_payment_reminders

        register_payment_failure(sub, factura)
        send_payment_reminders()
        sub.refresh_from_db()
        assert sub.notified_past_due is True

        mail.outbox.clear()
        send_payment_reminders()
        assert len(mail.outbox) == 0, "avisó dos veces del mismo fallo"

    def test_un_pago_nuevo_reabre_el_aviso(self, sub, factura):
        """Si se recupera y vuelve a fallar más adelante, tiene que avisar de
        nuevo: es un problema distinto, no el mismo repetido."""
        from billing.services import register_payment_failure
        from billing.tasks import send_payment_reminders

        register_payment_failure(sub, factura)
        send_payment_reminders()

        # Se recupera: activate_period resetea el flag (models.py:177)
        sub.notified_past_due = False
        sub.status = Subscription.Status.ACTIVE
        sub.save(update_fields=["notified_past_due", "status"])

        register_payment_failure(sub, factura)
        mail.outbox.clear()
        send_payment_reminders()
        assert len(mail.outbox) >= 1
