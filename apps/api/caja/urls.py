from django.urls import path
from .views import (
    RegisterListCreate,
    CurrentSessionView,
    OpenSessionView,
    SessionDetailView,
    AddMovementView,
    CloseSessionView,
    SessionHistoryView,
)

urlpatterns = [
    path("registers/",                          RegisterListCreate.as_view(),  name="caja-register-list"),
    path("registers/<int:pk>/open/",            OpenSessionView.as_view(),     name="caja-session-open"),
    path("sessions/current/",                   CurrentSessionView.as_view(),  name="caja-session-current"),
    path("sessions/history/",                   SessionHistoryView.as_view(),  name="caja-session-history"),
    path("sessions/<int:pk>/",                  SessionDetailView.as_view(),   name="caja-session-detail"),
    path("sessions/<int:pk>/movements/",        AddMovementView.as_view(),     name="caja-session-movements"),
    path("sessions/<int:pk>/close/",            CloseSessionView.as_view(),    name="caja-session-close"),
]
