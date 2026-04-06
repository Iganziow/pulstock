# api/auth_views.py
# Custom JWT views that set httpOnly cookies instead of returning tokens in body.
# The access token is ALSO returned in the JSON body so the frontend can read it
# for the Authorization header. The refresh token is ONLY in the cookie.

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class PulstockTokenSerializer(TokenObtainPairSerializer):
    """
    JWT token — solo claims mínimos necesarios.
    role/tenant_id se leen desde la DB en cada request (no en el token)
    para evitar information disclosure y stale claims.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Solo claim no-sensible para UX del frontend (no se usa para authz)
        token["username"] = user.username
        return token

from api.throttles import LoginRateThrottle

User = get_user_model()

_SECURE = not getattr(settings, "DEBUG", False)
_SAMESITE = "Lax"
_REFRESH_MAX_AGE = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
_ACCESS_MAX_AGE = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())


def _set_token_cookies(response, access: str, refresh: str):
    response.set_cookie(
        "access_token", access,
        max_age=_ACCESS_MAX_AGE,
        httponly=True, secure=_SECURE, samesite=_SAMESITE, path="/",
    )
    response.set_cookie(
        "refresh_token", refresh,
        max_age=_REFRESH_MAX_AGE,
        httponly=True, secure=_SECURE, samesite=_SAMESITE, path="/api/auth/",
    )


def _clear_token_cookies(response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth/")


class CookieTokenObtainView(TokenObtainPairView):
    """POST /api/auth/token/ — login, set tokens as httpOnly cookies."""
    serializer_class = PulstockTokenSerializer
    throttle_classes = [LoginRateThrottle]

    # Generic error message to prevent user enumeration
    _LOGIN_FAIL_MSG = "Usuario o contraseña incorrectos."

    def post(self, request, *args, **kwargs):
        username = request.data.get("username", "")

        # Pre-check user/tenant status — but always return GENERIC error
        # to prevent user enumeration attacks.
        user_check = None
        if username:
            user_check = User.objects.select_related("tenant").filter(username=username).first()
            if user_check:
                if not user_check.is_active or (
                    user_check.tenant_id and not user_check.tenant.is_active
                ):
                    # Return same 401 + generic message as wrong password
                    return Response({"detail": self._LOGIN_FAIL_MSG}, status=401)

        try:
            response = super().post(request, *args, **kwargs)
        except (AuthenticationFailed, InvalidToken):
            return Response({"detail": self._LOGIN_FAIL_MSG}, status=401)

        if response.status_code == 200:
            _set_token_cookies(response, response.data["access"], response.data["refresh"])
            del response.data["refresh"]
            user = user_check or User.objects.filter(username=username).first()
            if user:
                response.data["role"] = getattr(user, "role", "")
                response.data["tenant_id"] = getattr(user, "tenant_id", None)
                if user.is_superuser:
                    response.data["is_superuser"] = True
        return response


class CookieTokenRefreshView(APIView):
    """POST /api/auth/token/refresh/ — refresh using cookie, return new access."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw = request.COOKIES.get("refresh_token")
        if not raw:
            return Response({"detail": "No se encontró token de refresco"}, status=401)

        try:
            old = RefreshToken(raw)
            user_id = old.payload.get("user_id")
            old.blacklist()
        except TokenError:
            resp = Response({"detail": "Token inválido o expirado"}, status=401)
            _clear_token_cookies(resp)
            return resp

        try:
            user = User.objects.select_related("tenant").get(id=user_id)
        except User.DoesNotExist:
            resp = Response({"detail": "Usuario no encontrado"}, status=401)
            _clear_token_cookies(resp)
            return resp

        # Block refresh if user or tenant is deactivated
        if not user.is_active:
            resp = Response({"detail": "Tu cuenta ha sido desactivada."}, status=401)
            _clear_token_cookies(resp)
            return resp

        if user.tenant_id and not user.tenant.is_active:
            resp = Response({"detail": "Tu negocio ha sido suspendido."}, status=401)
            _clear_token_cookies(resp)
            return resp

        new = RefreshToken.for_user(user)
        access = str(new.access_token)
        refresh = str(new)

        response = Response({"access": access})
        _set_token_cookies(response, access, refresh)
        return response


class CookieLogoutView(APIView):
    """POST /api/auth/logout/ — blacklist refresh token and clear cookies."""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw = request.COOKIES.get("refresh_token")
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass
        response = Response({"detail": "Sesión cerrada"})
        _clear_token_cookies(response)
        return response
