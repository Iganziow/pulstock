"""
tests/test_b19_business_type.py — el tipo de negocio roto por partida doble.

Había tres verdades distintas sobre qué valores existen:

  · El modelo acepta: retail, restaurant, hardware, wholesale, pharmacy, other
  · El trial mandaba: minimarket, ferreteria, farmacia, ropa, libreria, otro
    — y el backend los guardaba SIN validar
  · El checkout mandaba los correctos… y el backend los DESCARTABA al crear
    el Tenant (los leía dos líneas antes y no los usaba)

Nada fallaba de forma visible. Simplemente todo cliente que pagaba quedaba en
"retail" y todo tenant de trial quedaba con un valor que ningún código sabe
leer, así que las tres cosas que dependen del tipo caían al default:

  1. Las unidades de medida sembradas — una cafetería necesita Porción, Taza
     y Cucharada; una ferretería, Pulgada y Galón.
  2. Los multiplicadores de feriado del forecast.
  3. La plantilla de arranque del Modo Apertura para un local nuevo.
"""
import pytest

from core.business_types import normalizar
from core.models import Tenant

VALIDOS = {c[0] for c in Tenant.BUSINESS_TYPE_CHOICES}


@pytest.mark.django_db
class TestNormalizador:
    def test_deja_pasar_los_validos(self):
        for v in VALIDOS:
            assert normalizar(v) == v

    def test_traduce_lo_que_mandaba_el_trial(self):
        """Los valores viejos llevan información: el dueño eligió algo. Se
        traducen en vez de descartarse."""
        assert normalizar("minimarket") == "retail"
        assert normalizar("ferreteria") == "hardware"
        assert normalizar("farmacia") == "pharmacy"
        assert normalizar("cafeteria") == "restaurant"
        assert normalizar("distribuidora") == "wholesale"
        assert normalizar("otro") == "other"

    def test_nunca_devuelve_algo_que_el_modelo_no_acepte(self):
        """Es el punto entero: guardar basura no rompe nada visible, y por eso
        el bug sobrevivió tanto."""
        for basura in ["", None, "   ", "panaderia", "xyz123", "RETAIL "]:
            assert normalizar(basura) in VALIDOS

    def test_no_le_importan_mayusculas_ni_espacios(self):
        assert normalizar("  Restaurant ") == "restaurant"
        assert normalizar("FERRETERIA") == "hardware"


@pytest.mark.django_db
class TestElTrialGuardaUnTipoUsable:
    def test_un_valor_viejo_del_formulario_se_traduce(self, client):
        """EL BUG: se guardaba 'ferreteria' tal cual y ningún código lo lee."""
        r = client.post(
            "/api/auth/register/",
            {
                "email": "nuevo@ferreteria.cl",
                "password": "unaclave12345",
                "business_name": "Ferretería El Tornillo",
                "business_type": "ferreteria",
                "full_name": "Juan Pérez",
            },
            content_type="application/json",
        )
        assert r.status_code in (200, 201), r.content
        t = Tenant.objects.filter(name="Ferretería El Tornillo").first()
        assert t is not None
        assert t.business_type == "hardware", (
            f"guardó {t.business_type!r}: las unidades de ferretería (Pulgada, "
            f"Galón) y los multiplicadores de feriado nunca se van a aplicar"
        )

    def test_sin_tipo_cae_al_defecto_valido(self, client):
        r = client.post(
            "/api/auth/register/",
            {
                "email": "sintipo@negocio.cl",
                "password": "unaclave12345",
                "business_name": "Negocio Sin Tipo",
                "full_name": "Ana Soto",
            },
            content_type="application/json",
        )
        assert r.status_code in (200, 201), r.content
        t = Tenant.objects.filter(name="Negocio Sin Tipo").first()
        assert t.business_type in VALIDOS


@pytest.mark.django_db
class TestElCheckoutNoDescartaElTipo:
    def test_el_tipo_elegido_llega_al_tenant(self, db):
        """EL OTRO BUG: el formulario manda 'restaurant' y el backend creaba
        el Tenant sin pasarlo, así que quedaba en 'retail' por default. Todo
        cliente que pagaba perdía su tipo."""
        from decimal import Decimal
        from django.utils import timezone
        from billing.models import CheckoutSession, Plan
        from billing.views import _auto_create_checkout_account

        plan = Plan.objects.create(
            name="Plan Pro", price_clp=Decimal("35000"), is_active=True,
        )
        sesion = CheckoutSession.objects.create(
            plan=plan, email="dueno@cafe.cl", business_name="Café Don Pedro",
            business_type="restaurant", amount_clp=plan.price_clp,
            status=CheckoutSession.STATUS_PAID,
            expires_at=timezone.now() + timezone.timedelta(hours=2),
            owner_name="Pedro Soto", owner_username="dueno@cafe.cl",
            owner_password_hash="pbkdf2_sha256$dummy",
        )

        _auto_create_checkout_account(sesion)

        t = Tenant.objects.filter(name="Café Don Pedro").first()
        assert t is not None, "no se creó el tenant"
        assert t.business_type == "restaurant", (
            f"quedó en {t.business_type!r}: una cafetería sin sus unidades de "
            f"receta ni sus multiplicadores de feriado"
        )
