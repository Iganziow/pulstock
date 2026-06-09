"""
Fix (09/06/26): last_login no se actualizaba con login JWT → la lista de
usuarios mostraba "Nunca accedió" para todos, aunque entraran a diario.
- UPDATE_LAST_LOGIN=True → login actualiza last_login.
- CookieTokenRefreshView actualiza last_login en cada refresh (uso activo).
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_login_actualiza_last_login(owner):
    owner.last_login = None
    owner.save(update_fields=["last_login"])

    c = APIClient()
    r = c.post("/api/auth/token/", {"username": "owner_test", "password": "testpass123"}, format="json")
    assert r.status_code == 200, r.content

    owner.refresh_from_db()
    assert owner.last_login is not None, "el login JWT debe actualizar last_login"


@pytest.mark.django_db
def test_refresh_actualiza_last_login(owner):
    c = APIClient()
    r = c.post("/api/auth/token/", {"username": "owner_test", "password": "testpass123"}, format="json")
    assert r.status_code == 200, r.content

    # Atrasar last_login para verificar que el refresh lo adelanta.
    old = timezone.now() - timedelta(days=3)
    type(owner).objects.filter(id=owner.id).update(last_login=old)

    r2 = c.post("/api/auth/token/refresh/", {}, format="json")
    assert r2.status_code == 200, r2.content

    owner.refresh_from_db()
    assert owner.last_login > old, "el refresh debe actualizar last_login (uso activo)"
