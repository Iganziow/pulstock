from rest_framework import generics, serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from core.permissions import HasTenant
from .models import Store


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ["id", "name", "code", "is_active"]


class StoreList(generics.ListAPIView):
    """
    GET /api/stores/
    Lista los locales del tenant del usuario.
    """
    permission_classes = [IsAuthenticated, HasTenant]
    serializer_class = StoreSerializer

    def get_queryset(self):
        t_id = self.request.user.tenant_id
        return Store.objects.filter(tenant_id=t_id).order_by("name")


class SetActiveStore(APIView):
    """
    POST /api/stores/set-active/
    body: {"store_id": 123}

    Setea el local activo del usuario (active_store).
    """
    permission_classes = [IsAuthenticated, HasTenant]

    def post(self, request):
        t_id = request.user.tenant_id
        store_id = request.data.get("store_id")

        if not store_id:
            return Response(
                {"detail": "store_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # (Opcional) cast seguro: si viene string "123"
        try:
            store_id = int(store_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "store_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        store = (
            Store.objects
            .filter(id=store_id, tenant_id=t_id, is_active=True)
            .first()
        )
        if not store:
            return Response(
                {"detail": "Store not found for this tenant"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Setear active_store del usuario
        request.user.active_store = store
        request.user.save(update_fields=["active_store"])

        return Response(
            {
                "ok": True,
                "active_store_id": store.id,
                "active_store_name": store.name,
            },
            status=status.HTTP_200_OK,
        )
