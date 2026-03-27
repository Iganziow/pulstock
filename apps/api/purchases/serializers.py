# purchases/serializers.py
from decimal import Decimal
from rest_framework import serializers

from catalog.serializers import ProductReadSerializer
from .models import Purchase, PurchaseLine


def _clean_note(v):
    if v is None:
        return ""
    return str(v).strip()


# (lo dejo porque lo tenías, aunque no se use aquí)
ISSUE_REASONS = ["MERMA", "VENCIDO", "USO_INTERNO", "OTRO"]


# =========================
# INPUT (CREATE PURCHASE)
# =========================
class PurchaseLineInSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=3)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return v

    def validate_unit_cost(self, v):
        if v is None:
            raise serializers.ValidationError("unit_cost is required")
        if v < 0:
            raise serializers.ValidationError("unit_cost must be >= 0")
        return v

    def validate_note(self, v):
        return _clean_note(v)


class PurchaseCreateSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    supplier_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    invoice_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    invoice_date = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # IVA opcional por ahora: guardamos tax_amount si viene, si no -> 0
    tax_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=3,
        required=False,
        allow_null=True,
    )

    lines = PurchaseLineInSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("lines is required")
        if len(lines) > 500:
            raise serializers.ValidationError("Máximo 500 líneas por compra.")
        return lines

    def validate_supplier_name(self, v):
        return _clean_note(v)

    def validate_invoice_number(self, v):
        return _clean_note(v)

    def validate_note(self, v):
        return _clean_note(v)

    def validate_tax_amount(self, v):
        if v is None:
            return Decimal("0.000")
        if v < 0:
            raise serializers.ValidationError("tax_amount must be >= 0")
        return v


# =========================
# OUTPUT (LINES)
# =========================
class PurchaseLineSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)

    class Meta:
        model = PurchaseLine
        fields = [
            "id",
            "product",
            "qty",
            "unit_cost",
            "line_total_cost",
            "note",
        ]


# =========================
# OUTPUT (LIST)
# =========================
class PurchaseListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Purchase
        fields = [
            "id",
            "created_at",
            "store_id",
            "warehouse_id",
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "status",
            "subtotal_cost",
            "tax_amount",
            "total_cost",
            "created_by_id",
        ]


# =========================
# OUTPUT (DETAIL)
# =========================
class PurchaseDetailSerializer(serializers.ModelSerializer):
    lines = PurchaseLineSerializer(many=True, read_only=True)

    class Meta:
        model = Purchase
        fields = [
            "id",
            "created_at",
            "store_id",
            "warehouse_id",
            "supplier_name",
            "invoice_number",
            "invoice_date",
            "note",
            "status",
            "subtotal_cost",
            "tax_amount",
            "total_cost",
            "created_by_id",
            "lines",
        ]
