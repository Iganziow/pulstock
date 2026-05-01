"""Tests del listado y categorías de CashMovement (Daniel 01/05/26)."""
import pytest
from decimal import Decimal
from datetime import timedelta

from caja.models import CashRegister, CashSession, CashMovement
from django.utils import timezone


pytestmark = pytest.mark.django_db


@pytest.fixture
def register(tenant, store):
    return CashRegister.objects.create(tenant=tenant, store=store, name="Caja A")


@pytest.fixture
def open_session_fx(register, owner, tenant, store):
    return CashSession.objects.create(
        tenant=tenant, store=store, register=register,
        opened_by=owner, initial_amount=Decimal("10000"), status="OPEN",
    )


class TestAddMovementWithCategory:
    """POST /caja/sessions/{id}/movements/ con categoría."""

    def test_add_movement_with_supplier_category(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {
                "type": "OUT",
                "category": "SUPPLIER",
                "amount": "5000",
                "description": "Pago carne",
            },
            format="json",
        )
        assert r.status_code == 201, r.data
        assert r.data["category"] == "SUPPLIER"
        assert r.data["category_label"] == "Pago a proveedor"

        # Verificar en DB
        m = CashMovement.objects.get(id=r.data["id"])
        assert m.category == "SUPPLIER"

    def test_add_movement_without_category_defaults_empty(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "amount": "1000", "description": "Sin categoría"},
            format="json",
        )
        assert r.status_code == 201
        assert r.data["category"] == ""
        assert r.data["category_label"] == "Sin categoría"

    def test_invalid_category_rejected(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        r = api_client.post(
            f"/api/caja/sessions/{open_session_fx.id}/movements/",
            {"type": "OUT", "category": "ALIENS", "amount": "100", "description": "x"},
            format="json",
        )
        assert r.status_code == 400


class TestCashMovementListView:
    """GET /caja/movements/ — listado paginado con filtros."""

    def _create(self, session, type_, category, amount, owner, tenant):
        return CashMovement.objects.create(
            tenant=tenant, session=session, type=type_, category=category,
            amount=Decimal(str(amount)), description=f"{category} {amount}",
            created_by=owner,
        )

    def test_list_returns_recent_movements(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        self._create(open_session_fx, "OUT", "SUPPLIER", "5000", owner, tenant)
        self._create(open_session_fx, "IN", "CAPITAL", "10000", owner, tenant)
        self._create(open_session_fx, "OUT", "SALARY", "3000", owner, tenant)

        r = api_client.get("/api/caja/movements/")
        assert r.status_code == 200
        assert r.data["count"] == 3
        assert len(r.data["results"]) == 3

    def test_filter_by_type(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        self._create(open_session_fx, "OUT", "SUPPLIER", "5000", owner, tenant)
        self._create(open_session_fx, "IN", "CAPITAL", "10000", owner, tenant)

        r = api_client.get("/api/caja/movements/?type=OUT")
        assert r.status_code == 200
        assert r.data["count"] == 1
        assert r.data["results"][0]["type"] == "OUT"

    def test_filter_by_category(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        self._create(open_session_fx, "OUT", "SUPPLIER", "5000", owner, tenant)
        self._create(open_session_fx, "OUT", "SALARY", "3000", owner, tenant)

        r = api_client.get("/api/caja/movements/?category=SUPPLIER")
        assert r.status_code == 200
        assert r.data["count"] == 1
        assert r.data["results"][0]["category"] == "SUPPLIER"

    def test_search_by_description(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        CashMovement.objects.create(
            tenant=tenant, session=open_session_fx, type="OUT",
            amount=Decimal("1000"), description="Pago a Coca Cola",
            created_by=owner,
        )
        CashMovement.objects.create(
            tenant=tenant, session=open_session_fx, type="OUT",
            amount=Decimal("500"), description="Carne premium",
            created_by=owner,
        )

        r = api_client.get("/api/caja/movements/?q=coca")
        assert r.status_code == 200
        assert r.data["count"] == 1

    def test_totals_by_type(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        self._create(open_session_fx, "OUT", "SUPPLIER", "5000", owner, tenant)
        self._create(open_session_fx, "OUT", "SALARY", "3000", owner, tenant)
        self._create(open_session_fx, "IN", "CAPITAL", "10000", owner, tenant)

        r = api_client.get("/api/caja/movements/")
        totals = r.data["totals_by_type"]
        assert Decimal(totals["in"]) == Decimal("10000")
        assert Decimal(totals["out"]) == Decimal("8000")
        assert Decimal(totals["net"]) == Decimal("2000")
        assert totals["count"] == 3

    def test_totals_by_category(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        self._create(open_session_fx, "OUT", "SUPPLIER", "5000", owner, tenant)
        self._create(open_session_fx, "OUT", "SUPPLIER", "3000", owner, tenant)
        self._create(open_session_fx, "OUT", "SALARY", "1500", owner, tenant)

        r = api_client.get("/api/caja/movements/")
        cats = r.data["totals_by_category"]
        # Find SUPPLIER row
        supplier_row = next((c for c in cats if c["category"] == "SUPPLIER"), None)
        assert supplier_row is not None
        assert Decimal(supplier_row["total"]) == Decimal("8000")
        assert supplier_row["count"] == 2

    def test_pagination(
        self, api_client, owner, tenant, store, register, open_session_fx,
    ):
        for i in range(5):
            self._create(open_session_fx, "OUT", "SUPPLIER", str(100 + i), owner, tenant)

        r = api_client.get("/api/caja/movements/?page_size=2&page=1")
        assert r.status_code == 200
        assert r.data["count"] == 5
        assert r.data["page_size"] == 2
        assert r.data["total_pages"] == 3
        assert len(r.data["results"]) == 2

    def test_multitenant_isolation(
        self, api_client, owner, tenant, store, register, open_session_fx,
        django_user_model,
    ):
        """Movements de otro tenant NO deben aparecer."""
        from core.models import Tenant
        from stores.models import Store

        other_tenant = Tenant.objects.create(slug="other-mvt", name="Other")
        other_store = Store.objects.create(tenant=other_tenant, code="o1", name="OS")
        other_register = CashRegister.objects.create(tenant=other_tenant, store=other_store, name="OR")
        other_session = CashSession.objects.create(
            tenant=other_tenant, store=other_store, register=other_register,
            opened_by=owner, initial_amount=Decimal("0"), status="OPEN",
        )
        # Movement en el tenant ajeno
        CashMovement.objects.create(
            tenant=other_tenant, session=other_session, type="OUT",
            amount=Decimal("9999"), description="OTRO TENANT — no debe verse",
            created_by=owner,
        )
        # Movement propio
        self._create(open_session_fx, "OUT", "SUPPLIER", "100", owner, tenant)

        r = api_client.get("/api/caja/movements/")
        assert r.data["count"] == 1
        assert r.data["results"][0]["amount"] == "100.00"


class TestCashMovementCategoriesView:
    """GET /caja/movements/categories/."""

    def test_returns_grouped_categories(self, api_client, owner):
        r = api_client.get("/api/caja/movements/categories/")
        assert r.status_code == 200
        assert "income" in r.data
        assert "expense" in r.data
        # Algunas categorías esperadas
        income_codes = {c["code"] for c in r.data["income"]}
        expense_codes = {c["code"] for c in r.data["expense"]}
        assert "CAPITAL" in income_codes
        assert "SUPPLIER" in expense_codes
        assert "SALARY" in expense_codes
