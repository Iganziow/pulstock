"""
Fixtures compartidas para todos los tests.
"""
import pytest
from decimal import Decimal

from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product


@pytest.fixture
def tenant(db):
    # Skip auto-subscription so billing tests can control subscription state themselves
    t = Tenant(name="Empresa Test", slug="empresa-test")
    t._skip_subscription = True
    t.save()
    return t


@pytest.fixture
def store(db, tenant):
    obj, _ = Store.objects.get_or_create(tenant=tenant, name="Local Principal")
    return obj


@pytest.fixture
def warehouse(db, tenant, store):
    obj, _ = Warehouse.objects.get_or_create(
        tenant=tenant,
        store=store,
        name="Bodega Principal",
    )
    return obj


@pytest.fixture
def owner(db, tenant, store):
    user, _ = User.objects.get_or_create(
        username="owner_test",
        defaults={
            "tenant": tenant,
            "active_store": store,
            "role": User.Role.OWNER,
        },
    )
    # Always ensure correct state (may be stale from prior test)
    user.tenant = tenant
    user.active_store = store
    user.role = User.Role.OWNER
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def product(db, tenant):
    return Product.objects.create(
        tenant=tenant,
        name="Producto Test",
        price=Decimal("1000.00"),
        is_active=True,
    )


@pytest.fixture
def product_b(db, tenant):
    return Product.objects.create(
        tenant=tenant,
        name="Producto B",
        price=Decimal("500.00"),
        is_active=True,
    )


@pytest.fixture
def forecast_subscription(db, tenant):
    """Create a Pro subscription with has_forecast=True for the test tenant."""
    from billing.models import Plan, Subscription
    from django.utils import timezone

    plan, _ = Plan.objects.get_or_create(
        key="pro",
        defaults={
            "name": "Plan Pro", "price_clp": 59990,
            "max_products": -1, "max_stores": -1, "max_users": -1,
            "has_forecast": True, "has_abc": True,
            "has_reports": True, "has_transfers": True,
        },
    )
    changed = []
    for feat in ("has_forecast", "has_abc", "has_reports", "has_transfers"):
        if not getattr(plan, feat):
            setattr(plan, feat, True)
            changed.append(feat)
    if changed:
        plan.save(update_fields=changed)

    now = timezone.now()
    sub, _ = Subscription.objects.get_or_create(
        tenant=tenant,
        defaults={
            "plan": plan,
            "status": "active",
            "current_period_start": now,
            "current_period_end": now + timezone.timedelta(days=30),
        },
    )
    return sub


@pytest.fixture
def api_client(owner):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=owner)
    return client
