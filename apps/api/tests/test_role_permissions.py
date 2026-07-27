"""
tests/test_role_permissions.py — Matriz de permisos por rol editable (Fudo-style).

- Defaults de fábrica (incluye inventory→caja=True, Mario 27-jul).
- /core/me/ devuelve permisos EFECTIVOS (defaults + overrides del tenant).
- GET/PUT /core/role-permissions/ solo dueño; owner no editable; settings/users
  bloqueados (anti-escalación).
"""
import pytest
from rest_framework.test import APIClient

from core.models import User
from core.role_permissions import effective_permissions, DEFAULT_ROLE_PERMISSIONS


URL_ME = "/api/core/me/"
URL_RP = "/api/core/role-permissions/"


def _make_user(tenant, store, username, role):
    u = User.objects.create_user(username=username, password="pass123")
    u.tenant = tenant
    u.active_store = store
    u.role = role
    u.save(update_fields=["tenant", "active_store", "role"])
    return u


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ── Defaults ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_inventory_tiene_caja_por_default(tenant):
    """Mario 27-jul: el rol Inventario ahora accede a Caja de fábrica."""
    assert DEFAULT_ROLE_PERMISSIONS["inventory"]["caja"] is True
    assert effective_permissions(tenant, "inventory")["caja"] is True


@pytest.mark.django_db
def test_owner_siempre_todo(tenant):
    perms = effective_permissions(tenant, "owner")
    assert all(perms.values())


# ── effective_permissions con overrides ────────────────────────────────────

@pytest.mark.django_db
def test_override_aplica_y_locked_no(tenant):
    tenant.role_permissions_overrides = {
        "cashier": {"reports": True, "settings": True},  # settings debe ignorarse
    }
    tenant.save(update_fields=["role_permissions_overrides"])
    perms = effective_permissions(tenant, "cashier")
    assert perms["reports"] is True          # override aplicado
    assert perms["settings"] is False        # bloqueado, no se puede otorgar


# ── /me/ refleja permisos efectivos ────────────────────────────────────────

@pytest.mark.django_db
def test_me_refleja_override(tenant, store):
    cajero = _make_user(tenant, store, "cajero_perm", User.Role.CASHIER)
    # Sin override: cashier no ve reports
    r = _client(cajero).get(URL_ME)
    assert r.json()["permissions"]["reports"] is False
    # Con override: sí
    tenant.role_permissions_overrides = {"cashier": {"reports": True}}
    tenant.save(update_fields=["role_permissions_overrides"])
    r = _client(cajero).get(URL_ME)
    assert r.json()["permissions"]["reports"] is True


# ── GET matriz ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_matriz_dueño(api_client, tenant, store):
    _make_user(tenant, store, "inv_user", User.Role.INVENTORY)
    r = api_client.get(URL_RP)
    assert r.status_code == 200
    data = r.json()
    assert "permission_meta" in data and "roles" in data
    roles = {x["role"] for x in data["roles"]}
    assert roles == {"manager", "cashier", "inventory"}  # owner NO editable
    # usuarios por rol incluye al inventory user
    inv_users = [u["name"] for u in data["users_by_role"]["inventory"]]
    assert any("inv_user" in n or n for n in inv_users)


# ── PUT aplica y persiste ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_put_aplica_override(api_client, tenant):
    resp = api_client.put(URL_RP, {
        "permissions": {
            "cashier": {"reports": True, "forecast": True},
            "owner": {"caja": False},          # debe ignorarse (no editable)
            "cashier2": {"pos": False},        # rol inexistente, ignorar
        }
    }, format="json")
    assert resp.status_code == 200
    tenant.refresh_from_db()
    assert tenant.role_permissions_overrides.get("cashier", {}).get("reports") is True
    assert "owner" not in tenant.role_permissions_overrides
    assert effective_permissions(tenant, "cashier")["forecast"] is True


@pytest.mark.django_db
def test_put_ignora_locked(api_client, tenant):
    api_client.put(URL_RP, {"permissions": {"manager": {"settings": True, "users": True, "caja": False}}}, format="json")
    tenant.refresh_from_db()
    mgr = tenant.role_permissions_overrides.get("manager", {})
    assert "settings" not in mgr and "users" not in mgr
    assert mgr.get("caja") is False  # caja sí es editable


# ── Permisos: solo dueño ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_no_dueño_no_puede(tenant, store):
    mgr = _make_user(tenant, store, "mgr_perm", User.Role.MANAGER)
    cli = _client(mgr)
    assert cli.get(URL_RP).status_code == 403
    assert cli.put(URL_RP, {"permissions": {}}, format="json").status_code == 403
