"""
Fix auditoría (09/06/26): AdminUserResetPasswordView reseteaba la contraseña
de CUALQUIER user, incluido otro superusuario → escalamiento/takeover entre
admins de plataforma. Ahora rechaza (403) si el target es is_superuser.
"""
import pytest

from core.models import User
from rest_framework.test import APIClient


@pytest.fixture
def super_client(db):
    su = User.objects.create_user(username="plat_admin", password="x")
    su.is_superuser = True
    su.is_staff = True
    su.save()
    c = APIClient()
    c.force_authenticate(user=su)
    return c


@pytest.mark.django_db
class TestSuperadminResetGuard:
    def test_cannot_reset_other_superuser(self, super_client, db):
        other_su = User.objects.create_user(username="other_admin", password="x")
        other_su.is_superuser = True
        other_su.save()
        r = super_client.post(f"/api/superadmin/users/{other_su.id}/reset-password/", {}, format="json")
        assert r.status_code == 403, f"no debe poder resetear a otro superuser (got {r.status_code})"
        # La contraseña del otro superuser NO debe cambiar.
        other_su.refresh_from_db()
        assert other_su.check_password("x")

    def test_can_reset_normal_user(self, super_client, tenant, store):
        u = User.objects.create_user(username="cliente", password="oldpass")
        u.tenant = tenant
        u.role = User.Role.CASHIER
        u.save()
        r = super_client.post(f"/api/superadmin/users/{u.id}/reset-password/", {}, format="json")
        assert r.status_code == 200, r.data
        assert r.data.get("new_password")
        u.refresh_from_db()
        assert not u.check_password("oldpass"), "la pass del cliente debió cambiar"
