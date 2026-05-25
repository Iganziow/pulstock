# api/middleware.py
import uuid
import logging
import threading

from django.http import JsonResponse

_request_id_local = threading.local()


def get_current_request_id() -> str:
    return getattr(_request_id_local, "request_id", "-")


class _RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_current_request_id()
        return True


# Attach filter to root logger so all handlers pick it up
logging.getLogger().addFilter(_RequestIDFilter())


class RequestIDMiddleware:
    """
    Genera un X-Request-ID único por request.
    - Lee el header entrante X-Request-ID (útil si el load balancer lo inyecta).
    - Si no existe, genera uno nuevo (UUID4 corto de 8 chars).
    - Lo inyecta en los logs vía logging.local() y lo devuelve en la respuesta.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        request.request_id = request_id
        _request_id_local.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        _request_id_local.request_id = "-"
        return response


class HealthCheckFastPathMiddleware:
    """
    Fast-path para /api/core/health/.

    El endpoint de liveness lo pegan monitores externos (UptimeRobot,
    Brevo, etc.) cada 1-5 min. Si pasa por todo el stack de middleware
    (sesiones, CSRF, auth, JWT cookie injection, billing subscription
    middleware), gasta ~280ms de CPU por ping aunque no haga nada útil.

    Esta clase intercepta GET/HEAD a /api/core/health/ ANTES de session/
    CSRF/auth/billing y devuelve {"status":"ok"} en <5ms. Sigue siendo
    una respuesta REAL de Django (no nginx), así que confirma que el
    proceso wsgi está vivo — que es exactamente lo que un liveness debe
    probar.

    NOTA: /api/core/health/deep/ NO entra acá — ese sí debe pasar por
    todo el stack porque chequea DB, redis y cron heartbeats.
    """

    PATHS = ("/api/core/health/", "/api/core/health")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method in ("GET", "HEAD")
            and request.path in self.PATHS
        ):
            return JsonResponse({"status": "ok"})
        return self.get_response(request)


class JWTCookieMiddleware:
    """
    If the request has no Authorization header but has an access_token cookie,
    inject the cookie value as a Bearer token in the Authorization header.
    This lets SimpleJWT's JWTAuthentication work transparently with cookies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "HTTP_AUTHORIZATION" not in request.META:
            token = request.COOKIES.get("access_token")
            if token:
                request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.get_response(request)
