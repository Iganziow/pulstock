import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import Tenant, Warehouse
from stores.models import Store
from catalog.models import Category, Product
from inventory.models import StockItem

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Tenant Test", slug="tenant-test", is_active=True)


@pytest.fixture
def store(db, tenant):
    return Store.objects.create(tenant=tenant, name="Store Test", code="LOCAL-1", is_active=True)


@pytest.fixture
def user(db, tenant, store):
    u = User.objects.create_user(username="u1", password="pass123")

    # ✅ CLAVE: tu API exige user.active_store_id (y normalmente tenant)
    u.tenant = tenant
    u.active_store = store
    u.save(update_fields=["tenant", "active_store"])

    return u


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def warehouse_a(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="Bodega A", is_active=True)


@pytest.fixture
def warehouse_b(db, tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="Bodega B", is_active=True)


@pytest.fixture
def category(db, tenant):
    return Category.objects.create(tenant=tenant, name="Cat")


@pytest.fixture
def product(db, tenant, category):
    return Product.objects.create(tenant=tenant, category=category, name="Producto 1", sku="SKU-1", is_active=True)


@pytest.fixture
def stockitem_a(db, tenant, warehouse_a, product):
    return StockItem.objects.create(
        tenant=tenant,
        warehouse=warehouse_a,
        product=product,
        on_hand="0.000",
        avg_cost="0.000",
        stock_value="0.000",
    )
