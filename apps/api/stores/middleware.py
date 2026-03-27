from stores.models import Store

class StoreContextMiddleware:
    """
    Define request.store:
    - Si viene header X-Store-Id => usa ese (si pertenece al tenant)
    - Si no, usa user.active_store
    - Si no, usa el primer store del tenant
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)

        t_id = getattr(user, "tenant_id", None)
        if not t_id:
            return self.get_response(request)

        store_id = request.headers.get("X-Store-Id")
        if store_id:
            try:
                request.store = Store.objects.get(id=int(store_id), tenant_id=t_id, is_active=True)
                return self.get_response(request)
            except Exception:
                # si mandan uno malo, simplemente cae al fallback
                pass

        if getattr(user, "active_store_id", None):
            try:
                request.store = Store.objects.get(id=user.active_store_id, tenant_id=t_id, is_active=True)
                return self.get_response(request)
            except Exception:
                pass

        request.store = Store.objects.filter(tenant_id=t_id, is_active=True).order_by("id").first()
        return self.get_response(request)
