"""
tests/test_destinatarios_alertas.py — a quién le llega cada alerta.

Antes: `User.objects.filter(role="owner").first()`. En Marbrava eso era UNA
persona —Mario— y sus cuatro encargados activos no recibían nada, cuando el
que hace las compras suele ser el encargado. La persona que puede actuar se
enteraba por WhatsApp.

Peor: el modelo `AlertPreference` ya tenía toggles POR USUARIO y su pantalla
en Configuración, pero el envío no los miraba. Solo servían para que el único
dueño apagara su propia alerta.
"""
from decimal import Decimal

import pytest
from django.core import mail
from django.core.management import call_command

from catalog.models import Product
from core.alert_recipients import destinatarios
from core.models import AlertPreference, User
from inventory.models import StockItem
from sales.models import Sale, SaleLine

D = Decimal


def _usuario(tenant, store, username, rol, email):
    return User.objects.create(
        username=username, tenant=tenant, active_store=store,
        role=rol, email=email, is_active=True,
    )


@pytest.fixture
def equipo(db, tenant, store, owner):
    """Un local como Marbrava: un dueño y varios encargados."""
    owner.email = "mario@marbrava.cl"
    owner.save(update_fields=["email"])
    return {
        "dueño": owner,
        "encargada": _usuario(tenant, store, "nadia", "manager", "nadia@marbrava.cl"),
        "encargado2": _usuario(tenant, store, "anais", "manager", "anais@marbrava.cl"),
        "cajero": _usuario(tenant, store, "nicol", "cashier", "nicol@marbrava.cl"),
    }


def _correos(users):
    return {u.email for u in users}


# ══════════════════════════════════════════════════════════════════════
# LA REGLA DE DESTINATARIOS
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestQuienRecibe:
    def test_le_llega_a_duenos_Y_encargados(self, tenant, equipo):
        """EL BUG: antes le llegaba solo al primer dueño."""
        recibe = _correos(destinatarios(tenant, "stock_bajo"))
        assert "mario@marbrava.cl" in recibe
        assert "nadia@marbrava.cl" in recibe, (
            "el encargado suele ser quien hace las compras: tiene que enterarse"
        )
        assert "anais@marbrava.cl" in recibe

    def test_al_cajero_no(self, tenant, equipo):
        """Un cajero no repone stock, y la alerta lleva datos de rotación que
        su rol no necesita."""
        assert "nicol@marbrava.cl" not in _correos(destinatarios(tenant, "stock_bajo"))

    def test_respeta_el_toggle_de_cada_uno(self, tenant, equipo):
        """La preferencia es POR PERSONA: que Mario se dé de baja no puede
        dejar a su encargada sin la alerta."""
        AlertPreference.objects.create(
            user=equipo["dueño"], tenant=tenant, stock_bajo=False,
        )
        recibe = _correos(destinatarios(tenant, "stock_bajo"))
        assert "mario@marbrava.cl" not in recibe
        assert "nadia@marbrava.cl" in recibe

    def test_sin_preferencias_guardadas_usa_el_default(self, tenant, equipo):
        """Nadie queda fuera por no haber entrado nunca a Configuración."""
        assert AlertPreference.objects.count() == 0
        assert len(destinatarios(tenant, "stock_bajo")) == 3

    def test_un_toggle_apagado_por_defecto_no_manda(self, tenant, equipo):
        """`merma_alta` viene en False: sin acción explícita, no se envía."""
        assert destinatarios(tenant, "merma_alta") == []

    def test_ignora_usuarios_inactivos_y_sin_correo(self, tenant, store, equipo):
        _usuario(tenant, store, "exempleado", "manager", "ex@marbrava.cl").delete()
        inactivo = _usuario(tenant, store, "patricio", "manager", "pat@marbrava.cl")
        inactivo.is_active = False
        inactivo.save(update_fields=["is_active"])
        _usuario(tenant, store, "sincorreo", "manager", "")

        recibe = _correos(destinatarios(tenant, "stock_bajo"))
        assert "pat@marbrava.cl" not in recibe
        assert "" not in recibe

    def test_no_manda_dos_veces_al_mismo_correo(self, tenant, store, equipo):
        """El dueño que además figura como encargado con la misma dirección
        recibiría dos correos idénticos, y eso se lee como sistema roto."""
        _usuario(tenant, store, "mario_2", "manager", "MARIO@marbrava.cl")
        recibe = destinatarios(tenant, "stock_bajo")
        correos = [u.email.lower() for u in recibe]
        assert len(correos) == len(set(correos)), "hay direcciones repetidas"

    def test_no_cruza_tenants(self, tenant, store, equipo, db):
        """Un encargado de otro café no puede recibir alertas ajenas."""
        from core.models import Tenant
        otro = Tenant(name="Cafe Rival", slug="cafe-rival")
        otro._skip_subscription = True
        otro.save()
        User.objects.create(
            username="rival", tenant=otro, role="owner",
            email="rival@otro.cl", is_active=True,
        )
        assert "rival@otro.cl" not in _correos(destinatarios(tenant, "stock_bajo"))


# ══════════════════════════════════════════════════════════════════════
# EL ENVÍO REAL
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEnvioMultiple:
    def _producto_quebrado(self, tenant, store, warehouse, user, category):
        p = Product.objects.create(
            tenant=tenant, name="Leche entera", sku="LE-1",
            category=category, price=D("1200"),
        )
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=p,
            on_hand=D("0"), avg_cost=D("100"),
        )
        venta = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse, created_by=user,
            subtotal=D("10000"), total=D("10000"),
            status="COMPLETED", sale_type="VENTA",
        )
        SaleLine.objects.create(
            tenant=tenant, sale=venta, product=p,
            qty=D("20"), unit_price=D("500"), unit_cost_snapshot=D("100"),
        )
        return p

    def test_la_alerta_llega_a_todo_el_equipo(
        self, tenant, store, warehouse, category, equipo,
    ):
        self._producto_quebrado(tenant, store, warehouse, equipo["dueño"], category)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        destinos = {m.to[0] for m in mail.outbox}
        assert destinos == {
            "mario@marbrava.cl", "nadia@marbrava.cl", "anais@marbrava.cl",
        }, f"llegó a {destinos}"

    def test_un_correo_por_persona_no_todos_en_copia(
        self, tenant, store, warehouse, category, equipo,
    ):
        """Con todos en copia nadie puede darse de baja por su cuenta, y
        cualquiera ve las direcciones del resto."""
        self._producto_quebrado(tenant, store, warehouse, equipo["dueño"], category)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        assert len(mail.outbox) == 3
        for m in mail.outbox:
            assert len(m.to) == 1, "cada correo va a una sola dirección"

    def test_quien_se_dio_de_baja_no_lo_recibe(
        self, tenant, store, warehouse, category, equipo,
    ):
        AlertPreference.objects.create(
            user=equipo["encargado2"], tenant=tenant, stock_bajo=False,
        )
        self._producto_quebrado(tenant, store, warehouse, equipo["dueño"], category)

        mail.outbox.clear()
        call_command("send_low_stock_alerts", verbosity=0)

        destinos = {m.to[0] for m in mail.outbox}
        assert "anais@marbrava.cl" not in destinos
        assert "mario@marbrava.cl" in destinos


# ══════════════════════════════════════════════════════════════════════
# EL ENDPOINT
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestEndpointDePreferencias:
    def test_expone_el_toggle_del_reporte_abc(self, api_client, tenant):
        """Sin este campo el reporte ABC no se podría desactivar desde la UI."""
        r = api_client.get("/api/core/alerts/")
        assert r.status_code == 200, r.content
        assert "reporte_abc" in r.json()

    def test_guarda_el_cambio(self, api_client, tenant):
        r = api_client.patch(
            "/api/core/alerts/", {"reporte_abc": False}, format="json",
        )
        assert r.status_code == 200, r.content
        assert r.json()["reporte_abc"] is False
        assert api_client.get("/api/core/alerts/").json()["reporte_abc"] is False

    def test_cada_usuario_tiene_las_suyas(self, tenant, store, equipo):
        """Cambiar las propias no puede tocar las de un compañero."""
        from rest_framework.test import APIClient
        c1, c2 = APIClient(), APIClient()
        c1.force_authenticate(user=equipo["dueño"])
        c2.force_authenticate(user=equipo["encargada"])

        c1.patch("/api/core/alerts/", {"stock_bajo": False}, format="json")

        assert c1.get("/api/core/alerts/").json()["stock_bajo"] is False
        assert c2.get("/api/core/alerts/").json()["stock_bajo"] is True
