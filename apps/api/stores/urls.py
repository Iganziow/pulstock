from django.urls import path
from .views import StoreList, SetActiveStore

urlpatterns = [
    path("", StoreList.as_view(), name="store-list"),
    path("set-active/", SetActiveStore.as_view(), name="store-set-active"),
]