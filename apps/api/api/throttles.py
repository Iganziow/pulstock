from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


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
