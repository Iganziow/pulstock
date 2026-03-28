# api/middleware.py
import uuid
import logging
import threading

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
