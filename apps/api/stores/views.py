from django.utils.decorators import method_decorator

from rest_framework import generics, serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from api.http_cache import browser_cache
from core.permissions import HasTenant
from .models import Store


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ["id", "name", "code", "is_active"]


@method_decorator(browser_cache(max_age=120), name="get")
class StoreList(generics.ListAPIView):
    """
    GET /api/stores/
    Lista los locales del tenant del usuario.
    Owners ven todos. Otros roles solo ven los asignados.

    Browser cache 2min: stores cambian muy poco. Si el dueño crea uno
    nuevo, lo ve cuando refresque o al cabo del TTL.
    """
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = StoreSerializer

    def get_queryset(self):
        user = self.request.user
        t_id = user.tenant_id
        qs = Store.objects.filter(tenant_id=t_id, is_active=True).order_by("name")

        # Owners see all stores
        if getattr(user, "is_owner", False):
            return qs

        # Other roles: filter by UserStoreAccess
        from core.models import UserStoreAccess
        allowed_ids = UserStoreAccess.objects.filter(
            user=user
        ).values_list("store_id", flat=True)
        return qs.filter(id__in=allowed_ids)


class SetActiveStore(APIView):
    """
    POST /api/stores/set-active/
    body: {"store_id": 123}

    Setea el local activo del usuario (active_store).
    Validates user has access to the store.
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        user = request.user
        t_id = user.tenant_id
        store_id = request.data.get("store_id")

        if not store_id:
            return Response(
                {"detail": "store_id es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            store_id = int(store_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "store_id debe ser un número."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        store = (
            Store.objects
            .filter(id=store_id, tenant_id=t_id, is_active=True)
            .first()
        )
        if not store:
            return Response(
                {"detail": "Local no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check access (owners bypass)
        if not getattr(user, "is_owner", False):
            from core.models import UserStoreAccess
            if not UserStoreAccess.objects.filter(user=user, store=store).exists():
                return Response(
                    {"detail": "No tienes acceso a este local."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        user.active_store = store
        user.save(update_fields=["active_store"])

        return Response(
            {
                "ok": True,
                "active_store_id": store.id,
                "active_store_name": store.name,
            },
            status=status.HTTP_200_OK,
        )
