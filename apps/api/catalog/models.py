from django.db import models
from core.models import Tenant
from django.db.models import Q


# catalog/models.py — agregar modelo:
class Unit(models.Model):
    """Unidades de medida del tenant."""
    UNIT_FAMILIES = [
        ("MASS", "Masa"),
        ("VOLUME", "Volumen"),
        ("LENGTH", "Longitud"),
        ("COUNT", "Conteo"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="units")
    code = models.CharField(max_length=20)   # "KG", "GR", "UN"
    name = models.CharField(max_length=60)   # "Kilogramo", "Gramo", "Unidad"
    family = models.CharField(max_length=10, choices=UNIT_FAMILIES, default="COUNT")
    is_base = models.BooleanField(default=False)
    base_unit = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="derived_units",
        help_text="Unidad base para conversión (ej: GR -> KG)"
    )
    conversion_factor = models.DecimalField(
        max_digits=18, decimal_places=8, default=1,
        help_text="1 esta unidad = X unidades base (ej: 1 KG = 1000 GR → factor=1000)"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("tenant", "code")]
        indexes = [models.Index(fields=["tenant", "code"])]

    def __str__(self):
        return f"{self.code} ({self.name})"



class Category(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="categories")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True, default="")  # familia opcional
    parent = models.ForeignKey(  "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",)
    is_active = models.BooleanField(default=True)  # ← NUEVO

    # Estación de impresión por defecto para todos los productos de esta
    # categoría. Las comandas se rutean por categoría → estación → impresora(s)
    # asignadas a esa estación. Productos individuales pueden override con
    # `Product.print_station_override`. Si está null, los productos caen
    # al fallback (estación marcada is_default_for_receipts).
    default_print_station = models.ForeignKey(
        "printing.PrintStation", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="default_categories",
        help_text="Estación de impresión donde sale la comanda por defecto (cocina, bar, etc.)",
    )

    class Meta:
        unique_together = [("tenant", "name")]
        indexes = [models.Index(fields=["tenant", "name"]),
                models.Index(fields=["tenant", "parent"]),
                models.Index(fields=["tenant", "is_active"]),  ]

    def __str__(self) -> str:
        return self.name
    
class Product(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey("Category", on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(
    max_digits=5, decimal_places=2, default=19.00,
    help_text="Porcentaje IVA, ej: 19.00 para 19%"
)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    min_stock = models.DecimalField(
    max_digits=12, decimal_places=3, default=0,
    help_text="Stock mínimo para alertas"
    )
    notes = models.TextField(blank=True, default="")
    brand = models.CharField(max_length=100, blank=True, default="")
    image_url = models.URLField(max_length=500, blank=True, default="")

    sku = models.CharField(max_length=80, blank=True, default="")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="", null=True)
    unit = models.CharField(max_length=30, blank=True, default="UN")
    is_active = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_obj = models.ForeignKey(
        "catalog.Unit", null=True, blank=True,
         on_delete=models.PROTECT, related_name="products"
    )

    # Override de estación de impresión a nivel producto. Si null, hereda
    # de la categoría. Útil cuando un producto no debe ir donde indica su
    # categoría (ej: "Café irlandés" en cat. "Tragos" pero sale en cocina).
    print_station_override = models.ForeignKey(
        "printing.PrintStation", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="override_products",
        help_text="Override estación de impresión para este producto (deja null para heredar de la categoría)",
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "sku"]),
            models.Index(fields=["tenant", "category"]),
            models.Index(fields=["tenant", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                condition=~Q(sku=""),
                name="uniq_product_sku_per_tenant_nonempty",
            )
        ]

    def __str__(self) -> str:
        return self.name


class Recipe(models.Model):
    """Receta de un producto: lista de ingredientes a descontar del stock al vender."""
    tenant    = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="recipes")
    product   = models.OneToOneField(
        "catalog.Product", on_delete=models.CASCADE, related_name="recipe"
    )
    is_active = models.BooleanField(default=True)
    notes     = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self):
        return f"Recipe(product={self.product_id})"


class RecipeLine(models.Model):
    """Ingrediente de una receta con su cantidad por unidad del producto padre."""
    tenant     = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="recipe_lines")
    recipe     = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="used_in_recipes",
        help_text="Producto/ingrediente a descontar del stock"
    )
    qty = models.DecimalField(
        max_digits=12, decimal_places=4,
        help_text="Cantidad de ingrediente por 1 unidad del producto padre"
    )
    unit = models.ForeignKey(
        "catalog.Unit", null=True, blank=True,
        on_delete=models.PROTECT, related_name="recipe_lines",
        help_text="Unidad de la cantidad. Si null, se usa la unidad del ingrediente."
    )

    class Meta:
        unique_together = [("recipe", "ingredient")]
        indexes = [
            models.Index(fields=["tenant", "recipe"]),
            models.Index(fields=["tenant", "ingredient"]),
        ]

    def __str__(self):
        return f"RecipeLine(recipe={self.recipe_id}, ingredient={self.ingredient_id}, qty={self.qty})"


class Barcode(models.Model):
    BARCODE_TYPES = [
        ("EAN13", "EAN-13"),
        ("EAN8", "EAN-8"),
        ("CODE128", "Code 128"),
        ("QR", "QR Code"),
        ("INTERNAL", "Código Interno"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="barcodes")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="barcodes")
    code = models.CharField(max_length=80)
    barcode_type = models.CharField(          # ← NUEVO, con default para no romper
        max_length=20, choices=BARCODE_TYPES,
        default="EAN13", blank=True
    )

    class Meta:
        unique_together = [("tenant", "code")]
        indexes = [
            models.Index(fields=["tenant", "code"]),
            models.Index(fields=["tenant", "product"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.barcode_type})"