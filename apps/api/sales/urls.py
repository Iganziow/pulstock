from django.urls import path
from .views import (
    SaleCreate, SaleList, SaleDetail, SaleVoid,
    TipsSummaryView, TipsListView,
    SaleEditPayments, SaleEditTip,
)

urlpatterns = [
    path("sales/", SaleCreate.as_view(), name="sale-create"),                    # POST
    path("sales/list/", SaleList.as_view(), name="sale-list"),                   # GET lista
    path("sales/<int:pk>/", SaleDetail.as_view(), name="sale-detail"),           # GET detalle
    path("sales/<int:pk>/void/", SaleVoid.as_view(), name="sale-void"),          # POST anular
    # Edición post-cierre (manager/owner). NO incluye qty: corregir
    # cantidades requiere anular la venta y crear una nueva (anti-fraude).
    path("sales/<int:pk>/payments/", SaleEditPayments.as_view(), name="sale-edit-payments"),
    path("sales/<int:pk>/tip/", SaleEditTip.as_view(), name="sale-edit-tip"),
    path("tips-summary/", TipsSummaryView.as_view(), name="tips-summary"),       # GET resumen propinas
    path("tips-list/", TipsListView.as_view(), name="tips-list"),                # GET lista detallada (tabla)
]
