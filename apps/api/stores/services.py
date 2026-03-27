from django.db import transaction
from django.utils.text import slugify

from core.models import Tenant, Warehouse
from stores.models import Store


def _unique_slug(base: str) -> str:
    base = slugify(base)[:70] or "tenant"
    slug = base
    i = 2
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


@transaction.atomic
def ensure_user_tenant_and_store(user):
    """
    Garantiza:
    - user.tenant existe
    - user.active_store existe
    - tenant.default_warehouse existe y queda asociada al store
    """
    if user.tenant_id:
        # asegurar store activo
        if user.active_store_id and user.active_store.tenant_id == user.tenant_id:
            return user.tenant, user.active_store

        store = Store.objects.filter(tenant_id=user.tenant_id, is_active=True).order_by("id").first()
        if store:
            user.active_store = store
            user.save(update_fields=["active_store"])
            return user.tenant, store

        # si no hay stores, creamos uno
        store = Store.objects.create(tenant_id=user.tenant_id, name="Local 1", code="LOCAL-1")
        user.active_store = store
        user.save(update_fields=["active_store"])
        return user.tenant, store

    # crear tenant nuevo (1 tenant por usuario)
    base_name = (user.get_full_name() or user.username or "Mi Negocio").strip()
    slug = _unique_slug(user.username or base_name)
    tenant = Tenant.objects.create(name=base_name, slug=slug, is_active=True)

    # crear store + bodega
    store = Store.objects.create(tenant=tenant, name="Local 1", code="LOCAL-1", is_active=True)
    wh = Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Principal", is_active=True)

    tenant.default_warehouse = wh
    tenant.save(update_fields=["default_warehouse"])

    user.tenant = tenant
    user.active_store = store
    user.save(update_fields=["tenant", "active_store"])

    return tenant, store
