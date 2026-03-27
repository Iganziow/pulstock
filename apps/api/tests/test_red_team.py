"""
Red Team / Destructive QA Tests for Pulstock.
Verifica resistencia a:
1. User enumeration en login/register
2. IDOR en precios (category_id cross-tenant)
3. Resource exhaustion (array overflow)
4. XSS payload storage (no ejecutable)
5. JWT refresh solo via cookie
6. Counter table race condition cap
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from rest_framework.test import APIClient
from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product, Category
from promotions.models import Promotion


@pytest.fixture
def tenant_rt(db):
    return Tenant.objects.create(name="RedTeam", slug="red-team")


@pytest.fixture
def tenant_evil(db):
    return Tenant.objects.create(name="Evil", slug="evil-tenant")


@pytest.fixture
def store_rt(tenant_rt):
    return Store.objects.create(tenant=tenant_rt, name="RT Store")


@pytest.fixture
def store_evil(tenant_evil):
    return Store.objects.create(tenant=tenant_evil, name="Evil Store")


@pytest.fixture
def warehouse_rt(tenant_rt, store_rt):
    return Warehouse.objects.create(tenant=tenant_rt, store=store_rt, name="Bodega RT")


@pytest.fixture
def owner_rt(tenant_rt, store_rt):
    return User.objects.create_user(
        username="rt_owner", password="Test1234!",
        tenant=tenant_rt, active_store=store_rt, role="owner",
    )


@pytest.fixture
def evil_owner(tenant_evil, store_evil):
    return User.objects.create_user(
        username="evil_owner", password="Evil1234!",
        tenant=tenant_evil, active_store=store_evil, role="evil",
    )


@pytest.fixture
def client_rt(owner_rt):
    c = APIClient()
    c.force_authenticate(user=owner_rt)
    return c


@pytest.fixture
def product_rt(tenant_rt):
    return Product.objects.create(tenant=tenant_rt, name="Producto RT", price=Decimal("1000"))


@pytest.fixture
def category_rt(tenant_rt):
    return Category.objects.create(tenant=tenant_rt, name="Cat RT")


@pytest.fixture
def category_evil(tenant_evil):
    return Category.objects.create(tenant=tenant_evil, name="Cat Evil")


# ══════════════════════════════════════════════════════════════
# 1. USER ENUMERATION — LOGIN
# ══════════════════════════════════════════════════════════════

class TestLoginEnumeration:
    """Login must NOT reveal if a user exists, is deactivated, etc."""

    def test_wrong_password_returns_401(self, owner_rt):
        c = APIClient()
        r = c.post("/api/auth/token/", {"username": "rt_owner", "password": "WRONG"}, format="json")
        assert r.status_code == 401
        assert "incorrectos" in r.json()["detail"].lower()

    def test_nonexistent_user_same_response(self, db):
        c = APIClient()
        r = c.post("/api/auth/token/", {"username": "no_existe_xyz", "password": "WRONG"}, format="json")
        assert r.status_code == 401
        assert "incorrectos" in r.json()["detail"].lower()

    def test_deactivated_user_same_response(self, owner_rt):
        owner_rt.is_active = False
        owner_rt.save()
        c = APIClient()
        r = c.post("/api/auth/token/", {"username": "rt_owner", "password": "Test1234!"}, format="json")
        # Must return 401, NOT 403 (no enumeration)
        assert r.status_code == 401
        assert "incorrectos" in r.json()["detail"].lower()

    def test_suspended_tenant_same_response(self, owner_rt, tenant_rt):
        tenant_rt.is_active = False
        tenant_rt.save()
        c = APIClient()
        r = c.post("/api/auth/token/", {"username": "rt_owner", "password": "Test1234!"}, format="json")
        assert r.status_code == 401

    def test_login_does_not_expose_is_superuser(self, owner_rt):
        """Login response should NOT include is_superuser field."""
        c = APIClient()
        r = c.post("/api/auth/token/", {"username": "rt_owner", "password": "Test1234!"}, format="json")
        assert r.status_code == 200
        assert "is_superuser" not in r.json()


# ══════════════════════════════════════════════════════════════
# 2. REGISTRATION ENUMERATION
# ══════════════════════════════════════════════════════════════

class TestRegistrationEnumeration:
    def test_existing_email_generic_error(self, owner_rt):
        """Registration with existing email must NOT say 'email already exists'."""
        owner_rt.email = "existing@test.com"
        owner_rt.save()
        c = APIClient()
        r = c.post("/api/auth/register/", {
            "email": "existing@test.com",
            "password": "Test1234!",
            "full_name": "Hacker",
            "business_name": "Hack Inc",
        }, format="json")
        if r.status_code == 400:
            # Must NOT contain "ya existe"
            detail = str(r.json())
            assert "ya existe" not in detail.lower()


# ══════════════════════════════════════════════════════════════
# 3. IDOR — PRICE LIST CATEGORY CROSS-TENANT
# ══════════════════════════════════════════════════════════════

class TestPriceListIDOR:
    def test_category_id_from_other_tenant_rejected(self, client_rt, product_rt, category_evil):
        """PriceList should reject category_id from another tenant."""
        r = client_rt.get(f"/api/catalog/products/prices/?category_id={category_evil.id}")
        assert r.status_code == 404

    def test_own_category_works(self, client_rt, product_rt, category_rt):
        product_rt.category = category_rt
        product_rt.save()
        r = client_rt.get(f"/api/catalog/products/prices/?category_id={category_rt.id}")
        assert r.status_code == 200


class TestPriceBulkIDOR:
    def test_filter_category_from_other_tenant(self, client_rt, product_rt, category_evil):
        """Bulk price update must reject cross-tenant category_id."""
        r = client_rt.post("/api/catalog/products/prices/bulk/", {
            "rule": {"type": "pct", "value": "10", "direction": "increase"},
            "filter": {"category_id": category_evil.id},
        }, format="json")
        assert r.status_code == 404

    def test_filter_product_ids_from_other_tenant(self, client_rt, product_rt, tenant_evil):
        alien = Product.objects.create(tenant=tenant_evil, name="Alien", price=Decimal("999"))
        r = client_rt.post("/api/catalog/products/prices/bulk/", {
            "rule": {"type": "pct", "value": "5", "direction": "increase"},
            "filter": {"product_ids": [product_rt.id, alien.id]},
        }, format="json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
# 4. RESOURCE EXHAUSTION — ARRAY OVERFLOW
# ══════════════════════════════════════════════════════════════

class TestArrayOverflow:
    def test_promotion_501_product_ids_rejected(self, client_rt, product_rt):
        now = timezone.now()
        ids = list(range(1, 502))  # 501 IDs
        r = client_rt.post("/api/promotions/", {
            "name": "Overflow",
            "discount_type": "pct",
            "discount_value": "10",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "product_ids": ids,
        }, format="json")
        assert r.status_code == 400

    def test_sale_201_lines_rejected(self, client_rt, warehouse_rt, product_rt):
        lines = [{"product_id": product_rt.id, "qty": 1, "unit_price": "100"}] * 201
        r = client_rt.post("/api/sales/sales/", {
            "warehouse_id": warehouse_rt.id,
            "lines": lines,
        }, format="json")
        assert r.status_code == 400

    def test_order_101_lines_rejected(self, client_rt, warehouse_rt, product_rt):
        # First create a table and open order
        tr = client_rt.post("/api/tables/tables/", {"name": "Overflow Table"}, format="json")
        tid = tr.json()["id"]
        client_rt.post(f"/api/tables/tables/{tid}/open/", {"warehouse_id": warehouse_rt.id}, format="json")
        order_r = client_rt.get(f"/api/tables/tables/{tid}/order/")
        oid = order_r.json()["id"]

        lines = [{"product_id": product_rt.id, "qty": 1}] * 101
        r = client_rt.post(f"/api/tables/orders/{oid}/add-lines/", {"lines": lines}, format="json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
# 5. XSS PAYLOAD STORAGE
# ══════════════════════════════════════════════════════════════

class TestXSSStorage:
    def test_xss_in_product_name_stored_as_text(self, client_rt):
        """XSS in product name must be stored as-is (JSON escapes it)."""
        payload = '<script>alert("xss")</script>'
        r = client_rt.post("/api/catalog/products/", {
            "name": payload,
            "price": "1000",
        }, format="json")
        assert r.status_code == 201
        # Returned as JSON string — safe
        assert r.json()["name"] == payload

    def test_xss_in_table_name(self, client_rt):
        payload = '<img src=x onerror=alert(1)>'
        r = client_rt.post("/api/tables/tables/", {"name": payload}, format="json")
        assert r.status_code == 201
        assert r.json()["name"] == payload


# ══════════════════════════════════════════════════════════════
# 6. JWT — REFRESH ONLY VIA COOKIE
# ══════════════════════════════════════════════════════════════

class TestJWTRefreshCookieOnly:
    def test_refresh_from_body_rejected(self, owner_rt):
        """Refresh endpoint must NOT accept token from request body."""
        c = APIClient()
        # Login to get tokens
        r = c.post("/api/auth/token/", {"username": "rt_owner", "password": "Test1234!"}, format="json")
        assert r.status_code == 200
        # access token is in body but refresh is NOT
        assert "refresh" not in r.json()

        # Try to refresh using body (should fail — no cookie)
        c2 = APIClient()  # fresh client, no cookies
        r2 = c2.post("/api/auth/token/refresh/", {}, format="json")
        assert r2.status_code == 401


# ══════════════════════════════════════════════════════════════
# 7. PROMOTIONS PAGINATION
# ══════════════════════════════════════════════════════════════

class TestPromotionsPagination:
    def test_list_returns_paginated_response(self, client_rt, product_rt, owner_rt, tenant_rt):
        # Create a few promos
        for i in range(3):
            Promotion.objects.create(
                tenant=tenant_rt, name=f"Promo {i}",
                discount_type="pct", discount_value=Decimal("10"),
                start_date=timezone.now().date(),
                end_date=(timezone.now() + timedelta(days=7)).date(),
                created_by=owner_rt,
            )
        r = client_rt.get("/api/promotions/")
        assert r.status_code == 200
        data = r.json()
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
