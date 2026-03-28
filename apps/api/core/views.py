from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from stores.services import ensure_user_tenant_and_store
from .permissions import HasTenant


# Permission map per role — frontend uses this to show/hide features
ROLE_PERMISSIONS = {
    "owner": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": True,
        "settings": True, "users": True, "caja": True,
    },
    "manager": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": True,
        "settings": False, "users": False, "caja": True,
    },
    "cashier": {
        "pos": True, "sales": True, "catalog": True, "catalog_write": False,
        "inventory": False, "inventory_write": False, "purchases": False,
        "purchases_write": False, "reports": False, "forecast": False,
        "settings": False, "users": False, "caja": True,
    },
    "inventory": {
        "pos": False, "sales": False, "catalog": True, "catalog_write": True,
        "inventory": True, "inventory_write": True, "purchases": True,
        "purchases_write": True, "reports": True, "forecast": False,
        "settings": False, "users": False, "caja": False,
    },
}


class MeView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        tenant, store = ensure_user_tenant_and_store(request.user)

        u = request.user
        role = getattr(u, "role", "owner").lower()
        data = {
            "id": u.id,
            "username": u.username,
            "email": getattr(u, "email", ""),
            "first_name": getattr(u, "first_name", ""),
            "last_name": getattr(u, "last_name", ""),
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "active_store_id": store.id,
            "default_warehouse_id": getattr(tenant, "default_warehouse_id", None),
            "role": role,
            "role_label": dict(u.Role.choices).get(role, role),
            "permissions": ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["cashier"]),
        }
        return Response(data)