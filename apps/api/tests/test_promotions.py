"""
Tests for promotions module.
Verifica:
1. CRUD completo de promociones
2. Tenant isolation (producto de otro tenant no se puede asociar)
3. Validación: discount_value positivo, product_ids válidos
4. PATCH product_ids valida tenant (bug crítico fixeado)
5. Active promotions para productos
"""
import pytest
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product
from promotions.models import Promotion, PromotionProduct


@pytest.fixture
def tenant_promo(db):
    return Tenant.objects.create(name="Promo Tenant", slug="promo-tenant")


@pytest.fixture
def tenant_other(db):
    return Tenant.objects.create(name="Other Tenant", slug="other-tenant")


@pytest.fixture
def store_promo(tenant_promo):
    return Store.objects.create(tenant=tenant_promo, name="Promo Store")


@pytest.fixture
def owner_promo(tenant_promo, store_promo):
    user = User.objects.create_user(
        username="promo_owner", password="test123",
        tenant=tenant_promo, active_store=store_promo, role="owner",
    )
    return user


@pytest.fixture
def cashier_promo(tenant_promo, store_promo):
    return User.objects.create_user(
        username="promo_cashier", password="test123",
        tenant=tenant_promo, active_store=store_promo, role="cashier",
    )


@pytest.fixture
def promo_client(owner_promo):
    c = APIClient()
    c.force_authenticate(user=owner_promo)
    return c


@pytest.fixture
def cashier_client(cashier_promo):
    c = APIClient()
    c.force_authenticate(user=cashier_promo)
    return c


@pytest.fixture
def products(tenant_promo):
    return [
        Product.objects.create(tenant=tenant_promo, name="Coca-Cola", price=Decimal("990")),
        Product.objects.create(tenant=tenant_promo, name="Fanta", price=Decimal("890")),
        Product.objects.create(tenant=tenant_promo, name="Sprite", price=Decimal("890")),
    ]


@pytest.fixture
def other_product(tenant_other):
    return Product.objects.create(tenant=tenant_other, name="Alien Product", price=Decimal("5000"))


# ── CREATE ──

class TestPromotionCreate:
    def test_create_percentage_promo(self, promo_client, products):
        now = timezone.now()
        r = promo_client.post("/api/promotions/", {
            "name": "Promo 10%",
            "discount_type": "pct",
            "discount_value": "10",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "product_ids": [products[0].id, products[1].id],
        }, format="json")
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Promo 10%"
        assert len(data["items"]) == 2

    def test_create_fixed_promo(self, promo_client, products):
        now = timezone.now()
        r = promo_client.post("/api/promotions/", {
            "name": "Promo precio fijo",
            "discount_type": "fixed_price",
            "discount_value": "790",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=3)).isoformat(),
            "product_ids": [products[2].id],
        }, format="json")
        assert r.status_code == 201

    def test_create_with_other_tenant_product_fails(self, promo_client, products, other_product):
        now = timezone.now()
        r = promo_client.post("/api/promotions/", {
            "name": "Bad Promo",
            "discount_type": "pct",
            "discount_value": "5",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "product_ids": [products[0].id, other_product.id],
        }, format="json")
        assert r.status_code == 400
        assert "no existen" in r.json()["detail"].lower() or "activos" in r.json()["detail"].lower()

    def test_cashier_cannot_create(self, cashier_client, products):
        now = timezone.now()
        r = cashier_client.post("/api/promotions/", {
            "name": "Promo",
            "discount_type": "pct",
            "discount_value": "5",
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
            "product_ids": [products[0].id],
        }, format="json")
        assert r.status_code == 403


# ── LIST ──

class TestPromotionList:
    def test_list_returns_promos(self, promo_client, products):
        now = timezone.now()
        Promotion.objects.create(
            tenant=products[0].tenant, name="Test", discount_type="pct",
            discount_value=Decimal("10"), start_date=now.date(),
            end_date=(now + timedelta(days=7)).date(),
            created_by=User.objects.get(username="promo_owner"),
        )
        r = promo_client.get("/api/promotions/")
        assert r.status_code == 200
        data = r.json()
        results = data if isinstance(data, list) else data.get("results", [])
        assert len(results) >= 1

    def test_list_isolated_by_tenant(self, promo_client, tenant_other):
        """Promo de otro tenant no aparece."""
        Promotion.objects.create(
            tenant=tenant_other, name="Secret", discount_type="pct",
            discount_value=Decimal("50"), start_date=timezone.now().date(),
            end_date=(timezone.now() + timedelta(days=7)).date(),
        )
        r = promo_client.get("/api/promotions/")
        data = r.json()
        results = data if isinstance(data, list) else data.get("results", [])
        names = [p["name"] for p in results]
        assert "Secret" not in names


# ── DETAIL / PATCH ──

class TestPromotionDetail:
    @pytest.fixture
    def promo(self, products, owner_promo):
        now = timezone.now()
        p = Promotion.objects.create(
            tenant=products[0].tenant, name="Original",
            discount_type="pct", discount_value=Decimal("15"),
            start_date=now.date(),
            end_date=(now + timedelta(days=14)).date(),
            created_by=owner_promo,
        )
        PromotionProduct.objects.create(promotion=p, product=products[0])
        return p

    def test_get_detail(self, promo_client, promo):
        r = promo_client.get(f"/api/promotions/{promo.id}/")
        assert r.status_code == 200
        assert r.json()["name"] == "Original"

    def test_patch_name(self, promo_client, promo):
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "name": "Renamed",
        }, format="json")
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_patch_discount_value(self, promo_client, promo):
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "discount_value": "25",
        }, format="json")
        assert r.status_code == 200

    def test_patch_negative_discount_rejected(self, promo_client, promo):
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "discount_value": "-5",
        }, format="json")
        assert r.status_code == 400

    def test_patch_zero_discount_rejected(self, promo_client, promo):
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "discount_value": "0",
        }, format="json")
        assert r.status_code == 400

    def test_patch_product_ids_validates_tenant(self, promo_client, promo, other_product, products):
        """CRITICAL: PATCH product_ids no debe aceptar productos de otro tenant."""
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "product_ids": [products[0].id, other_product.id],
        }, format="json")
        assert r.status_code == 400
        assert "no existen" in r.json()["detail"].lower() or "activos" in r.json()["detail"].lower()

    def test_patch_product_ids_valid(self, promo_client, promo, products):
        r = promo_client.patch(f"/api/promotions/{promo.id}/", {
            "product_ids": [products[1].id, products[2].id],
        }, format="json")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_delete_deactivates(self, promo_client, promo):
        r = promo_client.delete(f"/api/promotions/{promo.id}/")
        assert r.status_code in (200, 204)
        promo.refresh_from_db()
        assert promo.is_active is False

    def test_get_other_tenant_promo_404(self, promo_client, tenant_other):
        other = Promotion.objects.create(
            tenant=tenant_other, name="Hidden", discount_type="pct",
            discount_value=Decimal("10"), start_date=timezone.now().date(),
            end_date=(timezone.now() + timedelta(days=7)).date(),
        )
        r = promo_client.get(f"/api/promotions/{other.id}/")
        assert r.status_code == 404


# ── ACTIVE FOR PRODUCTS ──

class TestActivePromotionsForProducts:
    def test_returns_active_promos(self, promo_client, products, owner_promo):
        now = timezone.now()
        p = Promotion.objects.create(
            tenant=products[0].tenant, name="Active Now",
            discount_type="pct", discount_value=Decimal("10"),
            start_date=(now - timedelta(days=1)).date(),
            end_date=(now + timedelta(days=7)).date(),
            is_active=True, created_by=owner_promo,
        )
        PromotionProduct.objects.create(promotion=p, product=products[0])

        r = promo_client.get(f"/api/promotions/active-for-products/?product_ids={products[0].id}")
        assert r.status_code == 200
