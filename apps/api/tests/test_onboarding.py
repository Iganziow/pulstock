"""
tests/test_onboarding.py
========================
Comprehensive tests for the onboarding module:
- POST /api/auth/register/   (account creation, no auth)
- GET  /api/auth/onboarding-status/ (progress check, auth required)
"""
import pytest
from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APIClient

from core.models import Tenant, User, Warehouse
from stores.models import Store




# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
REGISTER_URL = "/api/auth/register/"
ONBOARDING_STATUS_URL = "/api/auth/onboarding-status/"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _disable_register_throttle(monkeypatch):
    """Disable rate limiting on RegisterView for all tests in this module."""
    from onboarding.views import RegisterView
    monkeypatch.setattr(RegisterView, "throttle_classes", [])


@pytest.fixture
def anon_client():
    """Unauthenticated API client for register endpoint."""
    return APIClient()


def _valid_payload(**overrides):
    """Return a valid registration payload, with optional overrides."""
    data = {
        "email": "nuevo@negocio.cl",
        "password": "Seg$ura1234!",
        "full_name": "Juan Perez",
        "business_name": "Ferreteria El Tornillo",
    }
    data.update(overrides)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER — SUCCESS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterSuccess:

    def test_register_valid_201(self, anon_client):
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert resp.status_code == 201
        assert resp.data["detail"] == "Cuenta creada exitosamente."

    def test_register_creates_tenant(self, anon_client):
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert Tenant.objects.filter(name="Ferreteria El Tornillo").exists()

    def test_register_creates_store(self, anon_client):
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        tenant = Tenant.objects.get(name="Ferreteria El Tornillo")
        assert Store.objects.filter(tenant=tenant).exists()

    def test_register_creates_warehouse(self, anon_client):
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        tenant = Tenant.objects.get(name="Ferreteria El Tornillo")
        assert Warehouse.objects.filter(tenant=tenant).exists()

    def test_register_creates_user(self, anon_client):
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        user = User.objects.get(email="nuevo@negocio.cl")
        assert user.username == "nuevo@negocio.cl"
        assert user.tenant is not None

    def test_register_returns_tokens(self, anon_client):
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert resp.status_code == 201
        assert "tokens" in resp.data
        assert "access" in resp.data["tokens"]

    def test_register_returns_tenant_info(self, anon_client):
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert "tenant" in resp.data
        assert resp.data["tenant"]["name"] == "Ferreteria El Tornillo"
        assert "slug" in resp.data["tenant"]

    def test_register_returns_store_info(self, anon_client):
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert "store" in resp.data
        assert resp.data["store"]["name"] == "Mi Local"  # default store name

    def test_register_returns_user_info(self, anon_client):
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert resp.data["user"]["email"] == "nuevo@negocio.cl"
        assert resp.data["user"]["full_name"] == "Juan Perez"

    def test_register_full_name_split(self, anon_client):
        """full_name is split into first_name and last_name."""
        resp = anon_client.post(
            REGISTER_URL,
            _valid_payload(full_name="Maria Gonzalez Silva", email="maria@negocio.cl"),
            format="json",
        )
        assert resp.status_code == 201
        user = User.objects.get(email="maria@negocio.cl")
        assert user.first_name == "Maria"
        assert user.last_name == "Gonzalez Silva"

    def test_register_single_name(self, anon_client):
        """A single-word name results in empty last_name."""
        resp = anon_client.post(
            REGISTER_URL,
            _valid_payload(full_name="Madonna", email="madonna@negocio.cl"),
            format="json",
        )
        assert resp.status_code == 201
        user = User.objects.get(email="madonna@negocio.cl")
        assert user.first_name == "Madonna"
        assert user.last_name == ""

    def test_register_custom_store_name(self, anon_client):
        resp = anon_client.post(
            REGISTER_URL,
            _valid_payload(store_name="Sucursal Centro", email="sucursal@negocio.cl"),
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["store"]["name"] == "Sucursal Centro"

    def test_register_email_lowercased(self, anon_client):
        anon_client.post(
            REGISTER_URL,
            _valid_payload(email="Juan@Negocio.CL", business_name="Negocio Caps"),
            format="json",
        )
        assert User.objects.filter(email="juan@negocio.cl").exists()

    def test_register_slug_generated(self, anon_client):
        anon_client.post(
            REGISTER_URL,
            _valid_payload(email="slug@negocio.cl"),
            format="json",
        )
        tenant = Tenant.objects.get(name="Ferreteria El Tornillo")
        assert tenant.slug  # not empty
        assert " " not in tenant.slug

    def test_register_user_linked_to_active_store(self, anon_client):
        anon_client.post(
            REGISTER_URL,
            _valid_payload(email="linked@negocio.cl"),
            format="json",
        )
        user = User.objects.get(email="linked@negocio.cl")
        assert user.active_store is not None
        assert user.active_store.tenant == user.tenant


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER — VALIDATION ERRORS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterValidation:

    def test_duplicate_email_400(self, anon_client):
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert resp.status_code == 400
        assert "email" in resp.data.get("errors", {})

    def test_weak_password_400(self, anon_client):
        resp = anon_client.post(
            REGISTER_URL,
            _valid_payload(password="123"),
            format="json",
        )
        assert resp.status_code == 400
        assert "password" in resp.data.get("errors", {})

    def test_common_password_400(self, anon_client):
        resp = anon_client.post(
            REGISTER_URL,
            _valid_payload(password="password1234"),
            format="json",
        )
        assert resp.status_code == 400
        assert "password" in resp.data.get("errors", {})

    def test_missing_email_400(self, anon_client):
        payload = _valid_payload()
        del payload["email"]
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 400
        assert "email" in resp.data.get("errors", {})

    def test_missing_password_400(self, anon_client):
        payload = _valid_payload()
        del payload["password"]
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 400
        assert "password" in resp.data.get("errors", {})

    def test_missing_full_name_400(self, anon_client):
        payload = _valid_payload()
        del payload["full_name"]
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 400
        assert "full_name" in resp.data.get("errors", {})

    def test_missing_business_name_400(self, anon_client):
        payload = _valid_payload()
        del payload["business_name"]
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 400
        assert "business_name" in resp.data.get("errors", {})

    def test_empty_email_400(self, anon_client):
        resp = anon_client.post(
            REGISTER_URL, _valid_payload(email=""), format="json"
        )
        assert resp.status_code == 400

    def test_empty_business_name_400(self, anon_client):
        resp = anon_client.post(
            REGISTER_URL, _valid_payload(business_name=""), format="json"
        )
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER — SLUG UNIQUENESS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterSlugUniqueness:

    def test_duplicate_business_name_gets_unique_slug(self, anon_client):
        """Two businesses with the same name get different slugs."""
        anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        resp2 = anon_client.post(
            REGISTER_URL,
            _valid_payload(email="otro@negocio.cl"),
            format="json",
        )
        assert resp2.status_code == 201
        slugs = list(Tenant.objects.values_list("slug", flat=True))
        assert len(slugs) == 2
        assert len(set(slugs)) == 2  # all unique


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER — EXTRA STORES / WAREHOUSES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestRegisterExtraStores:

    def test_extra_warehouses_created(self, anon_client):
        payload = _valid_payload(
            email="extras-wh@negocio.cl",
            extra_warehouses=["Bodega Fria", "Bodega Seca"],
        )
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 201
        tenant_id = resp.data["tenant"]["id"]
        store_id = resp.data["store"]["id"]
        # On the registration store: default warehouse + 2 extra = 3
        # (signal also creates a "Local Principal" store with its own warehouse)
        assert Warehouse.objects.filter(tenant_id=tenant_id, store_id=store_id).count() == 3
        # Verify the extra names exist
        wh_names = set(
            Warehouse.objects.filter(tenant_id=tenant_id, store_id=store_id)
            .values_list("name", flat=True)
        )
        assert "Bodega Fria" in wh_names
        assert "Bodega Seca" in wh_names

    def test_extra_stores_created(self, anon_client):
        payload = _valid_payload(
            email="extras-st@negocio.cl",
            business_name="Negocio Multi",
            extra_stores=[
                {"name": "Sucursal Norte", "warehouses": ["Bodega Norte"]},
            ],
        )
        resp = anon_client.post(REGISTER_URL, payload, format="json")
        assert resp.status_code == 201
        tenant_id = resp.data["tenant"]["id"]
        # Signal creates "Local Principal", register creates default store, + 1 extra
        # Signal store may or may not be the same as the default depending on name
        assert Store.objects.filter(tenant_id=tenant_id, name="Sucursal Norte").exists()
        # At minimum: the registration store + the extra store exist
        assert Store.objects.filter(tenant_id=tenant_id).count() >= 2


# ═══════════════════════════════════════════════════════════════════════════
# ONBOARDING STATUS
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestOnboardingStatus:

    def test_status_requires_auth(self, anon_client):
        resp = anon_client.get(ONBOARDING_STATUS_URL)
        assert resp.status_code == 401

    def test_status_after_register(self, anon_client):
        """Right after registering, business_setup and warehouse_ready should be True,
        but first_product and first_sale should be False."""
        reg_resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        assert reg_resp.status_code == 201

        # Authenticate with the returned token
        token = reg_resp.data["tokens"]["access"]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get(ONBOARDING_STATUS_URL)
        assert resp.status_code == 200
        steps = resp.data["steps"]
        assert steps["account_created"] is True
        assert steps["business_setup"] is True
        assert steps["warehouse_ready"] is True
        assert steps["first_product"] is False
        assert steps["first_sale"] is False
        assert resp.data["completed"] is False

    def test_status_progress_count(self, anon_client):
        reg_resp = anon_client.post(REGISTER_URL, _valid_payload(), format="json")
        token = reg_resp.data["tokens"]["access"]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        resp = client.get(ONBOARDING_STATUS_URL)
        assert resp.data["progress"] == 3  # account, business, warehouse
        assert resp.data["total_steps"] == 5

    def test_status_with_existing_user(self, api_client, owner, warehouse):
        """Existing owner fixture already has tenant, store, and warehouse."""
        resp = api_client.get(ONBOARDING_STATUS_URL)
        assert resp.status_code == 200
        steps = resp.data["steps"]
        assert steps["account_created"] is True
        assert steps["business_setup"] is True
        assert steps["warehouse_ready"] is True

    def test_status_with_product(self, api_client, owner, warehouse, product):
        """After adding a product, first_product step is True."""
        resp = api_client.get(ONBOARDING_STATUS_URL)
        assert resp.status_code == 200
        assert resp.data["steps"]["first_product"] is True
