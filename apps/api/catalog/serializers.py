from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from .services import validate_ean13
from .models import Category, Product, Barcode, Recipe, RecipeLine, Unit


def _tenant_id(request):
    user = getattr(request, "user", None)
    return getattr(user, "tenant_id", None)


def _resolve_unit_obj(tenant_id, unit_code):
    """
    Resolve a unit string code (e.g. 'KG') to a Unit FK for the tenant.
    Returns the Unit instance or None if not found.
    """
    if not unit_code or not tenant_id:
        return None
    code = unit_code.strip().upper()
    return Unit.objects.filter(tenant_id=tenant_id, code=code, is_active=True).first()


# -----------------------
# Category
# -----------------------
class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.PrimaryKeyRelatedField(source="parent",
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
    )
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    children_count = serializers.SerializerMethodField(read_only=True)

    # default_print_station_id: la estación a la que van las comandas de
    # esta categoría. Lo manejamos como IntegerField simple (read+write)
    # para evitar el import circular catalog → printing en module load.
    # La validación de pertenencia al tenant + activeness se hace en
    # `validate_default_print_station_id`.
    default_print_station_id = serializers.IntegerField(
        required=False, allow_null=True,
    )
    default_print_station_name = serializers.CharField(
        source="default_print_station.name", read_only=True, default=None,
    )

    class Meta:
        model = Category
        fields = [
            "id", "name", "code",
            "parent_id", "parent_name",
            "is_active", "children_count",
            "default_print_station_id", "default_print_station_name",
        ]

    def get_children_count(self, obj):
        # Use annotated value from queryset to avoid N+1
        v = getattr(obj, "children_count", None)
        if v is not None:
            return v
        return obj.children.count()

    def validate_default_print_station_id(self, value):
        # value llega como int (id) o None. Verificamos que la estación
        # exista, pertenezca al tenant y esté activa antes de aceptar.
        if value is None:
            return None
        request = self.context.get("request")
        t_id = _tenant_id(request)
        if not t_id:
            raise serializers.ValidationError("User must have a tenant.")
        from printing.models import PrintStation
        if not PrintStation.objects.filter(
            pk=value, tenant_id=t_id, is_active=True,
        ).exists():
            raise serializers.ValidationError(
                "Print station does not exist or does not belong to your tenant.",
            )
        return value

    def validate_parent_id(self, value):
        # validar que el parent pertenece al mismo tenant
        request = self.context.get("request")
        if value and request and request.user.tenant_id and value.tenant_id != request.user.tenant_id:
            raise serializers.ValidationError("Parent category does not belong to your tenant.")
        # evitar ciclos: recorrer ancestros para detectar referencias circulares
        if value and self.instance:
            ancestor = value
            visited = set()
            while ancestor is not None:
                if ancestor.pk in visited:
                    raise serializers.ValidationError("Referencia circular detectada en la jerarquía de categorías.")
                visited.add(ancestor.pk)
                if ancestor.pk == self.instance.pk:
                    raise serializers.ValidationError("Una categoría no puede ser descendiente de sí misma.")
                ancestor = ancestor.parent
        return value


# -----------------------
# Barcode
# -----------------------
class BarcodeSerializer(serializers.ModelSerializer):
    def validate_code(self, value):
        code = value.strip()
        if not code:
            raise serializers.ValidationError("Barcode cannot be empty.")
        # Si parece EAN13 (13 dígitos), validar checksum
        if code.isdigit() and len(code) == 13:
            if not validate_ean13(code):
                raise serializers.ValidationError(f"EAN-13 checksum inválido: {code}")
        return code


    class Meta:
        model = Barcode
        fields = ["id", "code", "barcode_type"]  # ← agregar barcode_type





# -----------------------
# Product (READ)
# Devuelve category + barcodes list
# -----------------------
class ProductReadSerializer(serializers.ModelSerializer):
    category   = CategorySerializer(read_only=True)
    barcodes   = BarcodeSerializer(many=True, read_only=True)
    has_recipe = serializers.SerializerMethodField()
    unit_obj_id = serializers.IntegerField(read_only=True, default=None)
    unit_obj_family = serializers.CharField(source="unit_obj.family", read_only=True, default=None)

    # Estación efectiva (resuelve override > category default > null) —
    # entrega el id que el frontend usa para agrupar líneas en comandas
    # sin tener que hacer la lookup en el cliente.
    effective_print_station_id = serializers.SerializerMethodField()

    def get_effective_print_station_id(self, obj):
        if obj.print_station_override_id:
            return obj.print_station_override_id
        if obj.category and obj.category.default_print_station_id:
            return obj.category.default_print_station_id
        return None

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "unit",
            "price",
            "is_active",
            "category",
            "barcodes",
            "has_recipe",
            "unit_obj_id", "unit_obj_family",
            "price", "cost", "tax_rate", "min_stock",
            "brand", "image_url",
            "print_station_override", "effective_print_station_id",
            "allow_negative_stock",
            "created_at", "updated_at",
        ]

    def get_has_recipe(self, obj):
        r = getattr(obj, "recipe", None)
        return r is not None and r.is_active


# ─── Recipe serializers ────────────────────────────────────────────────────────

class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Unit
        fields = ["id", "code", "name", "family", "is_base", "base_unit", "conversion_factor", "is_active"]


class RecipeLineReadSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    ingredient_sku  = serializers.CharField(source="ingredient.sku",  read_only=True)
    ingredient_unit = serializers.CharField(source="ingredient.unit", read_only=True)
    ingredient_unit_obj_id = serializers.IntegerField(source="ingredient.unit_obj_id", read_only=True, default=None)
    ingredient_unit_family = serializers.CharField(source="ingredient.unit_obj.family", read_only=True, default=None, allow_null=True)
    unit_id   = serializers.IntegerField(source="unit.id",   read_only=True, default=None)
    unit_code = serializers.CharField(source="unit.code", read_only=True, default=None, allow_null=True)

    class Meta:
        model  = RecipeLine
        fields = [
            "id", "ingredient_id", "ingredient_name", "ingredient_sku", "ingredient_unit",
            "ingredient_unit_obj_id", "ingredient_unit_family",
            "qty", "unit_id", "unit_code",
        ]


class RecipeReadSerializer(serializers.ModelSerializer):
    lines = RecipeLineReadSerializer(many=True, read_only=True)

    class Meta:
        model  = Recipe
        fields = ["id", "product_id", "is_active", "notes", "lines", "created_at", "updated_at"]


class RecipeLineWriteSerializer(serializers.Serializer):
    ingredient_id = serializers.IntegerField()
    qty           = serializers.DecimalField(max_digits=12, decimal_places=4)
    unit_id       = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate_qty(self, v):
        if v <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0.")
        return v


class RecipeWriteSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(default=True)
    notes     = serializers.CharField(required=False, allow_blank=True, default="")
    lines     = RecipeLineWriteSerializer(many=True)

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("La receta debe tener al menos un ingrediente.")
        ids = [l["ingredient_id"] for l in lines]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("No puede repetir el mismo ingrediente.")

        # ── BLINDAJE de coherencia de unidades ─────────────────────────
        # Mario lo pidió: "que pasa si el usuario sube leche pero como 1
        # unidad en vez de en litros o ml?". Escenarios riesgosos:
        #
        #   1. Ingrediente con unit_obj de COUNT (ej. UN) y receta dice
        #      0.15 L → al vender, se descuentan 0.15 UN (15% de un
        #      cartón) en vez de 1 L del cartón. Stock y costo erróneos.
        #
        #   2. Ingrediente sin unit_obj (solo string "UN") y receta con
        #      unit_id de VOLUME → la conversión no corre y se descuenta
        #      qty raw.
        #
        # Validamos:
        #   - Si la línea NO tiene unit_id, asumimos que la qty está en
        #     la unidad del ingrediente. OK.
        #   - Si la línea tiene unit_id, exigimos que la familia matchee
        #     con la unit_obj del ingrediente (o que el ingrediente
        #     tenga unit_obj).
        request = self.context.get("request")
        tenant_id = (
            getattr(request.user, "tenant_id", None) if request else None
        )
        if not tenant_id:
            return lines  # sin tenant no podemos validar — caso fixture/test

        from .models import Product, Unit
        ingredient_ids = [l["ingredient_id"] for l in lines]
        ingredients = {
            p.id: p
            for p in Product.objects.filter(
                tenant_id=tenant_id, id__in=ingredient_ids,
            ).select_related("unit_obj")
        }
        unit_ids = [l["unit_id"] for l in lines if l.get("unit_id")]
        units = {u.id: u for u in Unit.objects.filter(tenant_id=tenant_id, id__in=unit_ids)} if unit_ids else {}

        FAMILY_LABEL = {
            "MASS": "masa (KG/GR)",
            "VOLUME": "volumen (L/ML)",
            "LENGTH": "longitud",
            "COUNT": "conteo (unidades)",
        }
        errors = []
        for line in lines:
            ing = ingredients.get(line["ingredient_id"])
            if not ing:
                # validación más arriba lo cubre (404 al guardar)
                continue
            unit_id = line.get("unit_id")
            if not unit_id:
                # Línea sin unit_id explícito = se asume unidad del
                # ingrediente. Sin desalineación posible.
                continue
            line_unit = units.get(unit_id)
            if not line_unit:
                errors.append(f"{ing.name}: la unidad seleccionada (id={unit_id}) no existe en este negocio.")
                continue
            ing_unit_obj = ing.unit_obj
            if not ing_unit_obj:
                # El producto NO tiene unit_obj configurado (solo el
                # string `unit`). No podemos validar familia. Bloqueamos
                # con mensaje accionable.
                errors.append(
                    f"{ing.name}: el producto no tiene unidad de medida configurada. "
                    f"Edita el producto y asigna una unidad (KG, GR, L, ML, UN...) "
                    f"antes de usarlo en una receta."
                )
                continue
            if line_unit.family != ing_unit_obj.family:
                ing_fam = FAMILY_LABEL.get(ing_unit_obj.family, ing_unit_obj.family)
                line_fam = FAMILY_LABEL.get(line_unit.family, line_unit.family)
                errors.append(
                    f"{ing.name}: la receta dice {line_unit.code} ({line_fam}) "
                    f"pero el producto está en {ing_unit_obj.code} ({ing_fam}). "
                    f"Convierte el producto a {line_fam} o cambia la unidad de la receta."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return lines


# -----------------------
# Product (WRITE)
# - category: id o null
# - barcode_codes: ["...", "..."]
# - sku: opcional, pero si viene NO puede repetirse dentro del tenant
# -----------------------
class ProductWriteSerializer(serializers.ModelSerializer):
    # permitir null (front puede mandar null) y luego normalizamos a ""
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sku = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unit = serializers.CharField(required=False, allow_blank=True, allow_null=True,)

    barcode_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
    )

    # new optional fields
    min_stock = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, default=0)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    brand = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "description",
            "unit",
            "price",
            "is_active",
            "category",
            "barcode_codes",
            "min_stock",
            "cost",
            # Estación de impresión opcional (override). Si null, hereda de
            # la categoría. Validamos pertenencia al tenant en validate().
            "print_station_override",
            # Permitir vender este producto aunque no haya stock. Antes el
            # campo se mandaba pero el backend lo descartaba — placebo.
            "allow_negative_stock",
            "brand",
            "image_url",
        ]

    def validate_category(self, value):
        request = self.context.get("request")
        t_id = _tenant_id(request)

        if value is None:
            return None

        if not t_id:
            raise serializers.ValidationError("User must have a tenant.")

        if value.tenant_id != t_id:
            raise serializers.ValidationError("Category does not belong to your tenant.")

        return value

    def validate_print_station_override(self, value):
        # value es una PrintStation instance o None (DRF resolvió el FK
        # a partir del id). Verificamos pertenencia al tenant y activeness.
        if value is None:
            return None
        request = self.context.get("request")
        t_id = _tenant_id(request)
        if not t_id:
            raise serializers.ValidationError("User must have a tenant.")
        if value.tenant_id != t_id:
            raise serializers.ValidationError("Print station does not belong to your tenant.")
        if not value.is_active:
            raise serializers.ValidationError("La estación de impresión está inactiva.")
        return value

    def validate_barcode_codes(self, codes):
        cleaned = []
        seen = set()
        for c in codes or []:
            cc = (c or "").strip()
            if not cc:
                continue
            if cc in seen:
                continue
            seen.add(cc)
            cleaned.append(cc)

        if len(cleaned) > 30:
            raise serializers.ValidationError("Too many barcodes (max 30).")

        return cleaned

    def validate(self, attrs):
        unit = attrs.get("unit")
        request = self.context.get("request")
        t_id = _tenant_id(request)
        VALID_UNIT =  {"UN", "KG", "GR", "LT", "ML", "MT", "CM", "CAJA", "PAQ", "DOC"}
        attrs["unit"] = unit

        if unit in (None, ""):
            attrs["unit"] = "UN"
        elif isinstance(unit, str):
             attrs["unit"] = unit.strip().upper()
        else:
            raise serializers.ValidationError({"unit": "Unit must be a string."})

        if not t_id:
            raise serializers.ValidationError({"detail": "User must have a tenant."})

        # Validate price and cost are non-negative
        price = attrs.get("price")
        if price is not None and price < 0:
            raise serializers.ValidationError({"price": "El precio no puede ser negativo."})
        cost = attrs.get("cost")
        if cost is not None and cost < 0:
            raise serializers.ValidationError({"cost": "El costo no puede ser negativo."})

        # normalización global (front puede mandar null)
        if attrs.get("description", None) is None:
            attrs["description"] = ""
        if attrs.get("brand", None) is None:
            attrs["brand"] = ""
        if attrs.get("image_url", None) is None:
            attrs["image_url"] = ""

        # SKU: normaliza null->"" y valida unicidad si viene
        if attrs.get("sku", None) is None:
            attrs["sku"] = ""
        if attrs.get("unit", None) is None:
            attrs["unit"] = "UN"

        sku = (attrs.get("sku") or "").strip()
        if sku:
            qs = Product.objects.filter(tenant_id=t_id, sku__iexact=sku)

            # si estamos actualizando, excluye el mismo producto
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise serializers.ValidationError({"sku": "SKU already exists for this tenant."})

            # deja el sku limpio
            attrs["sku"] = sku

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        IMPORTANTE:
        - La VIEW ya hace serializer.save(tenant_id=...)
        - Por eso aquí NO volvemos a pasar tenant_id al create()
        """
        request = self.context.get("request")
        t_id = _tenant_id(request)
        if not t_id:
            raise serializers.ValidationError({"detail": "User must have a tenant."})

        barcode_codes = validated_data.pop("barcode_codes", [])

        # Auto-resolve unit_obj FK from unit string
        unit_code = validated_data.get("unit", "UN")
        if not validated_data.get("unit_obj"):
            unit_obj = _resolve_unit_obj(t_id, unit_code)
            if unit_obj:
                validated_data["unit_obj"] = unit_obj

        # create producto (tenant_id viene desde view -> serializer.save(tenant_id=...))
        product = Product.objects.create(**validated_data)

        # crear barcodes (tenant = del usuario)
        if barcode_codes:
            Barcode.objects.bulk_create(
                [Barcode(tenant_id=t_id, product=product, code=code) for code in barcode_codes]
            )

        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        t_id = _tenant_id(request)

        if not t_id:
            raise serializers.ValidationError({"detail": "User must have a tenant."})

        if instance.tenant_id != t_id:
            raise serializers.ValidationError({"detail": "Product does not belong to your tenant."})

        barcode_codes = validated_data.pop("barcode_codes", None)  # None => no tocar

        # set fields (normaliza nulls)
        for attr, value in validated_data.items():
            if attr in ("description", "sku", "brand", "image_url") and value is None:
                value = ""
            if attr == "unit" and value is None:
                value = "UN"
            if attr == "sku" and isinstance(value, str):
                value = value.strip()
            setattr(instance, attr, value)

        # Auto-resolve unit_obj FK when unit string changes
        if "unit" in validated_data:
            unit_obj = _resolve_unit_obj(t_id, validated_data["unit"])
            if unit_obj:
                instance.unit_obj = unit_obj

        instance.save()

        # reemplazo total de barcodes
        if barcode_codes is not None:
            Barcode.objects.filter(tenant_id=t_id, product=instance).delete()
            if barcode_codes:
                Barcode.objects.bulk_create(
                    [Barcode(tenant_id=t_id, product=instance, code=code) for code in barcode_codes]
                )

        return instance