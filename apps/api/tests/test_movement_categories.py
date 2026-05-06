"""
Tests del CRUD de MovementCategory (Daniel 01/05/26).

Cubre:
- GET listado (activas / incluyendo inactivas)
- POST crear (validaciones, slug auto, conflicto de code)
- PATCH editar (label, type, icon, color, order, is_active)
- DELETE soft delete (no afecta movimientos viejos)
- Multi-tenant isolation
- Auto-seed para Tenant nuevo (signal)
- Backfill de movimientos existentes
- Backward compat: movs viejos con `category` string siguen funcionando
"""
import pytest
from decimal import Decimal

from caja.models import (
    CashRegister, CashSession, CashMovement, MovementCategory,
)
from core.models import User, Tenant
from stores.models import Store


pytestmark = pytest.mark.django_db


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def register_fx(tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja A")


@pytest.fixture
def open_session_fx(register_fx, owner, tenant, store):
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register_fx,
        opened_by=owner, initial_amount=Decimal("10000"), status="OPEN",
    )


# ─── 1. Auto-seed via signal (Tenant nuevo) ────────────────────

class TestAutoSeedDefaultCategories:

    def test_new_tenant_gets_default_categories(self):
        """Cuando se crea un Tenant, el signal popula 11 categorías default
        (7 OUT + 4 IN). La cantidad cambió cuando agregamos TIP_WITHDRAW
        (Mario 06/05/26 — para registrar retiros de propinas)."""
        t = Tenant.objects.create(slug="autoseed-test", name="Test Auto")
        cats = MovementCategory.objects.filter(tenant=t)
        assert cats.count() == 11
        # 7 OUT + 4 IN
        assert cats.filter(type="OUT").count() == 7
        assert cats.filter(type="IN").count() == 4
        # Todas marcadas como template
        assert cats.filter(is_default_template=True).count() == 11
        # Códigos esperados
        codes = set(cats.values_list("code", flat=True))
        assert "SUPPLIER" in codes
        assert "SALARY" in codes
        assert "CAPITAL" in codes
        assert "TIP_WITHDRAW" in codes  # nuevo: retiro de propinas


# ─── 2. GET /caja/categories/ ──────────────────────────────────

class TestListCategories:

    def test_list_returns_only_active_by_default(self, api_client, owner, tenant):
        # Marbrava ya tiene 11 default por seed (incluyendo TIP_WITHDRAW)
        # Desactivar 1
        cat = MovementCategory.objects.filter(tenant=tenant, code="LOAN").first()
        cat.is_active = False
        cat.save()

        r = api_client.get("/api/caja/categories/")
        assert r.status_code == 200
        ids = {c["id"] for c in r.data["results"]}
        assert cat.id not in ids  # NO debe aparecer

    def test_list_with_include_inactive(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="LOAN").first()
        cat.is_active = False
        cat.save()

        r = api_client.get("/api/caja/categories/?include_inactive=1")
        assert r.status_code == 200
        ids = {c["id"] for c in r.data["results"]}
        assert cat.id in ids


# ─── 3. POST /caja/categories/ (crear) ─────────────────────────

class TestCreateCategory:

    def test_create_basic(self, api_client, owner, tenant):
        r = api_client.post("/api/caja/categories/", {
            "label": "Pago a Coca Cola",
            "type": "OUT",
        }, format="json")
        assert r.status_code == 201, r.data
        assert r.data["label"] == "Pago a Coca Cola"
        assert r.data["type"] == "OUT"
        assert r.data["is_default_template"] is False
        assert r.data["is_active"] is True

    def test_create_with_icon_color(self, api_client, owner, tenant):
        r = api_client.post("/api/caja/categories/", {
            "label": "Marketing",
            "type": "OUT",
            "icon": "📢",
            "color": "#FF0066",
        }, format="json")
        assert r.status_code == 201
        assert r.data["icon"] == "📢"
        assert r.data["color"] == "#FF0066"

    def test_auto_slug_from_label(self, api_client, owner, tenant):
        r = api_client.post("/api/caja/categories/", {
            "label": "Marketing Digital",
            "type": "OUT",
        }, format="json")
        assert r.status_code == 201
        # slugify("Marketing Digital") = "marketing-digital", luego upper + replace -
        assert r.data["code"] == "MARKETING_DIGITAL"

    def test_code_conflict_appends_suffix(self, api_client, owner, tenant):
        # Crear "Otro" varias veces — primero queda como OTRO, luego OTRO_2, OTRO_3
        r1 = api_client.post("/api/caja/categories/", {"label": "Otro", "type": "OUT"}, format="json")
        r2 = api_client.post("/api/caja/categories/", {"label": "Otro", "type": "OUT"}, format="json")
        assert r1.data["code"] != r2.data["code"]
        assert r2.data["code"].startswith("OTRO")

    def test_label_required(self, api_client, owner, tenant):
        r = api_client.post("/api/caja/categories/", {"type": "OUT"}, format="json")
        assert r.status_code == 400

    def test_invalid_type(self, api_client, owner, tenant):
        r = api_client.post("/api/caja/categories/", {"label": "X", "type": "ALIEN"}, format="json")
        assert r.status_code == 400


# ─── 4. PATCH /caja/categories/<id>/ (editar) ──────────────────

class TestUpdateCategory:

    def test_update_label(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="SUPPLIER").first()
        r = api_client.patch(f"/api/caja/categories/{cat.id}/", {"label": "Pago a CocaCola SA"}, format="json")
        assert r.status_code == 200
        assert r.data["label"] == "Pago a CocaCola SA"
        cat.refresh_from_db()
        assert cat.label == "Pago a CocaCola SA"

    def test_update_icon_color_order(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="SALARY").first()
        r = api_client.patch(f"/api/caja/categories/{cat.id}/",
                              {"icon": "💼", "color": "#3344FF", "order": 99}, format="json")
        assert r.status_code == 200
        assert r.data["icon"] == "💼"
        assert r.data["color"] == "#3344FF"
        assert r.data["order"] == 99

    def test_update_invalid_label_empty(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="SUPPLIER").first()
        r = api_client.patch(f"/api/caja/categories/{cat.id}/", {"label": ""}, format="json")
        assert r.status_code == 400

    def test_toggle_is_active(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="LOAN").first()
        r = api_client.patch(f"/api/caja/categories/{cat.id}/", {"is_active": False}, format="json")
        assert r.status_code == 200
        cat.refresh_from_db()
        assert cat.is_active is False
        # Reactivar
        r2 = api_client.patch(f"/api/caja/categories/{cat.id}/", {"is_active": True}, format="json")
        cat.refresh_from_db()
        assert cat.is_active is True


# ─── 5. DELETE soft (preserva historia) ─────────────────────────

class TestDeleteCategory:

    def test_delete_soft_disables_category(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="OWNER_DRAW").first()
        r = api_client.delete(f"/api/caja/categories/{cat.id}/")
        assert r.status_code == 200
        cat.refresh_from_db()
        assert cat.is_active is False
        # NO se borró de la BD (soft delete)
        assert MovementCategory.objects.filter(id=cat.id).exists()

    def test_delete_does_not_affect_existing_movements(
        self, api_client, owner, tenant, store, register_fx, open_session_fx,
    ):
        """CRÍTICO: borrar (soft) categoría NO debe afectar movimientos
        que la usan — siguen mostrando el label histórico."""
        cat = MovementCategory.objects.filter(tenant=tenant, code="SUPPLIER").first()

        # Crear movimiento usando esa categoría
        mov = CashMovement.objects.create(
            tenant=tenant, session=open_session_fx, type="OUT",
            category="SUPPLIER", category_fk=cat,
            amount=Decimal("5000"), description="Pago test",
            created_by=owner,
        )
        # Soft delete categoría
        api_client.delete(f"/api/caja/categories/{cat.id}/")

        # El movimiento sigue existiendo y referencia la cat (FK preservada)
        mov.refresh_from_db()
        assert mov.category_fk_id == cat.id

        # En el listado de movimientos, sigue apareciendo con su label
        r = api_client.get("/api/caja/movements/")
        ids = [m["id"] for m in r.data["results"]]
        assert mov.id in ids
        for m in r.data["results"]:
            if m["id"] == mov.id:
                assert m["category_label"] == "Pago a proveedor"  # label histórico

    def test_delete_already_inactive_returns_200(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="LOAN").first()
        cat.is_active = False
        cat.save()
        r = api_client.delete(f"/api/caja/categories/{cat.id}/")
        assert r.status_code == 200


# ─── 6. Multi-tenant isolation ──────────────────────────────────

class TestMultiTenantIsolation:

    def test_cannot_see_other_tenant_categories(self, api_client, owner, tenant):
        # Crear otro tenant + cat
        other = Tenant.objects.create(slug="other-cat", name="Other")
        other_cat = MovementCategory.objects.filter(tenant=other).first()
        # debe haber categorías default ya creadas por signal
        assert other_cat is not None

        # Owner del tenant 1 lista
        r = api_client.get("/api/caja/categories/")
        ids = {c["id"] for c in r.data["results"]}
        assert other_cat.id not in ids

    def test_cannot_edit_other_tenant_category(self, api_client, owner):
        other = Tenant.objects.create(slug="other-edit", name="Other")
        other_cat = MovementCategory.objects.filter(tenant=other).first()
        r = api_client.patch(f"/api/caja/categories/{other_cat.id}/", {"label": "HACK"}, format="json")
        assert r.status_code == 404

    def test_cannot_delete_other_tenant_category(self, api_client, owner):
        other = Tenant.objects.create(slug="other-del-cat", name="Other")
        other_cat = MovementCategory.objects.filter(tenant=other).first()
        r = api_client.delete(f"/api/caja/categories/{other_cat.id}/")
        assert r.status_code == 404
        other_cat.refresh_from_db()
        assert other_cat.is_active is True  # no se desactivó


# ─── 7. Backward compat: AddMovement con category_id ────────────

class TestAddMovementWithFK:

    def test_create_movement_with_category_id(
        self, api_client, owner, tenant, store, register_fx, open_session_fx,
    ):
        cat = MovementCategory.objects.filter(tenant=tenant, code="SUPPLIER").first()
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category_id": cat.id, "amount": "5000", "description": "Pago test"},
            format="json",
        )
        assert r.status_code == 201, r.data
        assert r.data["category_id"] == cat.id
        assert r.data["category_label"] == "Pago a proveedor"
        # category string también sincronizado para compat
        m = CashMovement.objects.get(id=r.data["id"])
        assert m.category == "SUPPLIER"
        assert m.category_fk_id == cat.id

    def test_create_with_legacy_category_string_still_works(
        self, api_client, owner, tenant, store, register_fx, open_session_fx,
    ):
        # Frontend viejo manda "category" string — debe seguir funcionando
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category": "SALARY", "amount": "3000", "description": "Sueldo"},
            format="json",
        )
        assert r.status_code == 201, r.data
        # Y debería linkear automáticamente al FK (porque existe categoría con code=SALARY)
        m = CashMovement.objects.get(id=r.data["id"])
        assert m.category == "SALARY"
        assert m.category_fk_id is not None  # auto-linked

    def test_create_with_invalid_category_id_returns_400(
        self, api_client, owner, tenant, store, register_fx, open_session_fx,
    ):
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category_id": 99999, "amount": "100", "description": "x"},
            format="json",
        )
        assert r.status_code == 400

    def test_create_with_inactive_category_id_returns_400(
        self, api_client, owner, tenant, store, register_fx, open_session_fx,
    ):
        cat = MovementCategory.objects.filter(tenant=tenant, code="LOAN").first()
        cat.is_active = False
        cat.save()
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category_id": cat.id, "amount": "100", "description": "x"},
            format="json",
        )
        assert r.status_code == 400


# ─── 8. Endpoint /caja/movements/categories/ (frontend dropdown) ─

class TestCategoriesEndpointGroupsByType:

    def test_returns_active_grouped_income_expense(self, api_client, owner, tenant):
        r = api_client.get("/api/caja/movements/categories/")
        assert r.status_code == 200
        income_codes = {c["code"] for c in r.data["income"]}
        expense_codes = {c["code"] for c in r.data["expense"]}
        assert "CAPITAL" in income_codes
        assert "SUPPLIER" in expense_codes

    def test_inactive_categories_not_shown(self, api_client, owner, tenant):
        cat = MovementCategory.objects.filter(tenant=tenant, code="REFUND").first()
        cat.is_active = False
        cat.save()
        r = api_client.get("/api/caja/movements/categories/")
        expense_codes = {c["code"] for c in r.data["expense"]}
        assert "REFUND" not in expense_codes
