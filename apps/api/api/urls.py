from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection, DatabaseError, OperationalError
from django.conf import settings

from api.auth_views import CookieTokenObtainView, CookieTokenRefreshView, CookieLogoutView


def health_check(request):
    """Endpoint para load balancers y monitoreo. Verifica DB y Redis."""
    checks = {}

    try:
        connection.ensure_connection()
        checks["db"] = True
    except (DatabaseError, OperationalError):
        checks["db"] = False

    try:
        from django.core.cache import cache
        cache.set("_health", "1", timeout=5)
        checks["redis"] = cache.get("_health") == "1"
    except (ConnectionError, OSError, ValueError):
        checks["redis"] = False

    all_ok = all(checks.values())
    return JsonResponse(
        {"status": "ok" if all_ok else "error", **checks},
        status=200 if all_ok else 503,
    )


urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),

    path("api/health/", health_check, name="health_check"),

    path("api/auth/token/", CookieTokenObtainView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/logout/", CookieLogoutView.as_view(), name="token_logout"),
    path("api/reports/", include("reports.urls")),
    path("api/catalog/", include("catalog.urls")),
    path("api/core/", include("core.urls")),
    path("api/sales/", include("sales.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/stores/", include("stores.urls")),
    path("api/purchases/", include("purchases.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/forecast/", include("forecast.urls")),
    path("api/auth/", include("onboarding.urls")),
    path("api/billing/", include("billing.urls")),
    path("api/caja/", include("caja.urls")),
    path("api/tables/", include("tables.urls")),
    path("api/superadmin/", include("superadmin.urls")),
    path("api/promotions/", include("promotions.urls")),
]
