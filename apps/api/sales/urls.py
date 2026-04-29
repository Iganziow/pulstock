from django.urls import path
from .views import SaleCreate, SaleList, SaleDetail, SaleVoid, TipsSummaryView, TipsListView

urlpatterns = [
    path("sales/", SaleCreate.as_view(), name="sale-create"),                    # POST
    path("sales/list/", SaleList.as_view(), name="sale-list"),                   # GET lista
    path("sales/<int:pk>/", SaleDetail.as_view(), name="sale-detail"),           # GET detalle
    path("sales/<int:pk>/void/", SaleVoid.as_view(), name="sale-void"),          # POST anular
    path("tips-summary/", TipsSummaryView.as_view(), name="tips-summary"),       # GET resumen propinas
    path("tips-list/", TipsListView.as_view(), name="tips-list"),                # GET lista detallada (tabla)
]
