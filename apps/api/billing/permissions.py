"""
billing/permissions.py
======================
DRF permissions that gate features based on the tenant's active plan.

Usage in views:
    from billing.permissions import RequireFeature

    class MyView(APIView):
        permission_classes = [IsAuthenticated, HasTenant, RequireFeature("has_forecast")]
"""

from rest_framework.permissions import BasePermission


# Map feature flags to user-friendly Spanish labels
_FEATURE_LABELS = {
    "has_forecast":  "Pronóstico de demanda",
    "has_abc":       "Análisis ABC",
    "has_reports":   "Reportes avanzados",
    "has_transfers": "Transferencias entre locales",
}


def RequireFeature(feature: str, min_role: str = "manager"):
    """
    Factory that returns a DRF permission class gating on:
    1. Plan boolean field (feature flag)
    2. Minimum user role (default: manager — blocks cashier)

    Returns 403 with an actionable message so the frontend can show an upgrade CTA.
    """
    label = _FEATURE_LABELS.get(feature, feature)

    # Role hierarchy for comparison
    _ROLE_LEVEL = {"owner": 4, "manager": 3, "inventory": 2, "cashier": 1}

    class _Perm(BasePermission):
        message = (
            f"{label} no está disponible en tu plan actual. "
            "Actualiza tu suscripción para acceder a esta función."
        )

        def has_permission(self, request, view):
            user = request.user
            tenant_id = getattr(user, "tenant_id", None)
            if not tenant_id:
                return False

            # Role check — block users below min_role
            user_role = getattr(user, "role", "cashier")
            user_level = _ROLE_LEVEL.get(user_role, 0)
            min_level = _ROLE_LEVEL.get(min_role, 3)
            if user_level < min_level:
                self.message = f"Se requiere rol de {min_role} o superior para acceder a {label}."
                return False

            try:
                from .models import Subscription
                sub = Subscription.objects.select_related("plan").get(
                    tenant_id=tenant_id,
                )
                # Block suspended / cancelled tenants even if plan has the feature
                if sub.status in (
                    Subscription.Status.SUSPENDED,
                    Subscription.Status.CANCELLED,
                ):
                    self.message = (
                        "Tu suscripción está suspendida. "
                        "Reactiva tu plan para acceder a esta función."
                    )
                    return False
                return bool(getattr(sub.plan, feature, False))
            except Subscription.DoesNotExist:
                return False

    _Perm.__name__ = f"RequireFeature_{feature}"
    _Perm.__qualname__ = _Perm.__name__
    return _Perm
