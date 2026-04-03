from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


class TenantRateThrottle(SimpleRateThrottle):
    """Rate limit per tenant — prevents a single tenant from overwhelming the API.
    All users of the same tenant share the 5000 req/hour limit."""
    scope = "tenant"

    def get_cache_key(self, request, view):
        tenant_id = getattr(request.user, "tenant_id", None) if hasattr(request, "user") else None
        if not tenant_id:
            return None
        return self.cache_format % {"scope": self.scope, "ident": tenant_id}


class LoginRateThrottle(AnonRateThrottle):
    """Límite estricto para el endpoint de obtención de tokens (login)."""
    scope = "login"


class RegisterRateThrottle(AnonRateThrottle):
    """Límite para registro de nuevas cuentas (previene creación masiva)."""
    scope = "register"


class SensitiveActionThrottle(UserRateThrottle):
    """Límite para acciones sensibles: cambio de password, creación/edición de usuarios."""
    scope = "sensitive_action"


class WebhookRateThrottle(AnonRateThrottle):
    """Límite para webhooks de pasarela de pago (previene abuse/DoS)."""
    scope = "webhook"
