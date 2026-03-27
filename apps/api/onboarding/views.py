# onboarding/views.py
# ─────────────────────────────────────────────────────
# POST /api/auth/register/    — Crear cuenta (paso 1-3 del onboarding)
# GET  /api/auth/onboarding-status/  — Verificar si completó onboarding
# POST /api/auth/complete-onboarding/ — Marcar onboarding como completado
# ─────────────────────────────────────────────────────

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from api.auth_views import _set_token_cookies

from api.throttles import RegisterRateThrottle

from core.models import Tenant, User, Warehouse
from stores.models import Store


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Body: {
        "email": "juan@mi-negocio.cl",
        "password": "...",
        "full_name": "Juan Pérez",
        "business_name": "Ferretería El Tornillo",
        "business_type": "ferreteria",  // opcional
        "store_name": "Local Principal", // opcional, default "Mi Local"
        "warehouse_name": "Bodega Principal" // opcional
    }

    Creates in one transaction:
    - User (username = email, with hashed password)
    - Tenant (business)
    - Store (first location)
    - Warehouse (first warehouse in that store)
    - Links everything together

    Returns JWT tokens so user is logged in immediately.
    """
    permission_classes = [AllowAny]
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        data = request.data

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        full_name = (data.get("full_name") or "").strip()
        business_name = (data.get("business_name") or "").strip()
        business_type = (data.get("business_type") or "").strip()
        store_name = (data.get("store_name") or "").strip() or "Mi Local"
        warehouse_name = (data.get("warehouse_name") or "").strip() or "Bodega Principal"
        # Extra config from onboarding step 3
        extra_warehouses = data.get("extra_warehouses") or []   # list of warehouse names for first store
        extra_stores = data.get("extra_stores") or []           # list of {name, warehouses: []} for additional stores

        # Validations
        errors = {}
        if not email:
            errors["email"] = "El email es obligatorio."
        elif User.objects.filter(Q(email=email) | Q(username=email)).exists():
            errors["email"] = "No se pudo crear la cuenta. Verifica tus datos."

        if not password:
            errors["password"] = "La contraseña es obligatoria."
        else:
            try:
                validate_password(password)
            except DjangoValidationError as e:
                errors["password"] = " ".join(e.messages)

        if not full_name:
            errors["full_name"] = "Tu nombre es obligatorio."

        if not business_name:
            errors["business_name"] = "El nombre de tu negocio es obligatorio."

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        # Generate unique slug
        base_slug = slugify(business_name)[:60] or "negocio"
        slug = base_slug
        counter = 1
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Split full_name
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        try:
            with transaction.atomic():
                # 1. Create tenant (skip signal — we create stores explicitly below)
                tenant = Tenant(
                    name=business_name,
                    slug=slug,
                    is_active=True,
                )
                tenant._skip_default_store = True
                tenant.save()

                # 2. Create store
                store = Store.objects.create(
                    tenant=tenant,
                    name=store_name,
                    code=f"{slug}-1",
                    is_active=True,
                )

                # 3. Create warehouse
                warehouse = Warehouse.objects.create(
                    tenant=tenant,
                    store=store,
                    name=warehouse_name,
                    is_active=True,
                )

                # 4. Create extra warehouses in first store (e.g. 1 local, 2 bodegas)
                for wh_name in extra_warehouses:
                    wh_name_clean = (wh_name or "").strip()
                    if wh_name_clean:
                        Warehouse.objects.create(
                            tenant=tenant, store=store,
                            name=wh_name_clean, is_active=True,
                        )

                # 4b. Create extra stores with their warehouses (e.g. multi-local)
                for j, extra_store_data in enumerate(extra_stores):
                    es_name = (extra_store_data.get("name") or "").strip() or f"Local {j+2}"
                    extra_store = Store.objects.create(
                        tenant=tenant, name=es_name,
                        code=f"{slug}-{j+2}", is_active=True,
                    )
                    es_whs = extra_store_data.get("warehouses") or ["Bodega Principal"]
                    first_es_wh = None
                    for ew_name in es_whs:
                        ew = Warehouse.objects.create(
                            tenant=tenant, store=extra_store,
                            name=(ew_name or "").strip() or "Bodega Principal", is_active=True,
                        )
                        if first_es_wh is None:
                            first_es_wh = ew
                    if first_es_wh:
                        extra_store.default_warehouse = first_es_wh
                        extra_store.save()

                # 5. Link default warehouse
                tenant.default_warehouse = warehouse
                tenant.save()

                store.default_warehouse = warehouse
                store.save()

                # 5b. Seed standard units for the new tenant
                try:
                    from catalog.management.commands.seed_units import seed_units_for_tenant
                    seed_units_for_tenant(tenant)
                except Exception:
                    pass  # non-critical — units can be seeded later

                # 6. Create user
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    tenant=tenant,
                    active_store=store,
                )

                # 6. Set role if role model exists
                try:
                    user.role = "owner"
                    user.save(update_fields=["role"])
                except Exception:
                    pass  # role field might not exist yet

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            access_str = str(refresh.access_token)
            refresh_str = str(refresh)
            response = Response({
                "detail": "Cuenta creada exitosamente.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "full_name": full_name,
                },
                "tenant": {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                },
                "store": {
                    "id": store.id,
                    "name": store.name,
                },
                "tokens": {
                    "access": access_str,
                },
            }, status=status.HTTP_201_CREATED)
            _set_token_cookies(response, access_str, refresh_str)
            return response

        except Exception:
            import logging
            logging.getLogger("onboarding").exception("Error en registro de cuenta")
            return Response(
                {"detail": "No se pudo crear la cuenta. Por favor intenta de nuevo."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class OnboardingStatusView(APIView):
    """
    GET /api/auth/onboarding-status/
    Returns whether the user has completed onboarding steps.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tenant = user.tenant
        store = user.active_store

        has_tenant = tenant is not None
        has_store = store is not None
        has_warehouse = False
        has_products = False
        has_first_sale = False

        if has_tenant and has_store:
            has_warehouse = Warehouse.objects.filter(
                tenant=tenant, store=store, is_active=True
            ).exists()

            from catalog.models import Product
            has_products = Product.objects.filter(
                tenant=tenant, is_active=True
            ).exists()

            from sales.models import Sale
            has_first_sale = Sale.objects.filter(
                tenant=tenant, store=store, status="COMPLETED"
            ).exists()

        steps = {
            "account_created": True,
            "business_setup": has_tenant and has_store,
            "warehouse_ready": has_warehouse,
            "first_product": has_products,
            "first_sale": has_first_sale,
        }

        completed = all(steps.values())

        return Response({
            "completed": completed,
            "steps": steps,
            "progress": sum(1 for v in steps.values() if v),
            "total_steps": len(steps),
        })