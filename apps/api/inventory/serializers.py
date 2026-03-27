from catalog.models import Product
from inventory.models import StockTransfer, StockTransferLine, StockMove
from rest_framework import serializers


def _clean_note(v):
    if v is None:
        return ""
    return str(v).strip()


ISSUE_REASONS = ["MERMA", "VENCIDO", "USO_INTERNO", "OTRO"]


class StockAdjustSerializer(serializers.Serializer):
    warehouse_id  = serializers.IntegerField()
    product_id    = serializers.IntegerField()
    qty           = serializers.DecimalField(max_digits=12, decimal_places=3)
    note          = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    new_avg_cost  = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        required=False, allow_null=True,
        help_text="Si se provee, sobrescribe el costo promedio ponderado directamente.",
    )

    def validate_qty(self, v):
        return v  # 0 allowed when only new_avg_cost is provided (cross-validated in view)

    def validate_note(self, v):
        return _clean_note(v)

    def validate_new_avg_cost(self, v):
        if v is not None and v < 0:
            raise serializers.ValidationError("new_avg_cost must be >= 0")
        return v


class StockReceiveSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return v

    def validate_unit_cost(self, v):
        if v is None:
            return None
        if v < 0:
            raise serializers.ValidationError("unit_cost must be >= 0")
        return v

    def validate_note(self, v):
        return _clean_note(v)


class StockIssueSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)

    # motivo tipificado (obligatorio)
    reason = serializers.ChoiceField(choices=ISSUE_REASONS)

    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return v

    def validate_note(self, v):
        return _clean_note(v)


# ======================================================
# TRANSFER (CREATE) - usados por POST /inventory/transfer/
# ======================================================
class TransferLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
        allow_null=True,
    )
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return v

    def validate_unit_cost(self, v):
        if v is None:
            return None
        if v < 0:
            raise serializers.ValidationError("unit_cost must be >= 0")
        return v

    def validate_note(self, v):
        return _clean_note(v)


class StockTransferSerializer(serializers.Serializer):
    from_warehouse_id = serializers.IntegerField()
    to_warehouse_id = serializers.IntegerField()
    lines = TransferLineSerializer(many=True)

    def validate(self, attrs):
        if attrs["from_warehouse_id"] == attrs["to_warehouse_id"]:
            raise serializers.ValidationError({"detail": "from_warehouse_id and to_warehouse_id must be different"})
        if not attrs.get("lines"):
            raise serializers.ValidationError({"detail": "lines must not be empty"})
        return attrs


class ProductMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "sku", "is_active"]


class StockMoveListSerializer(serializers.ModelSerializer):
    product = ProductMiniSerializer(read_only=True)
    created_by = serializers.SerializerMethodField()
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)
    warehouse_type = serializers.CharField(source="warehouse.warehouse_type", read_only=True, default=None)

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return {"id": obj.created_by_id, "username": getattr(obj.created_by, "username", None)}

    class Meta:
        model = StockMove
        fields = [
            "id",
            "created_at",
            "warehouse_id",
            "warehouse_name",
            "warehouse_type",
            "product",
            "move_type",
            "qty",
            "unit_cost",
            "reason",
            "ref_type",
            "ref_id",
            "note",
            "created_by",
            # ✅ costos (promedio ponderado / snapshot)
            "cost_snapshot",
            "value_delta",
        ]


# ======================================================
# KARDEX
# ======================================================
class KardexProductSerializer(serializers.ModelSerializer):
    barcode = serializers.SerializerMethodField()

    def get_barcode(self, obj):
        bcs = list(getattr(obj, "barcodes", []).all()) if hasattr(obj, "barcodes") else []
        if not bcs:
            return None
        return bcs[0].code

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "barcode"]


class KardexRowSerializer(serializers.ModelSerializer):
    product = KardexProductSerializer(read_only=True)
    created_by = serializers.SerializerMethodField()
    balance = serializers.CharField()  # decimal string calculado en view

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return {"id": obj.created_by_id, "username": getattr(obj.created_by, "username", None)}

    class Meta:
        model = StockMove
        fields = [
            "id",
            "created_at",
            "warehouse_id",
            "move_type",
            "product",
            "qty",
            "balance",
            "ref_type",
            "ref_id",
            "note",
            "created_by",
            # ✅ costos para reportes y auditoría
            "unit_cost",
            "cost_snapshot",
            "value_delta",
        ]


# ======================================================
# TRANSFER DETAIL (GET /inventory/transfers/<id>/)
# ======================================================
class TransferLineDetailSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    def get_product(self, obj):
        p = obj.product
        barcode = None
        bcs = list(getattr(p, "barcodes", []).all()) if hasattr(p, "barcodes") else []
        if bcs:
            barcode = bcs[0].code
        return {"id": p.id, "name": p.name, "sku": getattr(p, "sku", None), "barcode": barcode}

    class Meta:
        model = StockTransferLine
        fields = ["id", "product", "qty", "note"]


class TransferDetailSerializer(serializers.ModelSerializer):
    from_warehouse = serializers.SerializerMethodField()
    to_warehouse = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    lines = TransferLineDetailSerializer(many=True, read_only=True)
    moves = serializers.SerializerMethodField()

    def get_from_warehouse(self, obj):
        return {"id": obj.from_warehouse_id, "name": obj.from_warehouse.name, "warehouse_type": obj.from_warehouse.warehouse_type}

    def get_to_warehouse(self, obj):
        return {"id": obj.to_warehouse_id, "name": obj.to_warehouse.name, "warehouse_type": obj.to_warehouse.warehouse_type}

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return {"id": obj.created_by_id, "username": getattr(obj.created_by, "username", None)}

    def get_moves(self, obj):
        qs = (
            StockMove.objects.filter(
                tenant_id=obj.tenant_id,
                ref_type="TRANSFER",
                ref_id=obj.id,
            )
            .select_related("created_by", "product")
            .order_by("created_at", "id")
        )
        return [
            {
                "id": m.id,
                "created_at": m.created_at,
                "warehouse_id": m.warehouse_id,
                "move_type": m.move_type,
                "product_id": m.product_id,
                "qty": str(m.qty),
                "note": m.note,
                "created_by": getattr(getattr(m, "created_by", None), "username", None),
                # ✅ costos
                "unit_cost": str(m.unit_cost) if m.unit_cost is not None else None,
                "cost_snapshot": str(m.cost_snapshot) if m.cost_snapshot is not None else None,
                "value_delta": str(m.value_delta) if m.value_delta is not None else None,
            }
            for m in qs
        ]

    class Meta:
        model = StockTransfer
        fields = ["id", "created_at", "note", "from_warehouse", "to_warehouse", "created_by", "lines", "moves"]


class TransferListSerializer(serializers.ModelSerializer):
    from_warehouse = serializers.SerializerMethodField()
    to_warehouse = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    lines_count = serializers.IntegerField(read_only=True)

    def get_from_warehouse(self, obj):
        return {"id": obj.from_warehouse_id, "name": obj.from_warehouse.name, "warehouse_type": obj.from_warehouse.warehouse_type}

    def get_to_warehouse(self, obj):
        return {"id": obj.to_warehouse_id, "name": obj.to_warehouse.name, "warehouse_type": obj.to_warehouse.warehouse_type}

    def get_created_by(self, obj):
        if not obj.created_by_id:
            return None
        return {"id": obj.created_by_id, "username": getattr(obj.created_by, "username", None)}

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "created_at",
            "note",
            "from_warehouse",
            "to_warehouse",
            "created_by",
            "lines_count",
        ]


# ======================================================
# KARDEX REPORT (resumen por producto)
# ======================================================
class KardexReportProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sku = serializers.CharField(allow_null=True, required=False)
    barcode = serializers.CharField(allow_null=True, required=False)


class KardexReportRowSerializer(serializers.Serializer):
    product = KardexReportProductSerializer()
    in_qty = serializers.CharField()
    out_qty = serializers.CharField()
    adj_qty = serializers.CharField()
    net_qty = serializers.CharField()
    moves_count = serializers.IntegerField()
