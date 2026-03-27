from django.urls import path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from stores.services import ensure_user_tenant_and_store
from core.permissions import HasTenant, IsOwner
from core.models import Warehouse, User, AlertPreference
from core.views import MeView


class BootstrapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant, store = ensure_user_tenant_and_store(request.user)

        return Response({
            "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
            "active_store": {"id": store.id, "name": store.name, "code": store.code},
        })


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class WarehousesView(APIView):
    """
    GET  /api/core/warehouses/  — bodegas del active_store
    POST /api/core/warehouses/  — crear bodega en una tienda del tenant
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        tenant, store = ensure_user_tenant_and_store(request.user)

        qs = (
            Warehouse.objects
            .filter(tenant_id=tenant.id, store_id=store.id)
            .order_by("name")
        )

        return Response([
            {"id": w.id, "name": w.name, "is_active": w.is_active, "warehouse_type": w.warehouse_type}
            for w in qs
        ])

    def post(self, request):
        from stores.models import Store
        if not request.user.is_owner:
            return Response({"detail": "Solo el dueño puede crear bodegas."}, status=status.HTTP_403_FORBIDDEN)

        store_id = request.data.get("store")
        name = (request.data.get("name") or "").strip()
        t_id = request.user.tenant_id

        if not store_id or not name:
            return Response({"detail": "store y name son requeridos."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            store = Store.objects.get(id=store_id, tenant_id=t_id)
        except Store.DoesNotExist:
            return Response({"detail": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if Warehouse.objects.filter(tenant_id=t_id, store=store, name=name).exists():
            return Response({"detail": "Ya existe una bodega con ese nombre en esta tienda."}, status=status.HTTP_400_BAD_REQUEST)

        wh_type = (request.data.get("warehouse_type") or "storage").strip()
        if wh_type not in ("sales_floor", "storage"):
            wh_type = "storage"
        wh = Warehouse.objects.create(tenant_id=t_id, store=store, name=name, warehouse_type=wh_type)
        return Response({"id": wh.id, "name": wh.name, "warehouse_type": wh.warehouse_type}, status=status.HTTP_201_CREATED)


class WarehouseDetailView(APIView):
    """
    PATCH /api/core/warehouses/<id>/  — editar nombre o toggle is_active
    """
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def patch(self, request, wh_id):
        t_id = request.user.tenant_id
        try:
            wh = Warehouse.objects.get(id=wh_id, tenant_id=t_id)
        except Warehouse.DoesNotExist:
            return Response({"detail": "Bodega no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        updated = []

        if "name" in data:
            new_name = (data["name"] or "").strip()
            if not new_name:
                return Response({"detail": "Nombre requerido."}, status=status.HTTP_400_BAD_REQUEST)
            if (new_name != wh.name and
                    Warehouse.objects.filter(tenant_id=t_id, store_id=wh.store_id, name=new_name).exists()):
                return Response({"detail": "Ya existe una bodega con ese nombre en esta tienda."}, status=status.HTTP_400_BAD_REQUEST)
            wh.name = new_name
            updated.append("name")

        if "is_active" in data:
            wh.is_active = bool(data["is_active"])
            updated.append("is_active")

        if "warehouse_type" in data:
            wt = (data["warehouse_type"] or "").strip()
            if wt in ("sales_floor", "storage"):
                wh.warehouse_type = wt
                updated.append("warehouse_type")

        if updated:
            wh.save(update_fields=updated)
        return Response({"ok": True, "updated": updated})


class TenantSettingsView(APIView):
    """
    GET  /api/core/settings/  — returns full tenant config
    PATCH /api/core/settings/ — updates tenant fields (owner only)
    """
    permission_classes = [IsAuthenticated, HasTenant]

    EDITABLE_FIELDS = {
        "name", "legal_name", "rut", "giro", "address", "city", "comuna",
        "phone", "email", "website", "logo_url", "primary_color",
        "receipt_header", "receipt_footer", "receipt_show_logo", "receipt_show_rut",
        "currency", "timezone", "tax_rate",
    }

    def get(self, request):
        from core.models import Tenant
        t = Tenant.objects.get(id=request.user.tenant_id)
        return Response({
            "id": t.id, "name": t.name, "slug": t.slug,
            "legal_name": t.legal_name, "rut": t.rut, "giro": t.giro,
            "address": t.address, "city": t.city, "comuna": t.comuna,
            "phone": t.phone, "email": t.email, "website": t.website,
            "logo_url": t.logo_url, "primary_color": t.primary_color,
            "receipt_header": t.receipt_header, "receipt_footer": t.receipt_footer,
            "receipt_show_logo": t.receipt_show_logo, "receipt_show_rut": t.receipt_show_rut,
            "currency": t.currency, "timezone": t.timezone,
            "tax_rate": float(t.tax_rate),
            "created_at": t.created_at.isoformat(),
        })

    def patch(self, request):
        if not request.user.is_owner:
            return Response({"detail": "Solo el dueño puede cambiar la configuración."}, status=status.HTTP_403_FORBIDDEN)
        from core.models import Tenant
        from decimal import Decimal, InvalidOperation
        t = Tenant.objects.get(id=request.user.tenant_id)
        data = request.data
        updated = []

        # Validate critical fields
        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                return Response({"detail": "El nombre del negocio es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)
            data = {**data, "name": name}

        if "tax_rate" in data:
            try:
                tax = Decimal(str(data["tax_rate"]))
                if tax < 0 or tax > 100:
                    return Response({"detail": "El IVA debe estar entre 0% y 100%."}, status=status.HTTP_400_BAD_REQUEST)
            except (InvalidOperation, ValueError, TypeError):
                return Response({"detail": "IVA inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if "primary_color" in data:
            color = (data["primary_color"] or "").strip()
            if color and not (color.startswith("#") and len(color) in (4, 7)):
                return Response({"detail": "Color debe ser formato hex (#FFF o #FFFFFF)."}, status=status.HTTP_400_BAD_REQUEST)

        if "timezone" in data:
            import zoneinfo
            tz = (data["timezone"] or "").strip()
            if tz:
                try:
                    zoneinfo.ZoneInfo(tz)
                except (KeyError, Exception):
                    return Response({"detail": f"Zona horaria inválida: {tz}"}, status=status.HTTP_400_BAD_REQUEST)

        for field in self.EDITABLE_FIELDS:
            if field in data:
                setattr(t, field, data[field])
                updated.append(field)
        if updated:
            t.save(update_fields=updated)
        return Response({"ok": True, "updated": updated})


class StoreListView(APIView):
    """
    GET  /api/core/stores/  — list tenant stores
    POST /api/core/stores/  — create new store (owner only)
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), HasTenant(), IsOwner()]
        return [IsAuthenticated(), HasTenant()]

    def get(self, request):
        from stores.models import Store
        t_id = request.user.tenant_id
        stores = Store.objects.filter(tenant_id=t_id).order_by("name")

        # Batch-load warehouses to avoid N+1
        all_warehouses = Warehouse.objects.filter(tenant_id=t_id).order_by("name")
        wh_by_store: dict = {}
        for w in all_warehouses:
            wh_by_store.setdefault(w.store_id, []).append(w)

        return Response([
            {
                "id": s.id, "name": s.name, "code": s.code,
                "is_active": s.is_active,
                "default_warehouse_id": s.default_warehouse_id,
                "warehouses": [
                    {"id": w.id, "name": w.name, "is_active": w.is_active, "warehouse_type": w.warehouse_type}
                    for w in wh_by_store.get(s.id, [])
                ],
            }
            for s in stores
        ])

    def post(self, request):
        from stores.models import Store
        t_id = request.user.tenant_id

        # ── Plan limit check ──
        try:
            from billing.models import Subscription
            from billing.services import check_plan_limit
            sub = Subscription.objects.select_related("plan").get(tenant_id=t_id)
            current = Store.objects.filter(tenant_id=t_id).count()
            result = check_plan_limit(sub, "stores", current)
            if not result["allowed"]:
                return Response(
                    {"detail": f"Tu plan permite máximo {result['limit']} tienda(s). Mejora tu plan para crear más."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except Subscription.DoesNotExist:
            pass  # Tenant sin suscripción → sin límite (plan free)

        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "Nombre requerido"}, status=status.HTTP_400_BAD_REQUEST)
        code = (request.data.get("code") or "").strip()
        wh_name = (request.data.get("warehouse_name") or "").strip() or "Bodega Principal"

        if Store.objects.filter(tenant_id=t_id, name=name).exists():
            return Response({"detail": "Ya existe una tienda con ese nombre"}, status=status.HTTP_400_BAD_REQUEST)

        store = Store.objects.create(tenant_id=t_id, name=name, code=code)
        wh = Warehouse.objects.create(
            tenant_id=t_id, store=store, name=wh_name
        )
        store.default_warehouse = wh
        store.save(update_fields=["default_warehouse"])

        return Response({"id": store.id, "name": store.name}, status=status.HTTP_201_CREATED)


class StoreDetailView(APIView):
    """
    PATCH /api/core/stores/<id>/  — editar nombre, código o toggle is_active
    """
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def patch(self, request, store_id):
        from stores.models import Store
        t_id = request.user.tenant_id
        try:
            store = Store.objects.get(id=store_id, tenant_id=t_id)
        except Store.DoesNotExist:
            return Response({"detail": "Tienda no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        updated = []

        if "name" in data:
            new_name = (data["name"] or "").strip()
            if not new_name:
                return Response({"detail": "Nombre requerido."}, status=status.HTTP_400_BAD_REQUEST)
            if (new_name != store.name and
                    Store.objects.filter(tenant_id=t_id, name=new_name).exists()):
                return Response({"detail": "Ya existe una tienda con ese nombre."}, status=status.HTTP_400_BAD_REQUEST)
            store.name = new_name
            updated.append("name")

        if "code" in data:
            store.code = (data["code"] or "").strip()
            updated.append("code")

        if "is_active" in data:
            store.is_active = bool(data["is_active"])
            updated.append("is_active")

        if updated:
            store.save(update_fields=updated)
        return Response({"ok": True, "updated": updated})


class TenantUsersView(APIView):
    """
    GET  /api/core/users/         — list all users of this tenant (owner only)
    POST /api/core/users/         — create a new user (owner only)
    """
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def get_throttles(self):
        if self.request.method == "POST":
            from api.throttles import SensitiveActionThrottle
            return [SensitiveActionThrottle()]
        return []

    def get(self, request):
        users = User.objects.filter(
            tenant_id=request.user.tenant_id
        ).order_by("role", "first_name", "username")

        return Response([
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "role": u.role,
                "role_label": dict(User.Role.choices).get(u.role, u.role),
                "is_active": u.is_active,
                "active_store_id": u.active_store_id,
                "date_joined": u.date_joined.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ])

    def post(self, request):
        t_id = request.user.tenant_id

        # ── Plan limit check ──
        try:
            from billing.models import Subscription
            from billing.services import check_plan_limit
            sub = Subscription.objects.select_related("plan").get(tenant_id=t_id)
            current = User.objects.filter(tenant_id=t_id, is_active=True).count()
            result = check_plan_limit(sub, "users", current)
            if not result["allowed"]:
                return Response(
                    {"detail": f"Tu plan permite máximo {result['limit']} usuario(s). Mejora tu plan para crear más."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        except Subscription.DoesNotExist:
            pass  # Tenant sin suscripción → sin límite (plan free)

        data = request.data
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()
        role = (data.get("role") or "cashier").strip()

        if not username:
            return Response({"detail": "Username es requerido."}, status=status.HTTP_400_BAD_REQUEST)
        if not password or len(password) < 8:
            return Response({"detail": "Password debe tener al menos 8 caracteres."}, status=status.HTTP_400_BAD_REQUEST)
        if role not in dict(User.Role.choices):
            return Response({"detail": f"Rol inválido. Opciones: {', '.join(dict(User.Role.choices).keys())}"}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Ese nombre de usuario ya existe."}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            username=username,
            password=password,
            email=(data.get("email") or "").strip(),
            first_name=(data.get("first_name") or "").strip(),
            last_name=(data.get("last_name") or "").strip(),
            tenant_id=request.user.tenant_id,
            active_store_id=request.user.active_store_id,
            role=role,
        )

        return Response({
            "id": user.id, "username": user.username, "role": user.role,
        }, status=status.HTTP_201_CREATED)


class TenantUserDetailView(APIView):
    """
    PATCH  /api/core/users/<id>/  — update user role, active status, etc. (owner only)
    DELETE /api/core/users/<id>/  — deactivate user (owner only, can't delete self)
    """
    permission_classes = [IsAuthenticated, HasTenant, IsOwner]

    def get_throttles(self):
        from api.throttles import SensitiveActionThrottle
        return [SensitiveActionThrottle()]

    def _get_user(self, request, user_id):
        try:
            return User.objects.get(id=user_id, tenant_id=request.user.tenant_id)
        except User.DoesNotExist:
            return None

    def patch(self, request, user_id):
        target = self._get_user(request, user_id)
        if not target:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        updated = []

        # Role change
        if "role" in data:
            new_role = data["role"]
            if new_role not in dict(User.Role.choices):
                return Response({"detail": "Rol inválido."}, status=status.HTTP_400_BAD_REQUEST)
            # Can't remove own owner role
            if target.id == request.user.id and new_role != "owner":
                return Response({"detail": "No puedes quitarte el rol de dueño a ti mismo."}, status=status.HTTP_400_BAD_REQUEST)
            # Prevent removing last owner
            if target.role == "owner" and new_role != "owner":
                owner_count = User.objects.filter(
                    tenant_id=request.user.tenant_id, role="owner", is_active=True
                ).count()
                if owner_count <= 1:
                    return Response(
                        {"detail": "No se puede quitar el último dueño. Asigna otro dueño primero."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            target.role = new_role
            updated.append("role")

        # Active toggle
        if "is_active" in data:
            if target.id == request.user.id:
                return Response({"detail": "No puedes desactivarte a ti mismo."}, status=status.HTTP_400_BAD_REQUEST)
            target.is_active = bool(data["is_active"])
            updated.append("is_active")

        # Name/email
        for field in ("first_name", "last_name", "email"):
            if field in data:
                setattr(target, field, (data[field] or "").strip())
                updated.append(field)

        # Password reset — requires owner's current password for verification
        if "password" in data and data["password"]:
            pw = data["password"].strip()
            if len(pw) < 8:
                return Response({"detail": "Password debe tener al menos 8 caracteres."}, status=status.HTTP_400_BAD_REQUEST)
            # If changing another user's password, require owner's current password
            if target.id != request.user.id:
                current_pw = (data.get("current_password") or "").strip()
                if not current_pw:
                    return Response(
                        {"detail": "Debes confirmar tu contraseña actual para cambiar la de otro usuario."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not request.user.check_password(current_pw):
                    return Response(
                        {"detail": "Contraseña actual incorrecta."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            target.set_password(pw)
            updated.append("password")

        # Store assignment — validate belongs to tenant and is active
        if "active_store_id" in data:
            from stores.models import Store
            store_id = data["active_store_id"]
            if store_id:
                if not Store.objects.filter(
                    id=store_id, tenant_id=request.user.tenant_id, is_active=True
                ).exists():
                    return Response(
                        {"detail": "Tienda no encontrada o inactiva."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            target.active_store_id = store_id
            updated.append("active_store_id")

        if updated:
            save_fields = [f for f in updated if f != "password"]
            if save_fields:
                target.save(update_fields=save_fields)
            elif "password" in updated:
                target.save()

        return Response({"ok": True, "updated": updated})

    def delete(self, request, user_id):
        target = self._get_user(request, user_id)
        if not target:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return Response({"detail": "No puedes eliminar tu propia cuenta."}, status=status.HTTP_400_BAD_REQUEST)

        # Soft delete — deactivate instead of hard delete
        target.is_active = False
        target.save(update_fields=["is_active"])
        return Response({"ok": True, "deactivated": target.username})


class AlertPreferenceView(APIView):
    """
    GET  /api/core/alerts/  — preferencias de notificación del usuario
    PATCH /api/core/alerts/ — actualizar preferencias
    """
    permission_classes = [IsAuthenticated, HasTenant]

    FIELDS = ("stock_bajo", "forecast_urgente", "sugerencia_compra",
              "merma_alta", "sin_rotacion", "resumen_diario")

    def _get_or_create(self, user):
        prefs, _ = AlertPreference.objects.get_or_create(user=user)
        return prefs

    def get(self, request):
        prefs = self._get_or_create(request.user)
        return Response({f: getattr(prefs, f) for f in self.FIELDS})

    def patch(self, request):
        prefs = self._get_or_create(request.user)
        data = request.data
        updated = []
        for f in self.FIELDS:
            if f in data:
                setattr(prefs, f, bool(data[f]))
                updated.append(f)
        if updated:
            prefs.save(update_fields=updated)
        return Response({f: getattr(prefs, f) for f in self.FIELDS})


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("me/", MeView.as_view()),
    path("warehouses/", WarehousesView.as_view()),
    path("warehouses/<int:wh_id>/", WarehouseDetailView.as_view()),
    path("bootstrap/", BootstrapView.as_view(), name="bootstrap"),
    path("settings/", TenantSettingsView.as_view()),
    path("stores/", StoreListView.as_view()),
    path("stores/<int:store_id>/", StoreDetailView.as_view()),
    path("users/", TenantUsersView.as_view()),
    path("users/<int:user_id>/", TenantUserDetailView.as_view()),
    path("alerts/", AlertPreferenceView.as_view()),
]
