from django.contrib import admin
from .models import Category, Product, Barcode

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "code")
    list_filter = ("tenant",)
    search_fields = ("name", "code")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "name", "sku", "price", "unit", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "sku")

@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "code", "product")
    list_filter = ("tenant",)
    search_fields = ("code",)
