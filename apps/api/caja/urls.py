from django.urls import path
from .views import (
    RegisterListCreate,
    CurrentSessionView,
    OpenSessionView,
    SessionDetailView,
    AddMovementView,
    CloseSessionView,
    SessionHistoryView,
    CashMovementListView,
    CashMovementCategoriesView,
    CashMovementDeleteView,
)

urlpatterns = [
    path("registers/",                          RegisterListCreate.as_view(),  name="caja-register-list"),
    path("registers/<int:pk>/open/",            OpenSessionView.as_view(),     name="caja-session-open"),
    path("sessions/current/",                   CurrentSessionView.as_view(),  name="caja-session-current"),
    path("sessions/history/",                   SessionHistoryView.as_view(),  name="caja-session-history"),
    path("sessions/<int:pk>/",                  SessionDetailView.as_view(),   name="caja-session-detail"),
    path("sessions/<int:pk>/movements/",        AddMovementView.as_view(),     name="caja-session-movements"),
    path("sessions/<int:pk>/close/",            CloseSessionView.as_view(),    name="caja-session-close"),
    # Listado cross-session de movimientos (Daniel 01/05/26)
    path("movements/",                          CashMovementListView.as_view(),       name="caja-movements-list"),
    path("movements/categories/",               CashMovementCategoriesView.as_view(), name="caja-movements-categories"),
    # Eliminar movimiento (Mario 01/05/26)
    path("movements/<int:pk>/",                 CashMovementDeleteView.as_view(),     name="caja-movement-delete"),
]
