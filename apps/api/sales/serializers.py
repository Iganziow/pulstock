from decimal import Decimal
from rest_framework import serializers

from .models import Sale, SaleLine, SalePayment
from catalog.serializers import ProductReadSerializer
from inventory.models import StockMove


# =========================
# INPUT (CREATE SALE)
# =========================

DISCOUNT_TYPE_CHOICES = [("none", "none"), ("pct", "pct"), ("amt", "amt")]


class SaleLineInSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPE_CHOICES, default="none", required=False)
    discount_value = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), required=False)
    promotion_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("qty must be > 0")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("unit_price must be >= 0")
        return value

    def validate_discount_value(self, value):
        if value < 0:
            raise serializers.ValidationError("discount_value must be >= 0")
        return value


class SaleCreateSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    lines = SaleLineInSerializer(many=True)
    global_discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPE_CHOICES, default="none", required=False)
    global_discount_value = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), required=False)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("lines is required")
        if len(lines) > 200:
            raise serializers.ValidationError("Máximo 200 líneas por venta.")
        return lines


# =========================
# OUTPUT (LIST)
# =========================

class SaleListSerializer(serializers.ModelSerializer):
    """
    Listado de ventas (store-aware desde la view).
    Incluye campos de costo para reportes.
    """
    table_name = serializers.SerializerMethodField()

    def get_table_name(self, obj):
        if obj.open_order_id:
            try:
                return obj.open_order.table.name
            except Exception:
                return None
        return None

    class Meta:
        model = Sale
        fields = [
            "id",
            "sale_number",
            "created_at",
            "store_id",
            "warehouse_id",
            "subtotal",
            "total",
            "tip",
            "total_cost",
            "gross_profit",
            "status",
            "sale_type",
            "created_by_id",
            "open_order_id",
            "table_name",
        ]


# =========================
# OUTPUT (DETAIL)
# =========================

class SaleLineSerializer(serializers.ModelSerializer):
    product = ProductReadSerializer(read_only=True)

    # ✅ calculados desde StockMove ref_type="SALE" (fallback),
    #    pero si existen en el modelo (SaleLine.unit_cost_snapshot/line_cost/line_gross_profit),
    #    preferimos esos valores para no recalcular.
    unit_cost_snapshot = serializers.SerializerMethodField()
    line_cost = serializers.SerializerMethodField()
    line_profit = serializers.SerializerMethodField()

    def _moves_map(self, sale_id: int, tenant_id=None):
        """
        Cache interno por serializer instance:
        map[(sale_id, tenant_id)] -> {product_id -> StockMove}

        Si la vista pasó 'sale_moves_map' en el context, lo usa directamente
        para evitar queries adicionales.
        """
        # ── Atajo: mapa pre-cargado desde la vista ──
        ctx_map = self.context.get("sale_moves_map")
        if ctx_map is not None:
            return ctx_map

        # ── Fallback: query con cache por instancia ──
        cache = getattr(self, "_sale_moves_cache", None)
        if cache is None:
            cache = {}
            self._sale_moves_cache = cache

        cache_key = (int(sale_id), int(tenant_id) if tenant_id is not None else None)
        if cache_key in cache:
            return cache[cache_key]

        qs = (
            StockMove.objects
            .filter(ref_type="SALE", ref_id=sale_id)
            .only("id", "product_id", "cost_snapshot", "value_delta", "qty")
        )

        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)

        mp = {}
        for m in qs:
            mp[int(m.product_id)] = m

        cache[cache_key] = mp
        return mp

    def get_unit_cost_snapshot(self, obj: SaleLine):
        # 1) si el modelo tiene el campo y está seteado, úsalo
        if hasattr(obj, "unit_cost_snapshot"):
            v = getattr(obj, "unit_cost_snapshot", None)
            if v is not None:
                return str(v)

        # 2) fallback: desde StockMove
        sale_id = obj.sale_id
        tenant_id = getattr(obj, "tenant_id", None)
        mp = self._moves_map(sale_id, tenant_id=tenant_id)
        m = mp.get(int(obj.product_id))
        if not m or m.cost_snapshot is None:
            return None
        return str(m.cost_snapshot)

    def get_line_cost(self, obj: SaleLine):
        # 1) si el modelo tiene el campo y está seteado, úsalo
        if hasattr(obj, "line_cost"):
            v = getattr(obj, "line_cost", None)
            if v is not None:
                return str(v)

        # 2) fallback: desde StockMove.value_delta (OUT negativo)
        sale_id = obj.sale_id
        tenant_id = getattr(obj, "tenant_id", None)
        mp = self._moves_map(sale_id, tenant_id=tenant_id)
        m = mp.get(int(obj.product_id))
        if not m:
            return "0.000"
        if m.value_delta is None:
            return "0.000"
        v = Decimal(str(m.value_delta))
        return str(abs(v))

    def get_line_profit(self, obj: SaleLine):
        # 1) si el modelo tiene el campo line_gross_profit, úsalo
        if hasattr(obj, "line_gross_profit"):
            v = getattr(obj, "line_gross_profit", None)
            if v is not None:
                return str(v)

        # 2) fallback: profit = line_total - line_cost
        try:
            line_total = Decimal(str(obj.line_total or "0"))
        except Exception:
            line_total = Decimal("0")

        try:
            line_cost = Decimal(str(self.get_line_cost(obj) or "0"))
        except Exception:
            line_cost = Decimal("0")

        return str((line_total - line_cost).quantize(Decimal("1")))

    class Meta:
        model = SaleLine
        fields = [
            "id",
            "product",
            "qty",
            "unit_price",
            "line_total",
            "discount_amount",
            "original_unit_price",
            # ✅ cost tracking
            "unit_cost_snapshot",
            "line_cost",
            "line_profit",
        ]


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = ["method", "amount"]


class SaleDetailSerializer(serializers.ModelSerializer):
    lines    = SaleLineSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "sale_number",
            "created_at",
            "store_id",
            "warehouse_id",
            "subtotal",
            "total",
            "tip",
            "total_cost",
            "gross_profit",
            "status",
            "sale_type",
            "payments",
            "lines",
        ]
