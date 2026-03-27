from django.contrib import admin
from forecast.models import DailySales, ForecastModel, Forecast, PurchaseSuggestion, SuggestionLine


@admin.register(DailySales)
class DailySalesAdmin(admin.ModelAdmin):
    list_display = ["date", "product", "warehouse", "qty_sold", "revenue", "qty_lost"]
    list_filter = ["date", "warehouse"]
    search_fields = ["product__name"]


@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ["product", "warehouse", "algorithm", "version", "is_active", "data_points", "trained_at"]
    list_filter = ["algorithm", "is_active"]
    search_fields = ["product__name"]


@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ["product", "warehouse", "forecast_date", "qty_predicted", "days_to_stockout"]
    list_filter = ["forecast_date", "warehouse"]


@admin.register(PurchaseSuggestion)
class PurchaseSuggestionAdmin(admin.ModelAdmin):
    list_display = ["id", "warehouse", "supplier_name", "status", "priority", "total_estimated", "generated_at"]
    list_filter = ["status", "priority"]


@admin.register(SuggestionLine)
class SuggestionLineAdmin(admin.ModelAdmin):
    list_display = ["suggestion", "product", "current_stock", "days_to_stockout", "suggested_qty"]