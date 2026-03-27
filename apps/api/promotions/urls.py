from django.urls import path
from . import views

urlpatterns = [
    path("", views.PromotionListCreateView.as_view(), name="promotion-list-create"),
    path("<int:pk>/", views.PromotionDetailView.as_view(), name="promotion-detail"),
    path("active-for-products/", views.ActivePromotionsForProductsView.as_view(), name="active-promos"),
]
