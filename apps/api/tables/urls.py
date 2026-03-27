from django.urls import path
from .views import (
    TableListCreate,
    TableDetail,
    OpenOrderView,
    OrderDetail,
    AddLinesView,
    DeleteLineView,
    CheckoutView,
    CancelOrderView,
    ActiveOrderByTable,
    CounterOrderView,
)

urlpatterns = [
    path("tables/",                                 TableListCreate.as_view(),   name="table-list"),
    path("tables/<int:pk>/",                        TableDetail.as_view(),       name="table-detail"),
    path("tables/<int:pk>/open/",                   OpenOrderView.as_view(),     name="table-open-order"),
    path("tables/<int:pk>/order/",                  ActiveOrderByTable.as_view(),name="table-active-order"),
    path("counter-order/",                          CounterOrderView.as_view(),  name="counter-order"),
    path("orders/<int:pk>/",                        OrderDetail.as_view(),       name="order-detail"),
    path("orders/<int:pk>/add-lines/",              AddLinesView.as_view(),      name="order-add-lines"),
    path("orders/<int:pk>/lines/<int:line_id>/",    DeleteLineView.as_view(),    name="order-delete-line"),
    path("orders/<int:pk>/checkout/",               CheckoutView.as_view(),      name="order-checkout"),
    path("orders/<int:pk>/cancel/",                CancelOrderView.as_view(),   name="order-cancel"),
]
