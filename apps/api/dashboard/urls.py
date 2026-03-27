# dashboard/urls.py
from django.urls import path

# import from __init__.py where we put the view
from dashboard import DashboardSummaryView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
]