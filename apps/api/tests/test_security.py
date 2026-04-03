"""
Tests de seguridad — Usuarios, Roles y Permisos
=================================================

1.  Owner no puede resetear password de otro sin confirmar su propia password
2.  Owner puede resetear su propia password sin current_password
3.  No se puede quitar el último owner del tenant
4.  Se puede quitar un owner si hay otro owner activo
5.  Usuario sin tenant recibe 403 (no auto-bootstrap)
6.  active_store solo acepta stores del tenant activas
7.  active_store rechaza store de otro tenant
8.  active_store rechaza store inactiva
9.  JWT no contiene role, tenant_id, is_superuser
10. Login response body SÍ contiene role, tenant_id
11. Cashier no puede acceder a forecast (RequireFeature + role check)
12. Manager SÍ puede acceder a forecast
13. Deactivar usuario es soft-delete (is_active=False)
14. No puedes eliminarte a ti mismo
15. No puedes desactivarte a ti mismo
"""
import pytest
from unittest.mock import patch

from django.utils import timezone

from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import User, Tenant
from stores.models import Store


# ══════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════

@pytest.fixture
def owner_user(db, tenant, store):
    user, _ = User.objects.get_or_create(
        username="sec_owner",
        defaults={
            "tenant": tenant, "active_store": store,
            "role": User.Role.OWNER,
        },
    )
    user.set_password("ownerpass123")
    user.tenant = tenant
    user.active_store = store
    user.role = User.Role.OWNER
    user.save()
    return user


@pytest.fixture
def cashier_user(db, tenant, store, owner_user):
    user, _ = User.objects.get_or_create(
        username="sec_cashier",
        defaults={
            "tenant": tenant, "active_store": store,
            "role": User.Role.CASHIER,
        },
    )
    user.set_password("cashierpass123")
    user.tenant = tenant
    user.active_store = store
    user.role = User.Role.CASHIER
    user.save()
    return user


@pytest.fixture
def manager_user(db, tenant, store, owner_user):
    user, _ = User.objects.get_or_create(
        username="sec_manager",
        defaults={
            "tenant": tenant, "active_store": store,
            "role": User.Role.MANAGER,
        },
    )
    user.set_password("managerpass123")
    user.tenant = tenant
    user.active_store = store
    user.role = User.Role.MANAGER
    user.save()
    return user


@pytest.fixture
def owner_client(owner_user):
    c = APIClient()
    c.force_authenticate(user=owner_user)
    return c


@pytest.fixture
def cashier_client(cashier_user):
    c = APIClient()
    c.force_authenticate(user=cashier_user)
    return c


@pytest.fixture
def manager_client(manager_user):
    c = APIClient()
    c.force_authenticate(user=manager_user)
    return c


@pytest.fixture
def forecast_subscription(db, tenant):
    from billing.models import Plan, Subscription
    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={
            "name": "Plan Pro", "price_clp": 59990,
            "max_products": -1, "max_stores": -1, "max_users": -1,
            "has_forecast": True, "has_abc": True,
            "has_reports": True, "has_transfers": True,
        },
    )
    for feat in ("has_forecast", "has_abc", "has_reports", "has_transfers"):
        if not getattr(plan, feat):
            setattr(plan, feat, True)
    plan.save()

    sub = Subscription.objects.filter(tenant=tenant).first()
    now = timezone.now()
    if sub:
        sub.plan = plan
        sub.status = "active"
        sub.current_period_start = now
        sub.current_period_end = now + timezone.timedelta(days=30)
        sub.save()
    else:
        sub = Subscription.objects.create(
            tenant=tenant, plan=plan, status="active",
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )
    return sub


# ══════════════════════════════════════════════════
# 1-2: PASSWORD RESET SECURITY
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestPasswordResetSecurity:

    def test_owner_cannot_reset_other_password_without_current(self, owner_client, cashier_user):
        """Owner must provide current_password to reset another user's password."""
        r = owner_client.patch(
            f"/api/core/users/{cashier_user.id}/",
            {"password": "newpass12345"},
            format="json",
        )
        assert r.status_code == 400
        assert "contraseña actual" in r.data["detail"].lower()

    def test_owner_can_reset_other_with_current_password(self, owner_client, owner_user, cashier_user):
        """Owner provides correct current_password → allowed."""
        r = owner_client.patch(
            f"/api/core/users/{cashier_user.id}/",
            {"password": "newpass12345", "current_password": "ownerpass123"},
            format="json",
        )
        assert r.status_code == 200
        assert "password" in r.data["updated"]
        # Verify new password works
        cashier_user.refresh_from_db()
        assert cashier_user.check_password("newpass12345")

    def test_wrong_current_password_rejected(self, owner_client, cashier_user):
        """Wrong current_password → 403."""
        r = owner_client.patch(
            f"/api/core/users/{cashier_user.id}/",
            {"password": "newpass12345", "current_password": "wrongpassword"},
            format="json",
        )
        assert r.status_code == 403
        assert "incorrecta" in r.data["detail"].lower()

    def test_owner_can_change_own_password_without_current(self, owner_client, owner_user):
        """Owner changing OWN password doesn't require current_password."""
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"password": "mynewpass123"},
            format="json",
        )
        assert r.status_code == 200

    def test_short_password_rejected(self, owner_client, cashier_user, owner_user):
        """Password < 8 chars → 400."""
        r = owner_client.patch(
            f"/api/core/users/{cashier_user.id}/",
            {"password": "short", "current_password": "ownerpass123"},
            format="json",
        )
        assert r.status_code == 400


# ══════════════════════════════════════════════════
# 3-4: LAST OWNER PROTECTION
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestLastOwnerProtection:

    def test_cannot_remove_last_owner(self, owner_client, owner_user):
        """Only 1 owner → can't change role to non-owner."""
        # Ensure only 1 owner exists
        User.objects.filter(
            tenant_id=owner_user.tenant_id, role="owner"
        ).exclude(pk=owner_user.pk).update(role="manager")

        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"role": "manager"},
            format="json",
        )
        # Can't remove own owner role
        assert r.status_code == 400

    def test_can_demote_owner_if_another_exists(self, owner_client, owner_user, tenant):
        """2 owners → can demote one."""
        second_owner = User.objects.create_user(
            username="second_owner_sec", password="pass123",
            tenant=tenant, active_store=owner_user.active_store,
            role=User.Role.OWNER,
        )
        r = owner_client.patch(
            f"/api/core/users/{second_owner.id}/",
            {"role": "manager"},
            format="json",
        )
        assert r.status_code == 200
        second_owner.refresh_from_db()
        assert second_owner.role == "manager"

    def test_cannot_deactivate_self(self, owner_client, owner_user):
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"is_active": False},
            format="json",
        )
        assert r.status_code == 400

    def test_cannot_delete_self(self, owner_client, owner_user):
        r = owner_client.delete(f"/api/core/users/{owner_user.id}/")
        assert r.status_code == 400


# ══════════════════════════════════════════════════
# 5: NO AUTO-BOOTSTRAP TENANT
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestNoAutoBootstrap:

    def test_user_without_tenant_gets_403(self, db):
        """User without tenant → HasTenant returns False (no auto-create)."""
        orphan = User.objects.create_user(
            username="orphan_sec", password="pass123",
            tenant=None,
        )
        c = APIClient()
        c.force_authenticate(user=orphan)
        r = c.get("/api/catalog/products/")
        assert r.status_code == 403
        # Should NOT have created a tenant
        orphan.refresh_from_db()
        assert orphan.tenant_id is None


# ══════════════════════════════════════════════════
# 6-8: ACTIVE STORE VALIDATION
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestActiveStoreValidation:

    def test_valid_store_accepted(self, owner_client, owner_user, store):
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"active_store_id": store.id},
            format="json",
        )
        assert r.status_code == 200

    def test_other_tenant_store_rejected(self, owner_client, owner_user):
        """Store from different tenant → rejected."""
        other_tenant = Tenant.objects.create(name="Other T", slug="other-t-sec")
        other_store = Store.objects.create(tenant=other_tenant, name="Other Store")
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"active_store_id": other_store.id},
            format="json",
        )
        assert r.status_code == 400
        assert "no encontrada" in r.data["detail"].lower()

    def test_inactive_store_rejected(self, owner_client, owner_user, tenant):
        """Inactive store → rejected."""
        inactive = Store.objects.create(tenant=tenant, name="Closed Store", is_active=False)
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"active_store_id": inactive.id},
            format="json",
        )
        assert r.status_code == 400

    def test_null_store_accepted(self, owner_client, owner_user):
        """Setting store to null is allowed."""
        r = owner_client.patch(
            f"/api/core/users/{owner_user.id}/",
            {"active_store_id": None},
            format="json",
        )
        assert r.status_code == 200


# ══════════════════════════════════════════════════
# 9-10: JWT CLAIMS SECURITY
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestJWTClaimsSecurity:

    def test_jwt_does_not_contain_sensitive_claims(self, owner_user):
        """JWT from login should NOT contain role, tenant_id, is_superuser."""
        import jwt as pyjwt
        # Use the actual login endpoint to get token (uses PulstockTokenSerializer)
        c = APIClient()
        r = c.post("/api/auth/token/", {
            "username": owner_user.username,
            "password": "ownerpass123",
        }, format="json")
        assert r.status_code == 200
        access = r.data["access"]
        payload = pyjwt.decode(access, options={"verify_signature": False})
        assert "is_superuser" not in payload
        assert "role" not in payload
        assert "tenant_id" not in payload
        # Should have username for frontend UX
        assert payload.get("username") == owner_user.username

    def test_login_response_includes_user_info(self, owner_user):
        """Login response body contains role and tenant_id for frontend."""
        c = APIClient()
        r = c.post("/api/auth/token/", {
            "username": owner_user.username,
            "password": "ownerpass123",
        }, format="json")
        assert r.status_code == 200
        assert r.data.get("role") == "owner"
        assert r.data.get("tenant_id") is not None


# ══════════════════════════════════════════════════
# 11-12: ROLE-BASED FEATURE ACCESS
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestRoleBasedFeatureAccess:

    def test_cashier_cannot_access_forecast(self, cashier_client, forecast_subscription):
        """Cashier is blocked by RequireFeature role check."""
        r = cashier_client.get("/api/forecast/dashboard/")
        assert r.status_code == 403

    def test_manager_can_access_forecast(self, manager_client, forecast_subscription):
        """Manager passes RequireFeature role check."""
        r = manager_client.get("/api/forecast/dashboard/")
        # 200 OK (may return empty data but should not be 403)
        assert r.status_code == 200

    def test_owner_can_access_forecast(self, owner_client, forecast_subscription):
        """Owner passes RequireFeature."""
        r = owner_client.get("/api/forecast/dashboard/")
        assert r.status_code == 200


# ══════════════════════════════════════════════════
# 13-15: USER MANAGEMENT EDGE CASES
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserManagementEdgeCases:

    def test_delete_removes_user(self, owner_client, cashier_user):
        """DELETE hard-deletes user."""
        uid = cashier_user.id
        r = owner_client.delete(f"/api/core/users/{uid}/")
        assert r.status_code == 200
        assert not User.objects.filter(pk=uid).exists()

    def test_cashier_cannot_manage_users(self, cashier_client, owner_user):
        """Cashier can't access user management endpoints."""
        r = cashier_client.get("/api/core/users/")
        assert r.status_code == 403

    def test_cashier_cannot_create_users(self, cashier_client):
        r = cashier_client.post("/api/core/users/", {
            "username": "hacker", "password": "hack12345", "role": "owner",
        }, format="json")
        assert r.status_code == 403

    def test_role_escalation_blocked(self, owner_client, cashier_user):
        """Non-owner can't change their own role (endpoint is IsOwner)."""
        # Cashier tries to make themselves owner
        c = APIClient()
        c.force_authenticate(user=cashier_user)
        r = c.patch(f"/api/core/users/{cashier_user.id}/", {"role": "owner"}, format="json")
        assert r.status_code == 403  # IsOwner permission blocks

    def test_cross_tenant_user_not_found(self, owner_client, tenant):
        """Can't access user from another tenant."""
        other_tenant = Tenant.objects.create(name="Other2", slug="other2-sec")
        other_store = Store.objects.create(tenant=other_tenant, name="S2")
        other_user = User.objects.create_user(
            username="other_tenant_user_sec", password="pass123",
            tenant=other_tenant, active_store=other_store, role="owner",
        )
        r = owner_client.patch(
            f"/api/core/users/{other_user.id}/",
            {"role": "cashier"},
            format="json",
        )
        assert r.status_code == 404
