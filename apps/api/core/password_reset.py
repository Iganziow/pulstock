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
- **Límite por IP**: 20 por hora, con scope propio (`password_reset`). Antes
  compartía scope con `sensitive_action` (acciones autenticadas): quien
  ajustara ese número para otra cosa cambiaría este sin saberlo.
- **Usuarios inactivos no reciben nada**, y tampoco se distinguen.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
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
    """De dónde cuelga el enlace.

    `WEB_ORIGIN` NO es un atributo de settings — solo existe como variable de
    entorno, que settings.py consume para armar CORS. La primera versión hacía
    `getattr(settings, "WEB_ORIGIN", ...)`, que devolvía siempre vacío y caía
    al fallback: en producción funcionaba POR COINCIDENCIA (el fallback y el
    dominio real coinciden) y en desarrollo los correos apuntaban a
    producción. Se lee del entorno, igual que CORS, y puede venir como lista
    separada por comas: se usa el primero.
    """
    import os
    crudo = os.getenv("WEB_ORIGIN", "") or "https://pulstock.cl"
    return crudo.split(",")[0].strip().rstrip("/")


class SolicitarResetView(APIView):
    """POST {email} — manda el enlace. Siempre responde lo mismo."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        correo = (request.data.get("email") or "").strip().lower()
        if not correo:
            return Response(
                {"detail": "Falta el correo."}, status=status.HTTP_400_BAD_REQUEST
            )

        # UN ENLACE POR CADA CUENTA con ese correo — no `.first()`. El flujo
        # de crear personal valida username único pero NO email único, así que
        # dos cuentas pueden compartir correo. Con `.first()` el enlace
        # resetearía una cuenta arbitraria: la persona cree recuperar la suya
        # y cambia la clave de otra. Es lo mismo que hace el PasswordResetForm
        # de Django. Cada token va amarrado a su cuenta, así que no se cruzan.
        usuarios = list(User.objects.filter(email__iexact=correo, is_active=True))

        for usuario in usuarios:
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
    throttle_scope = "password_reset"

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

        # Los MISMOS validadores que el resto de la app: rechaza claves
        # comunes ("password"), puramente numericas ("12345678") y las muy
        # parecidas al nombre o correo. Solo mirar el largo dejaba la
        # recuperacion mas debil que el registro -- justo al reves de lo que
        # corresponde, porque este es el camino que usa quien ya perdio el
        # control de su cuenta. Va aca y no antes porque los validadores
        # necesitan al usuario para comparar contra sus datos.
        try:
            validate_password(clave, user=usuario)
        except ValidationError as e:
            return Response({"detail": " ".join(e.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        usuario.set_password(clave)
        usuario.save(update_fields=["password"])

        # CERRAR LAS SESIONES ABIERTAS. El caso de uso real de "olvidé mi
        # contraseña" incluye "me robaron la cuenta" — y sin esto, cambiar la
        # clave no echa al ladrón: su refresh token sigue valiendo 7 días.
        # Revocamos todos los refresh tokens vivos del usuario; los access
        # tokens no son revocables, así que queda una ventana máxima de 1 hora
        # (su vigencia), que es el costo aceptado del diseño JWT.
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                BlacklistedToken, OutstandingToken,
            )
            vivos = OutstandingToken.objects.filter(user=usuario)
            for t in vivos:
                BlacklistedToken.objects.get_or_create(token=t)
        except Exception as exc:
            # Si la revocación falla no dejamos a la persona sin su clave
            # nueva — pero queda registrado, porque significa que las
            # sesiones viejas siguen vivas.
            logger.error("No se pudieron revocar las sesiones de user_id=%s: %s",
                         usuario.pk, exc)

        logger.info("Contrasena cambiada por recuperacion: user_id=%s", usuario.pk)

        # Cambiar la contraseña ya invalida el token (su hash forma parte del
        # token), asi que el enlace no se puede reusar.
        return Response({"ok": True, "detail": "Listo. Ya puedes entrar con tu contraseña nueva."})


class VerificarTokenView(APIView):
    """POST {uid, token} — para que la pantalla no pida una contraseña nueva
    si el enlace ya venció. Evita el escalón de escribirla y recién ahí
    enterarse.

    POST y no GET, aunque no modifique nada: nginx registra `$request`, que
    incluye el query string. Con GET, cada token VALIDO quedaba escrito en
    texto plano en /var/log/nginx/access.log, legible durante sus dos horas
    de vida por cualquiera con acceso al servidor o a una copia de los logs.
    En el cuerpo de un POST no se registra.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        uid = (request.data.get("uid") or "").strip()
        token = (request.data.get("token") or "").strip()
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
