"""
billing/middleware.py
=====================
Middleware que bloquea el acceso al API si la suscripción está suspendida.

Rutas excluidas (siempre accesibles):
  - /api/auth/*     → login / refresh token
  - /api/billing/*  → gestión de suscripción y pago
  - /admin/*        → panel admin Django
  - /api/core/health/

Cómo agregar a settings.py:
  MIDDLEWARE = [
      ...
      "billing.middleware.SubscriptionAccessMiddleware",
  ]
  (Colocarlo DESPUÉS de AuthenticationMiddleware)
"""

import logging

from django.core.cache import cache
from django.db import DatabaseError, OperationalError
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


# Prefijos que siempre están disponibles, independiente del estado de pago
ALWAYS_ALLOWED_PREFIXES = [
    "/api/auth/",
    "/api/billing/",
    "/api/core/health/",
    # Agent-facing endpoints (api_key auth, not JWT) — bypass subscription check
    "/api/printing/agents/pair/",
    "/api/printing/agents/poll/",
    "/api/printing/agents/printers/",
    # Note: /api/printing/jobs/queue/ is user-facing → subscription required
    #       /api/printing/jobs/<id>/complete/ uses api_key → middleware will pass
    #       (no JWT user resolved) via the fallthrough below.
    "/admin/",
    "/static/",
]


class SubscriptionAccessMiddleware(MiddlewareMixin):

    def process_request(self, request):
        # Solo aplica a rutas de API (no landing, no Next.js)
        if not request.path.startswith("/api/"):
            return None

        # Rutas siempre accesibles
        for prefix in ALWAYS_ALLOWED_PREFIXES:
            if request.path.startswith(prefix):
                return None

        # Intentar resolver usuario JWT si no está autenticado por sesión
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            user = self._resolve_jwt_user(request)
            if user:
                request.user = user

        if not user or not user.is_authenticated:
            return None

        # Superuser siempre tiene acceso (admin)
        if user.is_superuser:
            return None

        # Sin tenant → no es un usuario del SaaS
        if not user.tenant_id:
            return None

        # Verificar suscripción (cacheado 60s para evitar query por request)
        cache_key = f"sub_access:{user.tenant_id}"
        cached = cache.get(cache_key)

        if cached is None:
            try:
                from .models import Subscription
                sub = Subscription.objects.only(
                    "status", "current_period_end", "suspended_at", "trial_ends_at"
                ).get(tenant_id=user.tenant_id)
                cached = {"allowed": sub.is_access_allowed, "status": sub.status}
            except Subscription.DoesNotExist:
                # Tenant sin suscripción → bloquear (no dar acceso gratis)
                cached = {"allowed": False, "status": "no_subscription"}
            except (DatabaseError, OperationalError):
                # Error de DB u otro problema inesperado → denegar por seguridad,
                # pero NO cachear para que el próximo request reintente la consulta.
                logger.exception("Error consultando suscripción para tenant=%s", user.tenant_id)
                return JsonResponse(
                    {
                        "detail": "Error verificando suscripción. Intenta de nuevo.",
                        "code": "subscription_check_error",
                    },
                    status=503,
                )
            cache.set(cache_key, cached, 60)

        if not cached["allowed"]:
            return JsonResponse(
                {
                    "detail": "Tu suscripción está suspendida. Actualiza tu método de pago.",
                    "code":   "subscription_suspended",
                    "status": cached["status"],
                    "action_url": "/dashboard/settings?tab=suscripcion",
                },
                status=402,
            )

        return None

    @staticmethod
    def _resolve_jwt_user(request):
        """Resolve JWT user from Authorization header at middleware level."""
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        from rest_framework.exceptions import AuthenticationFailed
        try:
            jwt_auth = JWTAuthentication()
            result = jwt_auth.authenticate(request)
            if result:
                return result[0]
        except (InvalidToken, TokenError, AuthenticationFailed):
            pass
        return None
