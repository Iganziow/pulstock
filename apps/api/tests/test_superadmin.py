"""
Tests for superadmin views.
Verifica que:
1. Solo superusers pueden acceder
2. Usuarios normales reciben 403
3. Los endpoints retornan datos correctos
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from rest_framework.test import APIClient
from core.models import Tenant, User
from stores.models import Store
from billing.models import Plan, Subscription, Invoice


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        key="pro_test", name="Pro Test", price_clp=59990,
        max_products=-1, max_stores=-1, max_users=-1,
        has_forecast=True, has_abc=True, has_reports=True, has_transfers=True,
    )


@pytest.fixture
def tenant_a(db):
    return Tenant.objects.create(name="Empresa A", slug="empresa-a")


@pytest.fixture
def tenant_b(db):
    return Tenant.objects.create(name="Empresa B", slug="empresa-b")


@pytest.fixture
def store_a(tenant_a):
    return Store.objects.create(tenant=tenant_a, name="Local A")


@pytest.fixture
def store_b(tenant_b):
    return Store.objects.create(tenant=tenant_b, name="Local B")


@pytest.fixture
def subscription_a(tenant_a, plan):
    now = timezone.now()
    sub, created = Subscription.objects.get_or_create(
        tenant=tenant_a,
        defaults={
            "plan": plan, "status": "active",
            "current_period_start": now,
            "current_period_end": now + timedelta(days=30),
        },
    )
    if not created:
        sub.plan = plan
        sub.status = "active"
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=30)
        sub.save()
    return sub


@pytest.fixture
def superuser(db, tenant_a, store_a):
    user = User.objects.create_user(
        username="superadmin", password="super123",
        is_superuser=True, is_staff=True,
        tenant=tenant_a, active_store=store_a,
        role="owner",
    )
    return user


@pytest.fixture
def normal_user(db, tenant_a, store_a):
    return User.objects.create_user(
        username="normaluser", password="normal123",
        tenant=tenant_a, active_store=store_a,
        role="owner",
    )


@pytest.fixture
def super_client(superuser):
    client = APIClient()
    client.force_authenticate(user=superuser)
    return client


@pytest.fixture
def normal_client(normal_user):
    client = APIClient()
    client.force_authenticate(user=normal_user)
    return client


# ── AUTENTICACIÓN / PERMISOS ──

class TestSuperadminAuth:
    """Solo superusers acceden a /api/superadmin/."""

    def test_anon_403(self, db):
        client = APIClient()
        r = client.get("/api/superadmin/stats/")
        assert r.status_code in (401, 403)

    def test_normal_user_403(self, normal_client):
        r = normal_client.get("/api/superadmin/stats/")
        assert r.status_code == 403

    def test_superuser_200(self, super_client, subscription_a):
        r = super_client.get("/api/superadmin/stats/")
        assert r.status_code == 200

    def test_tenant_list_normal_403(self, normal_client):
        r = normal_client.get("/api/superadmin/tenants/")
        assert r.status_code == 403

    def test_users_list_normal_403(self, normal_client):
        r = normal_client.get("/api/superadmin/users/")
        assert r.status_code == 403

    def test_invoices_normal_403(self, normal_client):
        r = normal_client.get("/api/superadmin/invoices/")
        assert r.status_code == 403


# ── PLATFORM STATS ──

class TestPlatformStats:
    def test_returns_kpis(self, super_client, subscription_a):
        r = super_client.get("/api/superadmin/stats/")
        assert r.status_code == 200
        data = r.json()
        assert "total_tenants" in data or "active_tenants" in data
        assert "mrr" in data


# ── TENANT LIST & DETAIL ──

class TestTenantViews:
    def test_list_returns_tenants(self, super_client, tenant_a, subscription_a):
        r = super_client.get("/api/superadmin/tenants/")
        assert r.status_code == 200
        data = r.json()
        # Puede ser array o paginado
        results = data if isinstance(data, list) else data.get("results", data)
        assert len(results) >= 1

    def test_list_search(self, super_client, tenant_a, subscription_a):
        r = super_client.get("/api/superadmin/tenants/?q=Empresa")
        assert r.status_code == 200

    def test_detail_existing(self, super_client, tenant_a, subscription_a):
        r = super_client.get(f"/api/superadmin/tenants/{tenant_a.id}/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Empresa A"

    def test_detail_not_found(self, super_client):
        r = super_client.get("/api/superadmin/tenants/99999/")
        assert r.status_code == 404


# ── USER MANAGEMENT ──

class TestAdminUserViews:
    def test_list_users(self, super_client, normal_user):
        r = super_client.get("/api/superadmin/users/")
        assert r.status_code == 200

    def test_create_user(self, super_client, tenant_a, store_a):
        r = super_client.post("/api/superadmin/users/create/", {
            "username": "newuser_sa",
            "email": "new@test.com",
            "password": "Pass1234!",
            "tenant_id": tenant_a.id,
            "role": "cashier",
        }, format="json")
        assert r.status_code in (200, 201)

    def test_create_user_without_tenant_fails(self, super_client):
        r = super_client.post("/api/superadmin/users/create/", {
            "username": "bad_user",
            "password": "Pass1234!",
        }, format="json")
        assert r.status_code == 400

    def test_toggle_user(self, super_client, normal_user):
        r = super_client.post(f"/api/superadmin/users/{normal_user.id}/toggle/")
        assert r.status_code == 200
        normal_user.refresh_from_db()
        assert normal_user.is_active is False
        # Toggle back
        r2 = super_client.post(f"/api/superadmin/users/{normal_user.id}/toggle/")
        assert r2.status_code == 200
        normal_user.refresh_from_db()
        assert normal_user.is_active is True

    def test_delete_user(self, super_client, tenant_a, store_a):
        doomed = User.objects.create_user(
            username="doomed", password="pass",
            tenant=tenant_a, active_store=store_a, role="cashier",
        )
        r = super_client.delete(f"/api/superadmin/users/{doomed.id}/")
        assert r.status_code in (200, 204)


# ── INVOICES ──

class TestAdminInvoiceViews:
    def test_list_invoices(self, super_client, subscription_a):
        Invoice.objects.create(
            subscription=subscription_a,
            amount_clp=59990,
            period_start=timezone.now().date(),
            period_end=(timezone.now() + timedelta(days=30)).date(),
        )
        r = super_client.get("/api/superadmin/invoices/")
        assert r.status_code == 200

    def test_filter_by_status(self, super_client, subscription_a):
        Invoice.objects.create(
            subscription=subscription_a,
            amount_clp=59990,
            status="paid",
            period_start=timezone.now().date(),
            period_end=(timezone.now() + timedelta(days=30)).date(),
        )
        r = super_client.get("/api/superadmin/invoices/?status=paid")
        assert r.status_code == 200


# ── SUBSCRIPTION ADMIN ──

class TestAdminSubscriptionView:
    def test_update_subscription_plan(self, super_client, tenant_a, subscription_a, plan):
        r = super_client.patch(
            f"/api/superadmin/tenants/{tenant_a.id}/subscription/",
            {"plan_id": plan.id},
            format="json",
        )
        assert r.status_code == 200
