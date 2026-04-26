import os
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Recrea las migraciones merge huérfanas de core que pdeploy genera al
# deployar pero que NO están commiteadas al repo (intencionalmente — ver
# docs/ops/04-deploy.md). Sin estos archivos, las migraciones que dependen
# de esos nodes no encuentran el padre y los tests fallan con
# NodeNotFoundError. Mismo patrón que `pdeploy`.
# ─────────────────────────────────────────────────────────────────────────────
# El huérfano `0018_merge_*` (recreado por pdeploy en el server) depende
# de `0017_merge_20260405_1600` que también es huérfano y depende de otros
# huérfanos en cadena. Para evitar mantener TODA la cadena en el conftest,
# usamos dependencies SIMPLIFICADAS que solo apuntan a archivos del repo.
#
# En PRODUCCIÓN, las migrations ya están aplicadas con el grafo histórico
# real — las dependencies son solo metadata de orden, no afectan el estado
# de la DB. En tests locales, este grafo simplificado es suficiente para
# que Django resuelva las leaves sin NodeNotFoundError.
_ORPHAN_MIGRATIONS = [
    ("0018_merge_0017_cronheartbeat_0017_merge_20260405_1600.py", [
        ("core", "0017_cronheartbeat"),
    ]),
]

def _recreate_orphan_merge_migrations():
    here = os.path.dirname(__file__)
    migrations_dir = os.path.join(here, "core", "migrations")
    for filename, deps in _ORPHAN_MIGRATIONS:
        target = os.path.join(migrations_dir, filename)
        if os.path.exists(target):
            continue
        deps_str = ",\n        ".join(f"({a!r}, {b!r})" for a, b in deps)
        content = (
            "# Merge migration auto-recreado para pytest. Mismo patrón que pdeploy.\n"
            "# Ver docs/ops/04-deploy.md.\n"
            "from django.db import migrations\n\n"
            "class Migration(migrations.Migration):\n"
            "    dependencies = [\n"
            f"        {deps_str},\n"
            "    ]\n"
            "    operations = []\n"
        )
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError:
            pass


_recreate_orphan_merge_migrations()


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
