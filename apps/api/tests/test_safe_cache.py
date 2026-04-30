"""
Tests del wrapper SafeRedisCache (Daniel 30/04/26).

Si Redis cae, el wrapper degrada a cache miss / no-op silencioso.
La app sigue funcionando, solo más lenta.
"""
import pytest
from unittest.mock import patch
from api.safe_cache import SafeRedisCache


pytestmark = pytest.mark.django_db


class TestSafeRedisCacheDegradation:
    """SafeRedisCache se degrada graciosamente si Redis cae."""

    def setup_method(self):
        # Apuntamos a un Redis inválido para forzar errores reales
        self.cache = SafeRedisCache(
            "redis://nonexistent-host-99999:6379/0",
            params={"KEY_PREFIX": "test"},
        )

    def test_get_returns_default_when_redis_down(self):
        """cache.get() devuelve `default` si Redis no responde."""
        result = self.cache.get("any-key", default="fallback")
        assert result == "fallback"

    def test_get_returns_none_by_default(self):
        result = self.cache.get("any-key")
        assert result is None

    def test_set_returns_false_when_redis_down(self):
        """cache.set() devuelve False (no crashea)."""
        result = self.cache.set("any-key", "value", timeout=60)
        assert result is False

    def test_delete_returns_false_when_redis_down(self):
        result = self.cache.delete("any-key")
        assert result is False

    def test_get_many_returns_empty_dict_when_redis_down(self):
        result = self.cache.get_many(["k1", "k2", "k3"])
        assert result == {}

    def test_has_key_returns_false_when_redis_down(self):
        result = self.cache.has_key("any-key")
        assert result is False


class TestSafeRedisCacheTransparent:
    """Cuando Redis está OK, SafeRedisCache se comporta idéntico al
    backend nativo. Verificamos via la cache `default` del proyecto
    (que ya está configurada con SafeRedisCache si REDIS_URL está set,
    o LocMemCache en dev)."""

    def test_normal_get_set_works(self):
        from django.core.cache import cache
        cache.set("test-safe", "ok", timeout=10)
        assert cache.get("test-safe") == "ok"
        cache.delete("test-safe")
        assert cache.get("test-safe") is None
