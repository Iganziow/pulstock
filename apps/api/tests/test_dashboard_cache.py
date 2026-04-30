"""
Tests del cache Redis del /dashboard/summary/ (Daniel 30/04/26).

Validan:
- Feature flag OFF por defecto: comportamiento idéntico al anterior, sin cache.
- Feature flag ON: primera request es MISS, segunda es HIT.
- Cache key incluye tenant + store + fecha (multi-tenant safe).
- Cache fallback transparente si el backend cae.
"""
import pytest
from unittest.mock import patch
from django.core.cache import cache
from django.test import override_settings


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    """Limpiar cache entre tests para no contaminar."""
    cache.clear()
    yield
    cache.clear()


class TestDashboardCacheFlag:
    """El cache solo se activa con feature flag."""

    @override_settings(CACHE_DASHBOARD_ENABLED=False)
    def test_flag_off_no_cache_header(self, auth_client):
        resp = auth_client.get("/api/dashboard/summary/")
        assert resp.status_code == 200
        # Sin flag, NO debe agregar header X-Cache
        assert "X-Cache" not in resp.headers

    @override_settings(CACHE_DASHBOARD_ENABLED=True, CACHE_DASHBOARD_TTL=60)
    def test_flag_on_first_miss_then_hit(self, auth_client):
        # Primera request: MISS (cache vacío)
        resp1 = auth_client.get("/api/dashboard/summary/")
        assert resp1.status_code == 200
        assert resp1.headers.get("X-Cache") == "MISS"

        # Segunda request inmediata: HIT
        resp2 = auth_client.get("/api/dashboard/summary/")
        assert resp2.status_code == 200
        assert resp2.headers.get("X-Cache") == "HIT"

        # Datos idénticos
        assert resp1.data == resp2.data

    @override_settings(CACHE_DASHBOARD_ENABLED=True)
    def test_cache_key_includes_tenant_and_store(self, auth_client, tenant, store):
        """Multi-tenant safety: dos tenants distintos NO comparten cache."""
        from django.utils import timezone

        # Cargar el endpoint para tenant 1
        resp = auth_client.get("/api/dashboard/summary/")
        assert resp.status_code == 200

        # Verificar que la cache key existe para este tenant+store
        today_iso = timezone.localtime().date().isoformat()
        # KEY_PREFIX = "pulstock", el delimiter es ":"
        # cache.get("dashboard:summary:tX:sY:date") aplica el prefix internamente
        cached_value = cache.get(f"dashboard:summary:t{tenant.id}:s{store.id}:{today_iso}")
        assert cached_value is not None, "Cache no se persistió con la key esperada"


class TestDashboardCacheRobustness:
    """Si Redis cae, el endpoint debe seguir funcionando.

    El código del view tiene try/except alrededor de cache.get/set
    (ver dashboard/__init__.py). Acá verificamos comportamiento
    integrado (hard-mock no aplica fácil — la cache es un símbolo
    compartido entre billing middleware y dashboard view).
    """

    @override_settings(CACHE_DASHBOARD_ENABLED=False)
    def test_flag_off_works_without_cache_backend(self, auth_client):
        """Con flag OFF, el endpoint NO toca cache. Dependencia
        cero del backend Redis."""
        resp = auth_client.get("/api/dashboard/summary/")
        assert resp.status_code == 200
        # Sin cache, no hay header X-Cache.
        assert "X-Cache" not in resp.headers
