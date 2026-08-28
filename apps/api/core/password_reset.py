"""
Recuperación de contraseña por correo.

Por qué existe
--------------
Hasta el 27-ago-2026 el sistema no tenía ninguna forma de recuperar una
contraseña perdida. La única manera de cambiar una clave era que el dueño
cambiara la de otro usuario — sabiendo la suya. Si el dueño perdía la propia,
el único camino era entrar por SSH y correr `manage.py changepassword`.

Eso es aceptable mientras hay un desarrollador. Deja de serlo el día de la
entrega: el superadmin de la plataforma, encerrado fuera de la plataforma que
compró, esperando a alguien que ya no está.

Decisiones de seguridad
-----------------------
- **No se revela si el correo existe.** La respuesta es siempre la misma, con
  el mismo texto y el mismo código. Un formulario que contesta distinto para
  un correo registrado es una lista de usuarios válidos servida gratis.
- **Token firmado de Django** (`default_token_generator`): lleva dentro el
  hash de la contraseña actual y el `last_login`, así que se invalida solo al
  usarse, y también si la persona entra por otro lado mientras tanto.
- **Dos horas de vigencia** (`PASSWORD_RESET_TIMEOUT`). El default de Django
  son tres días, demasiado para un correo que puede quedar en una bandeja
  compartida.
- **Límite por IP**: 20 por hora. Sin eso, el formulario es un cañón de correo
  gratis contra cualquier dirección.
- **Usuarios inactivos no reciben nada**, y tampoco se distinguen.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)
User = get_user_model()

# Misma respuesta pase lo que pase: exista el correo o no, esté activo o no.
RESPUESTA_NEUTRA = {
    "ok": True,
    "detail": (
        "Si ese correo tiene una cuenta, le enviamos un enlace para crear una "
        "contraseña nueva. Revisa también la carpeta de spam."
    ),
}

ASUNTO = "Pulstock — recuperar tu contraseña"

CUERPO = """Hola{saludo}:

Alguien pidió recuperar la contraseña de tu cuenta en Pulstock.

Para crear una nueva, entra acá:

{enlace}

El enlace vence en 2 horas y sirve una sola vez.

Si no fuiste tú, no tienes que hacer nada: tu contraseña actual sigue
funcionando y nadie puede entrar con este correo.

--
Pulstock
"""


def _url_base():
    """De dónde cuelga el enlace. `WEB_ORIGIN` es la misma variable que usa CORS."""
    return (getattr(settings, "WEB_ORIGIN", "") or "https://pulstock.cl").rstrip("/")


class SolicitarResetView(APIView):
    """POST {email} — manda el enlace. Siempre responde lo mismo."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive_action"

    def post(self, request):
        correo = (request.data.get("email") or "").strip().lower()
        if not correo:
            return Response(
                {"detail": "Falta el correo."}, status=status.HTTP_400_BAD_REQUEST
            )

        # `filter().first()` y no `get()`: si por un arrastre histórico hubiera
        # dos cuentas con el mismo correo, un get() lanzaría MultipleObjectsReturned
        # y el error 500 delataría justamente lo que no queremos delatar.
        usuario = User.objects.filter(email__iexact=correo, is_active=True).first()

        if usuario:
            token = default_token_generator.make_token(usuario)
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            enlace = f"{_url_base()}/recuperar/nueva?uid={uid}&token={token}"
            nombre = (getattr(usuario, "first_name", "") or "").strip()
            try:
                send_mail(
                    ASUNTO,
                    CUERPO.format(saludo=f" {nombre}" if nombre else "", enlace=enlace),
                    settings.DEFAULT_FROM_EMAIL,
                    [usuario.email],
                    fail_silently=False,
                )
                logger.info("Enlace de recuperacion enviado a user_id=%s", usuario.pk)
            except Exception as exc:
                # El correo puede fallar (Brevo caído, cuota agotada). Se
                # registra para poder diagnosticarlo, pero la respuesta al
                # visitante NO cambia: distinguir "no se pudo enviar" de "ese
                # correo no existe" vuelve a abrir la enumeración de usuarios.
                logger.error("Fallo el envio de recuperacion a user_id=%s: %s",
                             usuario.pk, exc)

        return Response(RESPUESTA_NEUTRA)


class ConfirmarResetView(APIView):
    """POST {uid, token, password} — fija la contraseña nueva."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive_action"

    def post(self, request):
        uid = (request.data.get("uid") or "").strip()
        token = (request.data.get("token") or "").strip()
        clave = (request.data.get("password") or "").strip()

        if len(clave) < 8:
            return Response(
                {"detail": "La contraseña debe tener al menos 8 caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario = None
        if uid:
            try:
                usuario = User.objects.filter(
                    pk=force_str(urlsafe_base64_decode(uid)), is_active=True
                ).first()
            except (TypeError, ValueError, OverflowError):
                usuario = None

        # Acá SÍ decimos que el enlace no sirve: llegar con un token invalido
        # no revela nada — quien lo tiene ya lo tenia. Y sin este mensaje la
        # persona se queda mirando un formulario que no hace nada.
        if not usuario or not default_token_generator.check_token(usuario, token):
            return Response(
                {"detail": "El enlace no es válido o ya venció. Pide uno nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario.set_password(clave)
        usuario.save(update_fields=["password"])
        logger.info("Contrasena cambiada por recuperacion: user_id=%s", usuario.pk)

        # Cambiar la contraseña ya invalida el token (su hash forma parte del
        # token), asi que el enlace no se puede reusar.
        return Response({"ok": True, "detail": "Listo. Ya puedes entrar con tu contraseña nueva."})


class VerificarTokenView(APIView):
    """GET ?uid=&token= — para que la pantalla no pida una contraseña nueva
    si el enlace ya venció. Evita el escalón de escribirla y recién ahí
    enterarse."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensitive_action"

    def get(self, request):
        uid = (request.query_params.get("uid") or "").strip()
        token = (request.query_params.get("token") or "").strip()
        usuario = None
        if uid:
            try:
                usuario = User.objects.filter(
                    pk=force_str(urlsafe_base64_decode(uid)), is_active=True
                ).first()
            except (TypeError, ValueError, OverflowError):
                usuario = None
        valido = bool(usuario and default_token_generator.check_token(usuario, token))
        return Response({"valido": valido})
