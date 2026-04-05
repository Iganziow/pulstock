# core/permissions.py
import logging

from rest_framework.permissions import BasePermission

from core.models import Tenant, Warehouse

logger = logging.getLogger(__name__)


class IsSuperAdmin(BasePermission):
    """Solo superusuarios de la plataforma."""
    message = "Solo superadministradores pueden realizar esta acción."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class HasTenant(BasePermission):
    """
    Permiso que garantiza que el usuario tenga tenant asignado.
    NO crea tenant automáticamente — los tenants se crean via onboarding.
    """

    message = "Tu negocio ha sido suspendido o tu cuenta no tiene un negocio asignado."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "tenant_id", None) is None:
            logger.warning(
                "User %s (id=%s) intentó acceder sin tenant asignado.",
                getattr(user, "username", "?"), getattr(user, "pk", "?"),
            )
            return False

        # Block access if tenant is deactivated
        tenant = getattr(user, "tenant", None)
        if tenant and not tenant.is_active:
            logger.warning(
                "User %s (id=%s) blocked — tenant %s is deactivated.",
                user.username, user.pk, tenant.name,
            )
            return False

        return True


# ══════════════════════════════════════════════════════════════════════════════
# ROLE-BASED PERMISSIONS
# ══════════════════════════════════════════════════════════════════════════════

class IsOwner(BasePermission):
    """Solo el dueño del negocio."""
    message = "Solo el dueño puede realizar esta acción."

    def has_permission(self, request, view):
        return getattr(request.user, "is_owner", False)


class IsManager(BasePermission):
    """Dueño o administrador/bodeguero."""
    message = "Necesitas ser administrador o dueño."

    def has_permission(self, request, view):
        return getattr(request.user, "is_manager", False)


class IsInventoryOrManager(BasePermission):
    """Dueño, administrador o encargado de inventario."""
    message = "Necesitas ser administrador o encargado de inventario."

    def has_permission(self, request, view):
        role = getattr(request.user, "role", "")
        return role in ("owner", "manager", "inventory")


class IsManagerOrReadOnly(BasePermission):
    """
    Manager+ puede escribir. Cajero solo puede leer (GET, HEAD, OPTIONS).
    """
    message = "Solo administradores pueden modificar esto."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return getattr(request.user, "is_manager", False)


class HasStoreAccess(BasePermission):
    """
    Validates the user has access to the currently active store.
    Owners bypass this check (they access all stores in their tenant).
    """
    message = "No tienes acceso a este local."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_owner", False):
            return True
        store_id = getattr(user, "active_store_id", None)
        if not store_id:
            return False
        from core.models import UserStoreAccess
        return UserStoreAccess.objects.filter(
            user=user, store_id=store_id
        ).exists()