from django.urls import path
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from stores.services import ensure_user_tenant_and_store
from core.permissions import HasTenant, IsOwner, IsManager
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
    GET  /api/core/users/         — list users of this tenant
      - OWNER: all users
      - MANAGER: only users whose store_access overlaps with manager's stores
    POST /api/core/users/         — create a new user
      - OWNER: can create any role, assign to any store
      - MANAGER: can create cashier/inventory only, ONLY in their assigned stores
    """
    permission_classes = [IsAuthenticated, HasTenant, IsManager]

    def get_throttles(self):
        if self.request.method == "POST":
            from api.throttles import SensitiveActionThrottle
            return [SensitiveActionThrottle()]
        return []

    def get(self, request):
        from core.models import UserStoreAccess

        base_qs = User.objects.filter(tenant_id=request.user.tenant_id)
        # Managers only see: themselves + users whose store_access overlaps
        if request.user.role == User.Role.MANAGER:
            my_stores = UserStoreAccess.objects.filter(
                tenant_id=request.user.tenant_id, user=request.user,
            ).values_list("store_id", flat=True)
            visible_user_ids = set(
                UserStoreAccess.objects.filter(
                    tenant_id=request.user.tenant_id, store_id__in=list(my_stores),
                ).values_list("user_id", flat=True)
            )
            visible_user_ids.add(request.user.id)  # manager always sees self
            base_qs = base_qs.filter(id__in=visible_user_ids)

        users = base_qs.order_by("role", "first_name", "username")

        # Pre-fetch store access for all users
        access_map: dict[int, list[dict]] = {}
        for sa in UserStoreAccess.objects.filter(
            tenant_id=request.user.tenant_id
        ).select_related("store"):
            access_map.setdefault(sa.user_id, []).append({
                "store_id": sa.store_id,
                "store_name": sa.store.name,
            })

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
                "store_access": access_map.get(u.id, []),
                "date_joined": u.date_joined.isoformat(),
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ])

    def post(self, request):
        t_id = request.user.tenant_id
        is_manager_only = (request.user.role == User.Role.MANAGER)

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

        # Manager restrictions: cannot create owner or manager, only cashier/inventory
        if is_manager_only and role in (User.Role.OWNER, User.Role.MANAGER):
            return Response(
                {"detail": "Solo el dueño puede crear usuarios con rol owner o manager."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if User.objects.filter(username=username).exists():
            return Response({"detail": "Ese nombre de usuario ya existe."}, status=status.HTTP_400_BAD_REQUEST)

        # Determine store(s) to assign
        store_ids = data.get("store_ids") or []
        if not store_ids and request.user.active_store_id:
            store_ids = [request.user.active_store_id]

        # Manager restrictions: can only assign to stores they have access to
        if is_manager_only:
            from core.models import UserStoreAccess
            allowed_store_ids = set(
                UserStoreAccess.objects.filter(
                    tenant_id=t_id, user=request.user,
                ).values_list("store_id", flat=True)
            )
            invalid_stores = [sid for sid in store_ids if int(sid) not in allowed_store_ids]
            if invalid_stores:
                return Response(
                    {"detail": "No puedes asignar un usuario a un local al que no tienes acceso."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        user = User.objects.create_user(
            username=username,
            password=password,
            email=(data.get("email") or "").strip(),
            first_name=(data.get("first_name") or "").strip(),
            last_name=(data.get("last_name") or "").strip(),
            tenant_id=t_id,
            active_store_id=store_ids[0] if store_ids else request.user.active_store_id,
            role=role,
        )

        # Create store access for non-owner users
        from core.models import UserStoreAccess
        if role == "owner":
            # Owners get access to ALL stores
            from stores.models import Store
            for store in Store.objects.filter(tenant_id=t_id, is_active=True):
                UserStoreAccess.objects.get_or_create(
                    user=user, store=store, defaults={"tenant_id": t_id})
        else:
            for sid in store_ids:
                UserStoreAccess.objects.get_or_create(
                    user=user, store_id=sid, defaults={"tenant_id": t_id})

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

        # Store access list — replace all access entries
        if "store_ids" in data:
            from core.models import UserStoreAccess
            from stores.models import Store
            new_ids = data["store_ids"] or []
            t_id = request.user.tenant_id
            # Validate all stores belong to tenant
            valid = set(Store.objects.filter(
                id__in=new_ids, tenant_id=t_id, is_active=True
            ).values_list("id", flat=True))
            # Replace access
            UserStoreAccess.objects.filter(user=target, tenant_id=t_id).delete()
            for sid in valid:
                UserStoreAccess.objects.create(user=target, store_id=sid, tenant_id=t_id)
            # Set active_store to first if current isn't in the new list
            if target.active_store_id not in valid and valid:
                target.active_store_id = next(iter(valid))
                if "active_store_id" not in updated:
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

        username = target.username
        target.delete()
        return Response({"ok": True, "deleted": username})


class AlertPreferenceView(APIView):
    """
    GET  /api/core/alerts/  — preferencias de notificación del usuario
    PATCH /api/core/alerts/ — actualizar preferencias
    """
    permission_classes = [IsAuthenticated, HasTenant]

    FIELDS = ("stock_bajo", "forecast_urgente", "sugerencia_compra",
              "merma_alta", "sin_rotacion", "resumen_diario")

    def _get_or_create(self, user):
        prefs, _ = AlertPreference.objects.get_or_create(
            user=user,
            defaults={"tenant_id": user.tenant_id},
        )
        # Backfill tenant_id on legacy rows (created before this fix)
        if not prefs.tenant_id and user.tenant_id:
            prefs.tenant_id = user.tenant_id
            prefs.save(update_fields=["tenant_id"])
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


class NotificationsView(APIView):
    """GET /core/notifications/ — alertas activas basadas en preferencias del usuario."""
    permission_classes = [IsAuthenticated, HasTenant]

    def get(self, request):
        user = request.user
        tid = user.tenant_id
        sid = getattr(user, "active_store_id", None)

        # Load user preferences (ensure tenant_id is set)
        prefs, _ = AlertPreference.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tid},
        )
        if not prefs.tenant_id and tid:
            prefs.tenant_id = tid
            prefs.save(update_fields=["tenant_id"])

        notifications = []

        # ── Stock bajo ──
        if prefs.stock_bajo:
            from inventory.models import StockItem
            from catalog.models import Product
            low_items = (
                StockItem.objects
                .filter(tenant_id=tid, product__is_active=True, product__min_stock__gt=0)
                .filter(on_hand__lt=models.F("product__min_stock"))
                .select_related("product")[:10]
            )
            for si in low_items:
                notifications.append({
                    "type": "stock_bajo",
                    "icon": "📦",
                    "title": f"{si.product.name} — stock bajo",
                    "description": f"Quedan {si.on_hand} unidades (mínimo: {si.product.min_stock})",
                    "link": "/dashboard/inventory/stock",
                    "severity": "warning" if float(si.on_hand) > 0 else "critical",
                })

        # ── Forecast urgente (days_to_stockout <= 3) ──
        if prefs.forecast_urgente:
            try:
                from forecast.models import Forecast
                from django.utils import timezone
                urgent = (
                    Forecast.objects
                    .filter(tenant_id=tid, date=timezone.now().date())
                    .filter(days_to_stockout__isnull=False, days_to_stockout__lte=3)
                    .select_related("product")[:5]
                )
                for f in urgent:
                    notifications.append({
                        "type": "forecast_urgente",
                        "icon": "⚠️",
                        "title": f"{f.product.name} — se agota pronto",
                        "description": f"Estimado {f.days_to_stockout} día(s) para quedarse sin stock",
                        "link": "/dashboard/forecast",
                        "severity": "critical" if f.days_to_stockout <= 1 else "warning",
                    })
            except (ImportError, AttributeError, ValueError) as e:
                logger.warning("Notifications: forecast queries failed: %s", e)
            except Exception as e:
                logger.exception("Notifications: unexpected error in forecast: %s", e)

        # ── Sugerencias de compra pendientes ──
        if prefs.sugerencia_compra:
            try:
                from forecast.models import PurchaseSuggestion
                pending = PurchaseSuggestion.objects.filter(
                    tenant_id=tid, status="pending"
                ).count()
                if pending > 0:
                    notifications.append({
                        "type": "sugerencia_compra",
                        "icon": "🛒",
                        "title": f"{pending} sugerencia(s) de compra",
                        "description": "Hay sugerencias automáticas de reposición pendientes",
                        "link": "/dashboard/forecast/suggestions",
                        "severity": "info",
                    })
            except (ImportError, AttributeError, ValueError) as e:
                logger.warning("Notifications: purchase suggestions failed: %s", e)
            except Exception as e:
                logger.exception("Notifications: unexpected error in suggestions: %s", e)

        # ── Merma alta (último mes) ──
        if prefs.merma_alta:
            from inventory.models import StockMove
            from django.utils import timezone
            from datetime import timedelta
            month_ago = timezone.now() - timedelta(days=30)
            loss_count = StockMove.objects.filter(
                tenant_id=tid, move_type="OUT", ref_type="LOSS",
                created_at__gte=month_ago,
            ).count()
            if loss_count > 0:
                notifications.append({
                    "type": "merma_alta",
                    "icon": "📉",
                    "title": f"{loss_count} merma(s) registradas este mes",
                    "description": "Revisa las pérdidas en el reporte de mermas",
                    "link": "/dashboard/reports/losses",
                    "severity": "warning",
                })

        # Sort: critical first, then warning, then info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        notifications.sort(key=lambda n: severity_order.get(n["severity"], 9))

        return Response({
            "count": len(notifications),
            "notifications": notifications,
        })


class NetworkPrintProxyView(APIView):
    """
    POST /api/core/print/network/
    Body: { "host": "192.168.1.50", "port": 9100, "data_b64": "<base64 ESC/POS>" }

    Proxy para impresoras de red (ESC/POS sobre TCP raw — puerto 9100 estándar).
    Permite que el navegador (que no puede abrir sockets TCP) imprima a
    impresoras de red como Epson TM-T20III, Xprinter WiFi, Bixolon, etc.

    Solo redirige TCP en la red LOCAL del servidor — NO accede a internet público
    por seguridad (validación de rango IP privado).
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        import base64
        import ipaddress
        import socket

        host = (request.data.get("host") or "").strip()
        port = int(request.data.get("port") or 9100)
        data_b64 = request.data.get("data_b64") or ""

        if not host or not data_b64:
            return Response({"detail": "host y data_b64 son requeridos."}, status=400)

        # Security: only allow private/local addresses (anti-SSRF)
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(host))
            if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                return Response(
                    {"detail": "Solo se permiten impresoras en red privada/local."},
                    status=400,
                )
        except (ValueError, socket.gaierror) as e:
            return Response({"detail": f"Host inválido: {e}"}, status=400)

        if not (1 <= port <= 65535):
            return Response({"detail": "Puerto inválido (1-65535)."}, status=400)

        try:
            data = base64.b64decode(data_b64)
        except Exception as e:
            return Response({"detail": f"data_b64 inválido: {e}"}, status=400)

        if len(data) > 200_000:  # 200KB max per print (safety)
            return Response({"detail": "Payload demasiado grande."}, status=400)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.sendall(data)
            sock.close()
            return Response({"ok": True, "bytes_sent": len(data)})
        except (socket.timeout, ConnectionRefusedError) as e:
            return Response(
                {"detail": f"No se pudo conectar a {host}:{port}. {e}"},
                status=502,
            )
        except OSError as e:
            return Response(
                {"detail": f"Error de red: {e}"},
                status=502,
            )


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
    path("notifications/", NotificationsView.as_view()),
    path("print/network/", NetworkPrintProxyView.as_view()),
]
