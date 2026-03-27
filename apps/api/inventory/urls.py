from django.urls import path
from .views import (
    StockAdjust, StockList, StockMoveList, StockReceive, StockIssue,
    StockTransferCreate, KardexView, StockTransferDetail,StockTransferList,KardexReportView
)

urlpatterns = [
    path("adjust/", StockAdjust.as_view(), name="stock-adjust"),
    path("receive/", StockReceive.as_view(), name="stock-receive"),
    path("issue/", StockIssue.as_view(), name="stock-issue"),
    path("stock/", StockList.as_view(), name="stock-list"),
    path("moves/", StockMoveList.as_view(), name="stock-moves"),

    path("transfer/", StockTransferCreate.as_view(), name="stock-transfer"),
    path("kardex/report/", KardexReportView.as_view(), name="inventory-kardex-report"),
    path("kardex/", KardexView.as_view(), name="inventory-kardex"),
    path("transfers/", StockTransferList.as_view(), name="stock-transfer-list"),
    path("transfers/<int:pk>/", StockTransferDetail.as_view(), name="stock-transfer-detail"),
    
]
