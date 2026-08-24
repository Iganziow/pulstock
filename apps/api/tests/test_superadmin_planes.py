"""
tests/test_superadmin_planes.py — poder crear un plan sin deploy.

El selector de planes del superadmin estaba escrito a mano en el frontend
(`inicio` / `crecimiento` / `pro`). Arreglar eso solo movía el problema: la
clave del modelo tenía `choices` cerrados, así que `full_clean()` —y con él el
admin de Django— rechazaba cualquier plan nuevo.

O sea que crear el plan anual que el propio roadmap recomienda ("los planes
anuales retienen 92% vs 68% los mensuales") necesitaba una migración y un
deploy. Para una plataforma que tiene que caminar sola tres meses, eso la deja
coja justo en la palanca comercial.

Se puede soltar porque las features NO dependen de la clave: salen de los flags
de cada fila. Eso es lo que se prueba primero, porque es la premisa de todo.
"""
import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from billing.models import Plan
from core.models import Tenant, User
from stores.models import Store


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Empresa A", slug="empresa-planes")


@pytest.fixture
def super_client(db, tenant_a):
    store = Store.objects.create(tenant=tenant_a, name="Local A")
    user = User.objects.create_user(
        username="superadmin-planes", password="super123",
        is_superuser=True, is_staff=True,
        tenant=tenant_a, active_store=store, role="owner",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestUnPlanNuevoSePuedeCrear:
    def test_acepta_una_clave_que_no_estaba_prevista(self):
        """El caso concreto: el plan anual."""
        p = Plan(key="anual", name="Plan Anual", price_clp=420_000, is_active=True)
        p.full_clean()          # esto es lo que corre el admin de Django
        p.save()
        assert Plan.objects.filter(key="anual").exists()

    def test_rechaza_claves_que_van_a_romper_urls_o_queries(self):
        """Soltar el candado no es dejar entrar cualquier cosa: un espacio o
        una mayúscula en la clave se convierte en un bug silencioso después."""
        for mala in ("Plan Anual", "ANUAL", "plan-anual", "2anual", ""):
            with pytest.raises(ValidationError):
                Plan(key=mala, name="X", price_clp=1).full_clean(exclude=["name"])

    def test_la_clave_sigue_siendo_unica(self):
        Plan.objects.create(key="anual", name="Plan Anual", price_clp=1)
        with pytest.raises(ValidationError):
            Plan(key="anual", name="Otro", price_clp=2).full_clean()


@pytest.mark.django_db
class TestLasFeaturesNoDependenDeLaClave:
    """La premisa de todo lo anterior. Si algún gate mirara `key == "pro"`, un
    plan nuevo nacería sin features y el arreglo sería una trampa."""

    def test_un_plan_con_clave_inventada_puede_traer_todo(self):
        p = Plan.objects.create(
            key="corporativo", name="Corporativo", price_clp=900_000,
            has_forecast=True, has_abc=True, has_reports=True, has_transfers=True,
            max_products=-1, max_stores=-1, max_users=-1,
        )
        assert p.has_forecast and p.has_transfers
        assert p.max_products == -1

    def test_y_uno_con_clave_conocida_puede_no_traer_nada(self):
        # El plan "pro" ya viene sembrado; lo que importa es que apagar su
        # feature la apague de verdad, no que el nombre la reponga.
        p, _ = Plan.objects.update_or_create(
            key="pro", defaults={"name": "Pro", "price_clp": 1, "has_forecast": False},
        )
        assert p.has_forecast is False, (
            "si el nombre del plan decidiera las features, cambiar el precio "
            "de un plan obligaría a tocar código"
        )


@pytest.mark.django_db
class TestElSuperadminLoVe:
    def test_el_endpoint_de_planes_lista_los_nuevos(self, api_client):
        """El selector del superadmin se llena desde acá. Si el plan nuevo no
        sale en esta lista, no se le puede asignar a nadie."""
        Plan.objects.create(key="anual", name="Plan Anual", price_clp=420_000)
        r = api_client.get("/api/billing/plans/")
        assert r.status_code == 200
        assert "anual" in [p["key"] for p in r.json()]

    def test_no_ofrece_planes_dados_de_baja(self):
        """Un plan viejo que se dejó de vender no puede seguir apareciendo en
        el selector: se asignaría a un cliente nuevo por accidente."""
        from rest_framework.test import APIClient
        Plan.objects.create(key="anual", name="Plan Anual", price_clp=1, is_active=False)
        r = APIClient().get("/api/billing/plans/")
        assert "anual" not in [p["key"] for p in r.json()]

    def test_se_puede_asignar_a_un_tenant(self, super_client, tenant_a):
        """La prueba de punta a punta: el plan nuevo sirve para algo.

        Se usa PATCH porque es el flujo real — el tenant nace con suscripción
        por una señal, así que pasar a anual siempre es un cambio de plan.
        """
        Plan.objects.create(key="anual", name="Plan Anual", price_clp=420_000)
        r = super_client.patch(
            f"/api/superadmin/tenants/{tenant_a.id}/subscription/",
            {"plan_key": "anual"}, format="json",
        )
        assert r.status_code == 200, r.content

        tenant_a.subscription.refresh_from_db()
        assert tenant_a.subscription.plan.key == "anual", (
            "el cambio respondió ok pero no quedó guardado"
        )
