# purchases/urls.py
from django.urls import path
from .views import PurchaseCreate, PurchaseList, PurchaseDetail, PurchasePost, PurchaseVoid

urlpatterns = [
    path("", PurchaseList.as_view(), name="purchase-list"),
    path("create/", PurchaseCreate.as_view(), name="purchase-create"),
    path("<int:pk>/", PurchaseDetail.as_view(), name="purchase-detail"),
    path("<int:pk>/post/", PurchasePost.as_view(), name="purchase-post"),
    path("<int:pk>/void/", PurchaseVoid.as_view(), name="purchase-void"),
]
