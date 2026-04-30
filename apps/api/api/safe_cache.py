"""
api/safe_cache.py
=================
SafeRedisCache: wrapper del backend Redis nativo de Django que captura
excepciones de conexión y se degrada graciosamente a "cache miss".

PROBLEMA QUE RESUELVE (Daniel 30/04/26):
Django 4+ tiene `django.core.cache.backends.redis.RedisCache` pero NO
tiene la opción `IGNORE_EXCEPTIONS` que sí tiene `django-redis`. Si
Redis cae, cualquier `cache.get()` o `cache.set()` tira excepción y
rompe el código cliente.

Esto es crítico porque DRF throttling usa `cache.get()` en CADA request
sin try/except. Si Redis cae → TODOS los endpoints con throttling
devuelven 500.

COMPORTAMIENTO:
- Si Redis está OK: idéntico al backend nativo.
- Si Redis cae: cache.get() devuelve `default`, cache.set() es no-op,
  cache.delete()/incr() son no-op. Todo logueado a WARNING.
- La app sigue funcionando, solo más lenta (sin cache → más DB queries).

Este wrapper hace lo que `django-redis` con `IGNORE_EXCEPTIONS=True`
pero sin sumar otra dependencia (django-redis pesa ~50KB y trae todo
un cliente Redis alternativo).
"""
import logging
from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)

# Excepciones que indican "Redis no disponible". Cualquiera de estas
# se degrada a cache miss / no-op silencioso. Otros errores (lógicos,
# de tipos, etc.) se propagan normalmente.
#
# `redis.exceptions.RedisError` es la clase base de TODOS los errores
# del cliente redis (ConnectionError, TimeoutError, ResponseError, etc.).
# Importante: redis.exceptions.ConnectionError NO hereda de la
# builtin Python ConnectionError, son clases distintas con el mismo
# nombre. Por eso necesitamos importar la de redis explícitamente.
try:
    from redis.exceptions import RedisError
    _REDIS_DOWN_EXCEPTIONS = (
        RedisError,           # cubre toda la familia de redis-py
        ConnectionError,      # builtin Python (extra defensa)
        OSError,              # socket errors
        TimeoutError,         # builtin
    )
except ImportError:
    # Sin redis-py instalado → improbable en prod, pero defensivo
    _REDIS_DOWN_EXCEPTIONS = (ConnectionError, OSError, TimeoutError)


def _safe(default_return):
    """Decorator: envuelve método de cache para devolver `default_return`
    si Redis cae."""
    def decorator(method):
        def wrapped(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except _REDIS_DOWN_EXCEPTIONS as exc:
                logger.warning(
                    "Cache %s failed (Redis down?): %s. Degraded to no-op.",
                    method.__name__, exc,
                )
                return default_return
        return wrapped
    return decorator


class SafeRedisCache(RedisCache):
    """RedisCache que degrada a cache-miss/no-op si Redis cae."""

    @_safe(default_return=None)
    def get(self, key, default=None, version=None):
        # `default` se respeta a través del decorator: si excepción,
        # devolvemos None — pero el comportamiento estándar Django es
        # devolver `default`. Lo respetamos manualmente.
        try:
            return super().get(key, default, version)
        except _REDIS_DOWN_EXCEPTIONS as exc:
            logger.warning("Cache get failed (Redis down?): %s", exc)
            return default

    @_safe(default_return=False)
    def set(self, key, value, timeout=300, version=None):
        return super().set(key, value, timeout, version)

    @_safe(default_return=False)
    def add(self, key, value, timeout=300, version=None):
        return super().add(key, value, timeout, version)

    @_safe(default_return=False)
    def delete(self, key, version=None):
        return super().delete(key, version)

    @_safe(default_return={})
    def get_many(self, keys, version=None):
        return super().get_many(keys, version)

    @_safe(default_return=False)
    def set_many(self, data, timeout=300, version=None):
        return super().set_many(data, timeout, version)

    @_safe(default_return=False)
    def has_key(self, key, version=None):
        return super().has_key(key, version)

    @_safe(default_return=None)
    def incr(self, key, delta=1, version=None):
        return super().incr(key, delta, version)

    @_safe(default_return=False)
    def clear(self):
        return super().clear()
