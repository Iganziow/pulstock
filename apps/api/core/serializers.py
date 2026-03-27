from rest_framework import serializers

class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    tenant_id = serializers.IntegerField()
    default_warehouse_id = serializers.IntegerField(allow_null=True)
