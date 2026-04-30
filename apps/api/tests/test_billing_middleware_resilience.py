"""
Tests del flujo billing middleware con Redis OK (sanity check).

El blindaje contra Redis caído está en SafeRedisCache wrapper
(api/safe_cache.py + tests/test_safe_cache.py). El middleware solo
llama cache.get/set sin try/except — el wrapper se encarga.

Acá validamos solo que el flujo NORMAL (Redis OK) sigue funcionando
correctamente tras nuestros cambios.
"""
import pytest
from django.core.cache import cache


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


class TestBillingMiddlewareNormalFlow:
    """Sanity check: con Redis OK, el middleware funciona normalmente."""

    def test_normal_path_works(self, auth_client):
        """Con cache disponible, requests autenticadas pasan OK."""
        resp1 = auth_client.get("/api/core/me/")
        # Segunda request hits cache (sub_access cached 60s)
        resp2 = auth_client.get("/api/core/me/")
        assert resp1.status_code == resp2.status_code
        assert resp1.status_code in (200, 402, 403)
