from rest_framework import serializers
from .models import Promotion, PromotionProduct


class PromotionProductSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_price = serializers.DecimalField(source="product.price", max_digits=12, decimal_places=2, read_only=True)
    promo_price = serializers.SerializerMethodField()

    class Meta:
        model = PromotionProduct
        fields = [
            "id", "product_id", "product_name", "product_sku",
            "product_price", "override_discount_value", "promo_price",
        ]

    def get_promo_price(self, obj):
        return str(obj.promotion.compute_promo_price(
            obj.product.price, obj.override_discount_value,
        ))


class PromotionListSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Promotion
        fields = [
            "id", "name", "discount_type", "discount_value",
            "start_date", "end_date", "is_active", "status",
            "product_count", "created_at",
        ]


class PromotionDetailSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    items = PromotionProductSerializer(many=True, read_only=True)
    product_ids = serializers.SerializerMethodField()

    def get_product_ids(self, obj):
        return list(obj.items.values_list("product_id", flat=True))

    class Meta:
        model = Promotion
        fields = [
            "id", "name", "discount_type", "discount_value",
            "start_date", "end_date", "is_active", "status",
            "items", "product_ids", "created_at",
        ]


class PromotionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    discount_type = serializers.ChoiceField(choices=Promotion.DISCOUNT_TYPE_CHOICES)
    discount_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    product_ids = serializers.ListField(child=serializers.IntegerField(), min_length=0, max_length=500, required=False, default=list)
    product_items = serializers.ListField(child=serializers.DictField(), required=False, max_length=500, default=list)

    def validate(self, data):
        if data["end_date"] <= data["start_date"]:
            raise serializers.ValidationError({"end_date": "La fecha de fin debe ser posterior a la de inicio."})
        if data["discount_type"] == "pct":
            if not (0 < data["discount_value"] <= 100):
                raise serializers.ValidationError({"discount_value": "El porcentaje debe estar entre 0 y 100."})
        elif data["discount_value"] <= 0:
            raise serializers.ValidationError({"discount_value": "El precio fijo debe ser mayor a 0."})
        # At least one product from either source
        has_items = bool(data.get("product_items"))
        has_ids = bool(data.get("product_ids"))
        if not has_items and not has_ids:
            raise serializers.ValidationError({"product_ids": "Debes seleccionar al menos un producto."})
        return data


class ActivePromoSerializer(serializers.Serializer):
    """Para el POS: precio promocional por producto."""
    product_id = serializers.IntegerField()
    promotion_id = serializers.IntegerField()
    promotion_name = serializers.CharField()
    discount_type = serializers.CharField()
    discount_value = serializers.DecimalField(max_digits=12, decimal_places=2)
    original_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    promo_price = serializers.DecimalField(max_digits=12, decimal_places=2)
