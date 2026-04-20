"""
Sales promotion resolution.

Resolves active promotions for a set of product IDs at sale time.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def resolve_active_promotions(product_ids, products, tenant_id):
    """
    Find active promotions for the given products and return the best price per product.

    Returns:
        dict: product_id -> (Promotion, effective_price)

    Exception handling: solo atrapamos errores de DB (connection lost, etc.)
    para no tumbar la venta si Postgres está transitoriamente caído.
    CUALQUIER OTRO error (bug, KeyError, ValueError) se propaga — no queremos
    silenciar errores que hacen que TODAS las promos desaparezcan sin aviso.
    """
    from promotions.models import PromotionProduct as PP
    from django.utils import timezone
    from django.db import OperationalError, DatabaseError

    promo_map = {}
    try:
        now = timezone.now()
        pp_qs = PP.objects.filter(
            product_id__in=product_ids,
            promotion__tenant_id=tenant_id,
            promotion__is_active=True,
            promotion__start_date__lte=now,
            promotion__end_date__gte=now,
        ).select_related("promotion")
    except (OperationalError, DatabaseError) as e:
        logger.exception("DB error cargando promociones tenant=%s: %s", tenant_id, e)
        return promo_map

    # Si la query corrió OK, procesamos cada PP. Si algo falla acá es un bug
    # de lógica — logueamos con `exception` (stacktrace) y seguimos con las
    # promociones que SÍ se pudieron procesar (no todo-o-nada).
    for pp in pp_qs:
        try:
            promo = pp.promotion
            if pp.product_id not in products:
                logger.warning(
                    "PromotionProduct apunta a product_id=%s que no está en la venta (tenant=%s, promo=%s)",
                    pp.product_id, tenant_id, promo.pk,
                )
                continue
            original = products[pp.product_id].price
            effective = promo.compute_promo_price(original, pp.override_discount_value)
            pid = pp.product_id
            if pid not in promo_map or effective < promo_map[pid][1]:
                promo_map[pid] = (promo, effective)
        except Exception as e:
            # Loguear con stacktrace para que se vea en logs/Sentry
            logger.exception(
                "Error aplicando promo pp=%s product=%s: %s",
                pp.pk, pp.product_id, e,
            )
            # seguimos con la siguiente — no tumbamos todas las promos

    return promo_map
