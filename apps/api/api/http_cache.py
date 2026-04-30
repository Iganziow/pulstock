"""
api/http_cache.py
=================
Decoradores y mixins para HTTP browser cache (Cache-Control + Vary).

Usado en endpoints read-only que cambian poco (catálogo, stores, warehouses,
configuración de cajas). El cache es PRIVATE: solo el browser del usuario
mismo lo guarda — nunca compartido entre usuarios o tenants. Esto previene
data leak multi-tenant.

NO usar en:
- Endpoints con datos vivos (dashboard summary, caja current, mesas).
- Endpoints con write side-effects (POST, PATCH, DELETE).
- Endpoints que devuelven datos sensibles (auth, billing).

Uso:
    from api.http_cache import browser_cache

    class MyView(APIView):
        @browser_cache(max_age=60)
        def get(self, request):
            ...

O en CBV:
    @method_decorator(browser_cache(max_age=60), name="get")
    class MyView(ListAPIView):
        ...
"""
from functools import wraps
from django.utils.cache import patch_cache_control, patch_vary_headers


def browser_cache(max_age: int = 60):
    """
    Decorator que agrega `Cache-Control: private, max-age=N` y `Vary: Authorization, X-Store-Id`.

    `private`: solo el browser del usuario cachea, NUNCA caches compartidos
    (proxies, CDN). Crítico para multi-tenant — distintos tenants/users
    NUNCA comparten respuesta.

    `Vary: Authorization, X-Store-Id`: el browser usa cache distinto para
    cada combinación de usuario × store. Si el user cambia de store activo,
    no ve datos del store anterior.

    Args:
        max_age: segundos que el browser puede usar la cached response sin
                 revalidar. Recomendado 30-300s según volatilidad del data.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(*args, **kwargs):
            response = view_func(*args, **kwargs)
            # Solo aplicar a respuestas exitosas (no a 4xx/5xx)
            if 200 <= response.status_code < 300:
                patch_cache_control(response, private=True, max_age=max_age)
                patch_vary_headers(response, ["Authorization", "X-Store-Id"])
            return response
        return _wrapped
    return decorator
