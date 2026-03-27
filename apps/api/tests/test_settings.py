"""
Tests para el módulo de configuración: settings, stores, warehouses, users, alerts.
"""
import pytest
from core.models import User, Warehouse, AlertPreference
from stores.models import Store
from billing.models import Plan, Subscription


# ═══════════════════════════════════════════════════════════════
# 1. TENANT SETTINGS
# ═══════════════════════════════════════════════════════════════
@pytest.mark.django_db
class TestTenantSettings:

    def test_get_settings(self, api_client, tenant):
        r = api_client.get("/api/core/settings/")
        assert r.status_code == 200
        d = r.data
        assert d["id"] == tenant.id
        assert d["name"] == tenant.name
        assert "slug" in d
        assert "legal_name" in d
        assert "receipt_show_logo" in d
        assert "created_at" in d

    def test_tax_rate_is_number(self, api_client):
        r = api_client.get("/api/core/settings/")
        assert r.status_code == 200
        assert isinstance(r.data["tax_rate"], float)

    def test_patch_settings_owner(self, api_client, tenant):
        r = api_client.patch(
            "/api/core/settings/",
            {"legal_name": "Empresa SPA", "rut": "76.123.456-7"},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["ok"] is True
        assert "legal_name" in r.data["updated"]
        assert "rut" in r.data["updated"]

        tenant.refresh_from_db()
        assert tenant.legal_name == "Empresa SPA"
        assert tenant.rut == "76.123.456-7"

    def test_patch_settings_non_owner_forbidden(self, tenant, store):
        from rest_framework.test import APIClient
        cashier = User.objects.create_user(
            username="cajero_test", password="testpass123",
            tenant=tenant, active_store=store, role=User.Role.CASHIER,
        )
        client = APIClient()
        client.force_authenticate(user=cashier)
        r = client.patch(
            "/api/core/settings/",
            {"name": "Hack"},
            format="json",
        )
        assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# 2. STORE MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@pytest.mark.django_db
class TestStoreManagement:

    def test_list_stores(self, api_client, store, warehouse):
        r = api_client.get("/api/core/stores/")
        assert r.status_code == 200
        assert len(r.data) >= 1
        s = next(x for x in r.data if x["id"] == store.id)
        assert "warehouses" in s
        assert len(s["warehouses"]) >= 1

    def test_create_store_with_custom_warehouse_name(self, api_client, tenant):
        r = api_client.post(
            "/api/core/stores/",
            {"name": "Local Norte", "code": "NORTE-1", "warehouse_name": "Bodega Fría"},
            format="json",
        )
        assert r.status_code == 201
        store = Store.objects.get(id=r.data["id"])
        assert store.name == "Local Norte"
        assert store.code == "NORTE-1"
        wh = Warehouse.objects.get(store=store, tenant=tenant)
        assert wh.name == "Bodega Fría"

    def test_create_store_duplicate_name(self, api_client, store):
        r = api_client.post(
            "/api/core/stores/",
            {"name": store.name},
            format="json",
        )
        assert r.status_code == 400
        assert "ya existe" in r.data["detail"].lower()

    def test_patch_store_name(self, api_client, store):
        r = api_client.patch(
            f"/api/core/stores/{store.id}/",
            {"name": "Local Renovado", "code": "REN-1"},
            format="json",
        )
        assert r.status_code == 200
        store.refresh_from_db()
        assert store.name == "Local Renovado"
        assert store.code == "REN-1"

    def test_patch_store_toggle_active(self, api_client, tenant):
        s = Store.objects.create(tenant=tenant, name="Local Temp")
        Warehouse.objects.create(tenant=tenant, store=s, name="Bodega Temp")
        r = api_client.patch(
            f"/api/core/stores/{s.id}/",
            {"is_active": False},
            format="json",
        )
        assert r.status_code == 200
        s.refresh_from_db()
        assert s.is_active is False

    def test_patch_store_not_found(self, api_client):
        r = api_client.patch(
            "/api/core/stores/99999/",
            {"name": "No existe"},
            format="json",
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 3. WAREHOUSE MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@pytest.mark.django_db
class TestWarehouseManagement:

    def test_create_warehouse(self, api_client, tenant, store):
        r = api_client.post(
            "/api/core/warehouses/",
            {"store": store.id, "name": "Bodega Secundaria"},
            format="json",
        )
        assert r.status_code == 201
        assert r.data["name"] == "Bodega Secundaria"
        assert Warehouse.objects.filter(
            tenant=tenant, store=store, name="Bodega Secundaria",
        ).exists()

    def test_create_warehouse_duplicate_name(self, api_client, store, warehouse):
        r = api_client.post(
            "/api/core/warehouses/",
            {"store": store.id, "name": warehouse.name},
            format="json",
        )
        assert r.status_code == 400

    def test_patch_warehouse_name(self, api_client, warehouse):
        r = api_client.patch(
            f"/api/core/warehouses/{warehouse.id}/",
            {"name": "Bodega Renombrada"},
            format="json",
        )
        assert r.status_code == 200
        warehouse.refresh_from_db()
        assert warehouse.name == "Bodega Renombrada"

    def test_patch_warehouse_toggle_active(self, api_client, warehouse):
        r = api_client.patch(
            f"/api/core/warehouses/{warehouse.id}/",
            {"is_active": False},
            format="json",
        )
        assert r.status_code == 200
        warehouse.refresh_from_db()
        assert warehouse.is_active is False

    def test_patch_warehouse_not_found(self, api_client):
        r = api_client.patch(
            "/api/core/warehouses/99999/",
            {"name": "Nope"},
            format="json",
        )
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# 4. USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@pytest.mark.django_db
class TestUserManagement:

    def test_create_user(self, api_client, tenant):
        r = api_client.post(
            "/api/core/users/",
            {"username": "nuevo_cajero", "password": "password123", "role": "cashier"},
            format="json",
        )
        assert r.status_code == 201
        assert r.data["role"] == "cashier"
        u = User.objects.get(username="nuevo_cajero")
        assert u.tenant_id == tenant.id

    def test_create_user_short_password(self, api_client):
        r = api_client.post(
            "/api/core/users/",
            {"username": "fail_user", "password": "short", "role": "cashier"},
            format="json",
        )
        assert r.status_code == 400
        assert "8 caracteres" in r.data["detail"]

    def test_patch_user_role(self, api_client, tenant, store):
        user = User.objects.create_user(
            username="manager_test", password="password123",
            tenant=tenant, active_store=store, role=User.Role.MANAGER,
        )
        r = api_client.patch(
            f"/api/core/users/{user.id}/",
            {"role": "cashier"},
            format="json",
        )
        assert r.status_code == 200
        user.refresh_from_db()
        assert user.role == "cashier"

    def test_owner_cannot_demote_self(self, api_client, owner):
        r = api_client.patch(
            f"/api/core/users/{owner.id}/",
            {"role": "cashier"},
            format="json",
        )
        assert r.status_code == 400

    def test_patch_user_password_min_8(self, tenant, store):
        """Password < 8 chars should be rejected."""
        from django.core.cache import cache
        cache.clear()  # Clear throttle cache from prior tests
        from rest_framework.test import APIClient
        # Use fresh user to avoid ordering issues
        the_owner = User.objects.create_user(
            username="pw_owner_fresh", password="known_pw_123",
            tenant=tenant, active_store=store, role=User.Role.OWNER,
        )
        target = User.objects.create_user(
            username="pw_target_fresh", password="password123",
            tenant=tenant, active_store=store, role=User.Role.CASHIER,
        )
        c = APIClient()
        c.force_authenticate(user=the_owner)
        r = c.patch(
            f"/api/core/users/{target.id}/",
            {"password": "1234567", "current_password": "known_pw_123"},
            format="json",
        )
        assert r.status_code == 400
        assert "8 caracteres" in r.data["detail"]


# ═══════════════════════════════════════════════════════════════
# 5. ALERT PREFERENCES
# ═══════════════════════════════════════════════════════════════
@pytest.mark.django_db
class TestAlertPreferences:

    def test_get_defaults(self, api_client, owner):
        r = api_client.get("/api/core/alerts/")
        assert r.status_code == 200
        assert r.data["stock_bajo"] is True
        assert r.data["forecast_urgente"] is True
        assert r.data["merma_alta"] is False
        assert r.data["resumen_diario"] is False
        # Should have created a record
        assert AlertPreference.objects.filter(user=owner).exists()

    def test_patch_partial(self, api_client, owner):
        r = api_client.patch(
            "/api/core/alerts/",
            {"merma_alta": True, "stock_bajo": False},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["merma_alta"] is True
        assert r.data["stock_bajo"] is False
        # Others unchanged
        assert r.data["forecast_urgente"] is True

    def test_preferences_persist(self, api_client, owner):
        api_client.patch(
            "/api/core/alerts/",
            {"resumen_diario": True},
            format="json",
        )
        r = api_client.get("/api/core/alerts/")
        assert r.data["resumen_diario"] is True


# ═══════════════════════════════════════════════════════════════
# 6. PLAN LIMITS ENFORCEMENT
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def free_plan(db):
    plan, _ = Plan.objects.get_or_create(
        key="free",
        defaults={"name": "Gratuito", "price_clp": 0,
                  "max_products": 100, "max_stores": 1, "max_users": 1},
    )
    # Reset to known values each time
    plan.max_products = 100
    plan.max_stores = 1
    plan.max_users = 1
    plan.price_clp = 0
    plan.save(update_fields=["max_products", "max_stores", "max_users", "price_clp"])
    return plan


@pytest.fixture
def free_subscription(db, tenant, free_plan):
    sub = Subscription.objects.filter(tenant=tenant).first()
    if sub:
        sub.plan = free_plan
        sub.status = Subscription.Status.ACTIVE
        sub.save(update_fields=["plan", "status"])
        return sub
    return Subscription.objects.create(
        tenant=tenant, plan=free_plan, status=Subscription.Status.ACTIVE,
    )


@pytest.mark.django_db
class TestPlanLimitsEnforcement:

    def test_store_limit_blocks_creation(self, api_client, tenant, store, free_subscription):
        """Free plan allows 1 store — tenant already has 1, so creating another should fail."""
        r = api_client.post(
            "/api/core/stores/",
            {"name": "Segunda Tienda"},
            format="json",
        )
        assert r.status_code == 403
        assert "plan" in r.data["detail"].lower()

    def test_store_creation_allowed_with_higher_limit(self, api_client, tenant, store):
        """Plan with max_stores=5 — tenant has 1, so creating another should work."""
        plan, _ = Plan.objects.get_or_create(
            key="pro_s", defaults=dict(name="Pro Stores", price_clp=9990,
            max_products=-1, max_stores=5, max_users=-1),
        )
        sub = Subscription.objects.filter(tenant=tenant).first()
        if sub:
            sub.plan = plan
            sub.status = Subscription.Status.ACTIVE
            sub.save(update_fields=["plan", "status"])
        else:
            Subscription.objects.create(
                tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE,
            )
        r = api_client.post(
            "/api/core/stores/",
            {"name": "Segunda Tienda"},
            format="json",
        )
        assert r.status_code == 201

    def test_user_limit_blocks_creation(self, api_client, tenant, owner, free_subscription):
        """Exceeding user limit should fail with 403."""
        from core.models import User as UserModel
        from django.core.cache import cache
        cache.clear()
        # Set limit to exactly current count so next creation is over limit
        current = UserModel.objects.filter(tenant_id=tenant.id, is_active=True).count()
        Plan.objects.filter(pk=free_subscription.plan_id).update(max_users=current)
        r = api_client.post(
            "/api/core/users/",
            {"username": f"extra_user_lim_{current}", "password": "password123", "role": "cashier"},
            format="json",
        )
        assert r.status_code in (402, 403)
        detail = str(r.data.get("detail", "")).lower()
        assert "plan" in detail or "límite" in detail or "limit" in detail

    def test_user_creation_allowed_with_higher_plan(self, api_client, tenant, owner):
        """Plan with max_users=3 — tenant has 1 (owner), creating another should work."""
        pro, _ = Plan.objects.get_or_create(
            key="pro",
            defaults={"name": "Pro", "price_clp": 9990,
                      "max_products": -1, "max_stores": 1, "max_users": 3},
        )
        pro.max_users = 3
        pro.save(update_fields=["max_users"])
        Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={"plan": pro, "status": Subscription.Status.ACTIVE},
        )
        r = api_client.post(
            "/api/core/users/",
            {"username": "cajero_pro", "password": "password123", "role": "cashier"},
            format="json",
        )
        assert r.status_code == 201

    def test_no_subscription_allows_creation(self, api_client, tenant):
        """Without a subscription record, creation should be allowed (graceful fallback)."""
        r = api_client.post(
            "/api/core/stores/",
            {"name": "Tienda Sin Plan"},
            format="json",
        )
        assert r.status_code == 201
