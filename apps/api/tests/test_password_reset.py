"""
tests/test_password_reset.py — recuperar la contraseña sin quedar expuesto.

Hasta el 27-ago-2026 no había ninguna forma de recuperar una clave perdida:
el único camino era SSH y `manage.py changepassword`. Aceptable con un
desarrollador cerca; inaceptable el día de la entrega, cuando el dueño de la
plataforma puede quedar encerrado fuera de ella.

Lo que estos tests cuidan no es tanto que funcione —eso es fácil— sino que al
agregarlo no hayamos abierto una puerta: enumeración de usuarios, tokens
reutilizables, o reset de cuentas dadas de baja.
"""
import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()

PEDIR = "/api/auth/password/reset/"
CONFIRMAR = "/api/auth/password/reset/confirm/"
CHEQUEAR = "/api/auth/password/reset/check/"


@pytest.fixture(autouse=True)
def _sin_contador_de_intentos():
    """El limite de 20/hora por IP es real y se acumula ENTRE tests, porque
    DRF lo guarda en cache. Sin esto, el septimo test del archivo empieza a
    recibir 429 y el archivo entero se vuelve dependiente del orden.

    Que haya aparecido es buena senal: el limite existe y funciona.
    """
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def persona(db, tenant):
    return User.objects.create_user(
        username="rosa", email="rosa@marbrava.cl",
        password="claveVieja123", tenant=tenant, role="owner",
    )


def _enlace_del_correo():
    """Saca uid y token del último correo enviado."""
    assert len(mail.outbox) == 1, f"se esperaba 1 correo, hay {len(mail.outbox)}"
    m = re.search(r"uid=([^&\s]+)&token=([^\s]+)", mail.outbox[0].body)
    assert m, f"el correo no trae el enlace:\n{mail.outbox[0].body}"
    return m.group(1), m.group(2)


@pytest.mark.django_db
class TestElCaminoFeliz:
    def test_pide_el_enlace_y_le_llega(self, api_client, persona):
        r = api_client.post(PEDIR, {"email": "rosa@marbrava.cl"}, format="json")
        assert r.status_code == 200
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["rosa@marbrava.cl"]
        assert "recuperar" in mail.outbox[0].subject.lower()

    def test_el_correo_no_distingue_mayusculas(self, api_client, persona):
        api_client.post(PEDIR, {"email": "ROSA@Marbrava.CL"}, format="json")
        assert len(mail.outbox) == 1

    def test_cambia_la_clave_y_puede_entrar(self, api_client, persona):
        api_client.post(PEDIR, {"email": persona.email}, format="json")
        uid, token = _enlace_del_correo()

        r = api_client.post(CONFIRMAR, {
            "uid": uid, "token": token, "password": "claveNueva456",
        }, format="json")
        assert r.status_code == 200, r.data

        persona.refresh_from_db()
        assert persona.check_password("claveNueva456")
        assert not persona.check_password("claveVieja123")

    def test_la_pantalla_puede_verificar_antes_de_pedir_la_clave(self, api_client, persona):
        api_client.post(PEDIR, {"email": persona.email}, format="json")
        uid, token = _enlace_del_correo()
        r = api_client.get(f"{CHEQUEAR}?uid={uid}&token={token}")
        assert r.status_code == 200 and r.data["valido"] is True


@pytest.mark.django_db
class TestNoAbrimosUnaPuerta:
    def test_no_revela_si_el_correo_existe(self, api_client, persona):
        """LA TRAMPA PRINCIPAL.

        Un formulario que contesta distinto para un correo registrado que para
        uno inventado es una lista de usuarios válidos servida gratis. La
        respuesta tiene que ser idéntica: mismo código y mismo texto.
        """
        r1 = api_client.post(PEDIR, {"email": "rosa@marbrava.cl"}, format="json")
        mail.outbox.clear()
        r2 = api_client.post(PEDIR, {"email": "nadie@ejemplo.cl"}, format="json")

        assert r1.status_code == r2.status_code == 200
        assert r1.data == r2.data, "las respuestas se distinguen entre sí"
        assert len(mail.outbox) == 0, "le mandó correo a una cuenta que no existe"

    def test_una_cuenta_dada_de_baja_no_recibe_nada(self, api_client, persona):
        persona.is_active = False
        persona.save(update_fields=["is_active"])
        r = api_client.post(PEDIR, {"email": persona.email}, format="json")
        assert r.status_code == 200
        assert len(mail.outbox) == 0

    def test_el_enlace_sirve_una_sola_vez(self, api_client, persona):
        """Usado el token, el hash de la contraseña cambia y el token muere.
        Si se pudiera reusar, un correo viejo filtrado sería una llave viva."""
        api_client.post(PEDIR, {"email": persona.email}, format="json")
        uid, token = _enlace_del_correo()

        primera = api_client.post(CONFIRMAR, {
            "uid": uid, "token": token, "password": "claveNueva456"}, format="json")
        assert primera.status_code == 200

        segunda = api_client.post(CONFIRMAR, {
            "uid": uid, "token": token, "password": "otraDistinta789"}, format="json")
        assert segunda.status_code == 400, "el enlace se pudo usar dos veces"

        persona.refresh_from_db()
        assert persona.check_password("claveNueva456")

    def test_un_token_inventado_no_sirve(self, api_client, persona):
        uid = urlsafe_base64_encode(force_bytes(persona.pk))
        r = api_client.post(CONFIRMAR, {
            "uid": uid, "token": "esto-no-es-un-token", "password": "loQueSea123",
        }, format="json")
        assert r.status_code == 400
        persona.refresh_from_db()
        assert persona.check_password("claveVieja123")

    def test_el_token_de_una_persona_no_sirve_para_otra(self, api_client, persona, tenant):
        otra = User.objects.create_user(
            username="otro", email="otro@marbrava.cl",
            password="suyaPropia123", tenant=tenant, role="cashier",
        )
        token_de_otra = default_token_generator.make_token(otra)
        uid_de_persona = urlsafe_base64_encode(force_bytes(persona.pk))

        r = api_client.post(CONFIRMAR, {
            "uid": uid_de_persona, "token": token_de_otra, "password": "intruso123",
        }, format="json")
        assert r.status_code == 400
        persona.refresh_from_db()
        assert persona.check_password("claveVieja123")

    def test_un_uid_corrupto_no_revienta(self, api_client):
        for basura in ("%%%", "aaaa", "", "99999999999999999999"):
            r = api_client.post(CONFIRMAR, {
                "uid": basura, "token": "x", "password": "loQueSea123"}, format="json")
            assert r.status_code == 400, f"uid {basura!r} devolvió {r.status_code}"

    def test_rechaza_contrasenas_cortas(self, api_client, persona):
        api_client.post(PEDIR, {"email": persona.email}, format="json")
        uid, token = _enlace_del_correo()
        r = api_client.post(CONFIRMAR, {
            "uid": uid, "token": token, "password": "corta"}, format="json")
        assert r.status_code == 400
        persona.refresh_from_db()
        assert persona.check_password("claveVieja123")

    def test_si_el_correo_falla_la_respuesta_no_cambia(self, api_client, persona, monkeypatch):
        """Brevo puede caerse o agotar su cuota. Si en ese caso la respuesta
        fuera distinta, volveríamos a distinguir un correo real de uno
        inventado — por la puerta de atrás."""
        def explota(*a, **k):
            raise RuntimeError("Brevo caído")
        monkeypatch.setattr("core.password_reset.send_mail", explota)

        r = api_client.post(PEDIR, {"email": persona.email}, format="json")
        assert r.status_code == 200
        assert r.data == {
            "ok": True,
            "detail": (
                "Si ese correo tiene una cuenta, le enviamos un enlace para crear una "
                "contraseña nueva. Revisa también la carpeta de spam."
            ),
        }


@pytest.mark.django_db
class TestElSuperadminTambien:
    def test_un_superadmin_puede_recuperar_su_clave(self, api_client, db):
        """El caso que motiva todo esto: el dueño de la plataforma, encerrado
        fuera de la plataforma, sin desarrollador a quien llamar."""
        jefe = User.objects.create_user(
            username="jefe", email="admin@pulstock.cl",
            password="claveVieja123", is_superuser=True, is_staff=True,
        )
        api_client.post(PEDIR, {"email": jefe.email}, format="json")
        uid, token = _enlace_del_correo()

        r = api_client.post(CONFIRMAR, {
            "uid": uid, "token": token, "password": "claveNueva456"}, format="json")
        assert r.status_code == 200

        jefe.refresh_from_db()
        assert jefe.check_password("claveNueva456")
        assert jefe.is_superuser, "recuperar la clave no debe tocar los permisos"
