"""
billing.reconcile — red de seguridad para webhooks perdidos (B25).

El problema
-----------
Al contratar, se crea un `CheckoutSession` en PENDING y se guarda su
`flow_token`. Cuando el cliente paga, Flow avisa por webhook y ahí se crea la
cuenta. Si ese webhook se pierde —Flow reintenta pero no infinitamente, y basta
un deploy, un 502 de nginx o una caída de minutos— la sesión queda PENDING
**para siempre**: el cliente pagó y se queda sin cuenta, viendo "contacta a
soporte".

El `flow_token` estaba guardado desde el primer día y nunca se leía. Esta tarea
lo usa: le pregunta a Flow por cada sesión pendiente si el pago entró, y si
entró, completa la cuenta.

Por qué no basta con confiar en el webhook
------------------------------------------
El webhook es *push* y puede perderse. La reconciliación es *pull* y es
idempotente: consulta el estado real en el gateway, que es la fuente de verdad.
Es el patrón que recomiendan Stripe y Flow para no depender de un solo canal.

No duplica lógica: reusa `_auto_create_checkout_account`, que ya es idempotente
y toma un lock (`select_for_update`), así que si el webhook llega tarde y ambos
corren a la vez, solo uno crea la cuenta.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# Margen antes de dudar del webhook: Flow reintenta unos minutos, así que
# consultar antes solo generaría llamadas de más.
RECONCILE_AFTER_MINUTES = 15
# Hasta cuándo mirar hacia atrás. Más allá, la sesión ya expiró y el caso es
# para soporte, no para un cron.
RECONCILE_MAX_AGE_HOURS = 72

FLOW_STATUS_PAID = 2


def reconcile_pending_checkouts(limit: int = 50) -> dict:
    """Busca pagos que entraron a Flow pero cuyo webhook nunca llegó.

    Devuelve {"revisadas": n, "recuperadas": n, "errores": n}.
    """
    from .models import CheckoutSession
    from .gateway import get_payment_status
    from .views import _auto_create_checkout_account

    ahora = timezone.now()
    desde = ahora - timedelta(hours=RECONCILE_MAX_AGE_HOURS)
    hasta = ahora - timedelta(minutes=RECONCILE_AFTER_MINUTES)

    pendientes = (
        CheckoutSession.objects
        .filter(
            status=CheckoutSession.STATUS_PENDING,
            created_at__gte=desde,
            created_at__lte=hasta,
        )
        .exclude(flow_token="")
        .select_related("plan")
        .order_by("created_at")[:limit]
    )

    revisadas = recuperadas = errores = 0

    for sesion in pendientes:
        revisadas += 1
        try:
            estado = get_payment_status(sesion.flow_token)
        except Exception as exc:
            errores += 1
            logger.warning(
                "reconcile: no se pudo consultar Flow para session=%s: %s",
                sesion.token, exc,
            )
            continue

        if estado.get("status") != FLOW_STATUS_PAID:
            # Sigue pendiente o fue rechazado: no hay nada que recuperar.
            continue

        logger.warning(
            "reconcile: PAGO HUERFANO detectado — session=%s email=%s flowOrder=%s. "
            "El webhook nunca llegó; creando la cuenta ahora.",
            sesion.token, sesion.email, estado.get("flowOrder"),
        )
        try:
            _auto_create_checkout_account(sesion, payment_data=estado)
            recuperadas += 1
        except Exception as exc:
            errores += 1
            logger.error(
                "reconcile: falló al completar session=%s: %s",
                sesion.token, exc, exc_info=True,
            )

    if recuperadas or errores:
        logger.info(
            "reconcile_pending_checkouts: %d revisadas, %d recuperadas, %d errores",
            revisadas, recuperadas, errores,
        )
    return {"revisadas": revisadas, "recuperadas": recuperadas, "errores": errores}
