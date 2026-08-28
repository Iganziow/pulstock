"""
Crea la cuenta de superadmin de Mario, SIN contraseña.

Cómo usarlo, desde el servidor:

    scp tools/traspaso/crear_superadmin_mario.py ignacio@65.108.148.200:/tmp/
    ssh ignacio@65.108.148.200
    cd /var/www/pulstock/apps/api
    venv/bin/python manage.py shell < /tmp/crear_superadmin_mario.py

Por qué sin contraseña
----------------------
La clave no se genera acá, no se imprime y no viaja por ningún canal: la
cuenta nace con `set_unusable_password()` y Mario se la fija él mismo entrando
por «Olvidé mi contraseña». El secreto no llega a existir fuera de su cabeza —
ni en este archivo, ni en un log, ni en el historial de una terminal.

Requiere que la recuperación de contraseña esté desplegada (commit 0c39614).

Por qué ese correo y no admin@pulstock.cl
-----------------------------------------
`pulstock.cl` NO tiene registro MX: no puede recibir correo. Una cuenta de
superadmin con esa dirección sería irrecuperable, porque el enlace se enviaría
al vacío — justo la cuenta que más necesita poder recuperarse.

`mariodennismunoz+admin@gmail.com` llega a la bandeja de Mario (Gmail entrega
el sufijo `+algo` a la casilla base) y queda separada de su cuenta diaria del
café. Cuando el MX exista, se puede cambiar desde el panel.

Por qué separada de su cuenta del café
--------------------------------------
`mariodennismunoz@gmail.com` es el dueño del negocio y queda con sesión
abierta en el POS todo el día. Si esa misma cuenta pudiera borrar negocios de
la plataforma, cualquier sesión olvidada en el mesón sería la llave maestra.

Es idempotente: si la cuenta ya existe, no la toca.
"""
from django.contrib.auth import get_user_model

User = get_user_model()

CORREO = "mariodennismunoz+admin@gmail.com"
USUARIO = "admin_pulstock"

existe = (User.objects.filter(username=USUARIO).first()
          or User.objects.filter(email__iexact=CORREO).first())

if existe:
    print("YA EXISTE -> id=%s user=%s email=%s super=%s" % (
        existe.id, existe.username, existe.email, existe.is_superuser))
else:
    u = User.objects.create(
        username=USUARIO,
        email=CORREO,
        first_name="Mario",
        last_name="Munoz",
        is_superuser=True,
        is_staff=True,
        is_active=True,
        tenant=None,          # cuenta de plataforma, no de un negocio
    )
    u.set_unusable_password()
    u.save()
    print("CREADA -> id=%s user=%s email=%s" % (u.id, u.username, u.email))
    print("")
    print("SIN CONTRASENA a proposito.")
    print("Mario entra a https://pulstock.cl/recuperar, escribe ese correo,")
    print("y fija su clave desde el enlace que le llega.")

print("")
print("--- superadmins en el sistema ---")
for x in User.objects.filter(is_superuser=True).order_by("id"):
    print("  id=%-3s %-34s activo=%s tenant=%s" % (
        x.id, x.email or "(sin correo)", x.is_active, x.tenant_id))
