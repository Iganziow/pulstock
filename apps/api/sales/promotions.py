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
    """
    promo_map = {}
    try:
        from promotions.models import PromotionProduct as PP
        from django.utils import timezone

        now = timezone.now()
        pp_qs = PP.objects.filter(
            product_id__in=product_ids,
            promotion__tenant_id=tenant_id,
            promotion__is_active=True,
            promotion__start_date__lte=now,
            promotion__end_date__gte=now,
        ).select_related("promotion")

        for pp in pp_qs:
            promo = pp.promotion
            original = products[pp.product_id].price
            effective = promo.compute_promo_price(original, pp.override_discount_value)
            pid = pp.product_id
            if pid not in promo_map or effective < promo_map[pid][1]:
                promo_map[pid] = (promo, effective)
    except Exception as e:
        logger.warning("Error cargando promociones para venta (tenant=%s): %s", tenant_id, e)

    return promo_map
