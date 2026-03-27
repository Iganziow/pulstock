# stores/context.py
from rest_framework.exceptions import ValidationError

from stores.models import Store
from core.models import Warehouse, Tenant


ACTIVE_STORE_400 = {
    "detail": (
        "active_store is required. "
        "Set it with POST /api/stores/set-active/ (body: {\"store_id\": <id>})."
    )
}


def get_active_store_or_400(user) -> Store:
    """
    Retorna el Store activo válido del usuario para su tenant.
    Si no hay, levanta ValidationError => DRF responde 400.
    """
    if not getattr(user, "tenant_id", None):
        raise ValidationError({"detail": "User has no tenant."})

    if not getattr(user, "active_store_id", None):
        raise ValidationError(ACTIVE_STORE_400)

    store = (
        Store.objects
        .filter(id=user.active_store_id, tenant_id=user.tenant_id, is_active=True)
        .first()
    )
    if not store:
        raise ValidationError({"detail": "active_store is invalid for this tenant or inactive."})

    return store


def resolve_warehouse_in_active_store_or_400(*, user, warehouse_id: int) -> Warehouse:
    """
    Valida que la bodega pertenezca al tenant y al active_store.
    - Caso normal: warehouse.store_id == active_store_id
    - Caso migración suave: warehouse.store_id NULL
        => solo se permite si es tenant.default_warehouse, y se "pega" al active_store.
    """
    store = get_active_store_or_400(user)

    wh = (
        Warehouse.objects
        .filter(id=warehouse_id, tenant_id=user.tenant_id)
        .select_related("store", "tenant")
        .first()
    )
    if not wh:
        raise ValidationError({"detail": "Invalid warehouse for this tenant."})

    # ✅ caso correcto
    if wh.store_id == store.id:
        return wh

    # 🧯 migración suave: si está NULL, intentamos corregir SOLO si es la default_warehouse del tenant
    if wh.store_id is None:
        tenant = Tenant.objects.filter(id=user.tenant_id).only("id", "default_warehouse_id").first()
        if tenant and tenant.default_warehouse_id == wh.id:
            Warehouse.objects.filter(id=wh.id, store__isnull=True).update(store=store)
            wh.store_id = store.id
            return wh

        raise ValidationError({
            "detail": (
                "Warehouse has no store assigned (migration pending). "
                "Please assign it to a store before using inventory."
            ),
            "warehouse_id": wh.id,
        })

    # ❌ bodega de otro store
    raise ValidationError({
        "detail": "Warehouse does not belong to active_store.",
        "warehouse_id": wh.id,
        "active_store_id": store.id,
        "warehouse_store_id": wh.store_id,
    })
