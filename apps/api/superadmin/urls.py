from django.urls import path
from .views import (
    PlatformStatsView,
    RevenueChartView,
    TenantListView,
    TenantDetailView,
    AdminSubscriptionView,
    AdminUserListView,
    AdminUserCreateView,
    AdminUserToggleView,
    AdminUserDeleteView,
    AdminInvoiceListView,
    AdminInvoicePayView,
    AdminForecastMetricsView,
    AdminForecastTrainView,
    AdminImportSalesView,
    AdminHolidayListView,
    AdminHolidayDetailView,
    # Soporte (pre-piloto)
    AdminUserResetPasswordView,
    AdminTenantResendEmailView,
    AdminGlobalSearchView,
    AdminTenantNotesView,
)

urlpatterns = [
    # Dashboard
    path("stats/",                    PlatformStatsView.as_view()),
    path("revenue-chart/",           RevenueChartView.as_view()),

    # Soporte — búsqueda global
    path("search/",                  AdminGlobalSearchView.as_view()),

    # Tenants
    path("tenants/",                 TenantListView.as_view()),
    path("tenants/<int:tenant_id>/", TenantDetailView.as_view()),
    path("tenants/<int:tenant_id>/subscription/", AdminSubscriptionView.as_view()),
    path("tenants/<int:tenant_id>/notes/",         AdminTenantNotesView.as_view()),
    path("tenants/<int:tenant_id>/resend-email/",  AdminTenantResendEmailView.as_view()),

    # Users
    path("users/",                   AdminUserListView.as_view()),
    path("users/create/",           AdminUserCreateView.as_view()),
    path("users/<int:user_id>/toggle/", AdminUserToggleView.as_view()),
    path("users/<int:user_id>/reset-password/", AdminUserResetPasswordView.as_view()),
    path("users/<int:user_id>/",       AdminUserDeleteView.as_view()),

    # Invoices
    path("invoices/",               AdminInvoiceListView.as_view()),
    path("invoices/<int:invoice_id>/pay/", AdminInvoicePayView.as_view()),

    # Holidays
    path("holidays/",              AdminHolidayListView.as_view()),
    path("holidays/<int:holiday_id>/", AdminHolidayDetailView.as_view()),

    # Forecast
    path("forecast/",              AdminForecastMetricsView.as_view()),
    path("forecast/train/",        AdminForecastTrainView.as_view()),
    path("forecast/import-sales/", AdminImportSalesView.as_view()),
]
