from django.urls import path
from reports import views
from reports.exports import (
    SalesSummaryExportView,
    LossesExportView,
    StockValuedExportView,
    AuditTrailExportView,
)

urlpatterns = [
    # Stock y operación
    path("stock-valued/", views.StockValuedReportView.as_view(), name="report-stock-valued"),
    path("transfer-suggestion-sheet/", views.TransferSuggestionSheetReportView.as_view(), name="report-transfer-suggestion-sheet"),
    path("losses/", views.LossesReportView.as_view(), name="report-losses"),

    # Ventas y rentabilidad
    path("sales-summary/", views.SalesSummaryReportView.as_view(), name="report-sales-summary"),
    path("top-products/", views.TopProductsReportView.as_view(), name="report-top-products"),
    path("profitability/", views.ProfitabilityReportView.as_view(), name="report-profitability"),

    # Inventario
    path("dead-stock/", views.DeadStockReportView.as_view(), name="report-dead-stock"),
    path("inventory-count-sheet/", views.InventoryCountSheetView.as_view(), name="report-inventory-count-sheet"),
    path("inventory-diff/", views.InventoryDiffReportView.as_view(), name="report-inventory-diff"),
    path("audit-trail/", views.AuditTrailReportView.as_view(), name="report-audit-trail"),
    path("abc-analysis/", views.ABCAnalysisReportView.as_view(), name="report-abc-analysis"),
    path("inventory-health/", views.InventoryHealthView.as_view(), name="report-inventory-health"),

    # Exports
    path("sales-summary/export/", SalesSummaryExportView.as_view(), name="report-sales-summary-export"),
    path("losses/export/", LossesExportView.as_view(), name="report-losses-export"),
    path("stock-valued/export/", StockValuedExportView.as_view(), name="report-stock-valued-export"),
    path("audit-trail/export/", AuditTrailExportView.as_view(), name="report-audit-trail-export"),
]