from django.urls import path
from forecast import views

urlpatterns = [
    # Dashboard KPIs
    path("dashboard/", views.ForecastDashboardView.as_view(), name="forecast-dashboard"),

    # Products with forecast
    path("products/", views.ForecastProductListView.as_view(), name="forecast-products"),
    path("products/<int:product_id>/", views.ForecastProductDetailView.as_view(), name="forecast-product-detail"),

    # Alerts
    path("alerts/", views.ForecastAlertsView.as_view(), name="forecast-alerts"),

    # Suggestions
    path("suggestions/", views.SuggestionListView.as_view(), name="forecast-suggestions"),
    path("suggestions/<int:pk>/approve/", views.SuggestionApproveView.as_view(), name="forecast-suggestion-approve"),
    path("suggestions/<int:pk>/dismiss/", views.SuggestionDismissView.as_view(), name="forecast-suggestion-dismiss"),

    # Holidays
    path("holidays/", views.HolidayListCreateView.as_view(), name="forecast-holidays"),
    path("holidays/<int:pk>/", views.HolidayDetailView.as_view(), name="forecast-holiday-detail"),
]