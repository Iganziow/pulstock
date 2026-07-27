from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from api.http_cache import browser_cache
from stores.services import ensure_user_tenant_and_store
from .permissions import HasTenant, IsOwner
from .role_permissions import (
    DEFAULT_ROLE_PERMISSIONS as ROLE_PERMISSIONS,  # compat retro
    PERMISSION_META, EDITABLE_ROLES, LOCKED_PERMISSIONS,
    effective_permissions, sanitize_overrides,
)


class MeView(APIView):
    permission_classes = [IsAuthenticated, HasTenant]

    @method_decorator(browser_cache(max_age=60))
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
            "permissions": effective_permissions(tenant, role),
        }
        return Response(data)


class RolePermissionsView(APIView):
    """GET/PUT /api/core/role-permissions/ — matriz de permisos editable (dueño).

    Estilo Fudo: el dueño ve una matriz permiso × rol y activa/desactiva lo
    que cada rol puede hacer. El owner tiene todo y no es editable; `settings`
    y `users` quedan bloqueados (solo dueño) para evitar escalación.
    """
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def _payload(self, tenant):
        from .models import User
        # Permisos efectivos por rol editable.
        roles = []
        for role in EDITABLE_ROLES:
            roles.append({
                "role": role,
                "role_label": dict(User.Role.choices).get(role, role),
                "permissions": effective_permissions(tenant, role),
            })
        # Usuarios por rol (para "cada rol tiene sus usuarios").
        users_by_role = {r: [] for r in EDITABLE_ROLES + ["owner"]}
        qs = User.objects.filter(tenant=tenant, is_active=True).order_by("first_name", "username")
        for us in qs:
            r = (us.role or "owner").lower()
            if r in users_by_role:
                name = " ".join(filter(None, [us.first_name, us.last_name])).strip() or us.username
                users_by_role[r].append({"id": us.id, "name": name, "email": us.email})
        return {
            "permission_meta": PERMISSION_META,
            "locked_permissions": sorted(LOCKED_PERMISSIONS),
            "editable_roles": EDITABLE_ROLES,
            "roles": roles,
            "users_by_role": users_by_role,
        }

    def get(self, request):
        tenant, _ = ensure_user_tenant_and_store(request.user)
        return Response(self._payload(tenant))

    def put(self, request):
        from .models import log_audit
        tenant, _ = ensure_user_tenant_and_store(request.user)
        overrides = sanitize_overrides(request.data.get("permissions") or request.data)
        tenant.role_permissions_overrides = overrides
        tenant.save(update_fields=["role_permissions_overrides"])
        log_audit(request, "role_permissions_update", "tenant", tenant.id, {
            "overrides": overrides,
        })
        return Response(self._payload(tenant))