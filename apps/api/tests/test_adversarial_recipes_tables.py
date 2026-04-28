"""
Adversarial tests for Recipes, Products, and Tables.
Intentionally misuses the API to verify robustness.
"""
import pytest
from decimal import Decimal
from django.utils import timezone

from rest_framework.test import APIClient
from core.models import Tenant, User, Warehouse
from stores.models import Store
from catalog.models import Product, Recipe, RecipeLine


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Adversarial Test", slug="adversarial-test")


@pytest.fixture
def store(tenant):
    return Store.objects.create(tenant=tenant, name="Test Store")


@pytest.fixture
def warehouse(tenant, store):
    return Warehouse.objects.create(tenant=tenant, store=store, name="Bodega Test")


@pytest.fixture
def owner(tenant, store):
    user = User.objects.create_user(
        username="adv_owner", password="test123",
        tenant=tenant, active_store=store, role="owner",
    )
    return user


@pytest.fixture
def client(owner):
    c = APIClient()
    c.force_authenticate(user=owner)
    return c


@pytest.fixture
def product_a(tenant):
    return Product.objects.create(tenant=tenant, name="Hamburguesa", price=Decimal("5990"))


@pytest.fixture
def product_b(tenant):
    return Product.objects.create(tenant=tenant, name="Pan", price=Decimal("500"))


@pytest.fixture
def product_c(tenant):
    return Product.objects.create(tenant=tenant, name="Carne", price=Decimal("3000"))


@pytest.fixture
def other_tenant(db):
    return Tenant.objects.create(name="Other", slug="other-adv")


@pytest.fixture
def other_product(other_tenant):
    return Product.objects.create(tenant=other_tenant, name="Alien", price=Decimal("999"))


# ══════════════════════════════════════════════════════════════
# RECIPES — ADVERSARIAL TESTS
# ══════════════════════════════════════════════════════════════

class TestRecipeAdversarial:
    URL = "/api/catalog/products/{}/recipe/"

    def test_self_reference_rejected(self, client, product_a):
        """Producto no puede ser ingrediente de sí mismo."""
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_a.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 400
        assert "propia receta" in r.json()["detail"].lower()

    def test_circular_dependency_a_uses_b_then_b_uses_a(self, client, product_a, product_b):
        """A usa B como ingrediente. Luego B intenta usar A → ciclo."""
        # A -> B (ok)
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "2"}],
        }, format="json")
        assert r.status_code == 200

        # B -> A (debe fallar: ciclo)
        r2 = client.post(self.URL.format(product_b.id), {
            "lines": [{"ingredient_id": product_a.id, "qty": "1"}],
        }, format="json")
        assert r2.status_code == 400
        assert "circular" in r2.json()["detail"].lower()

    def test_transitive_cycle_a_b_c_a(self, client, product_a, product_b, product_c):
        """A→B, B→C, luego C→A → ciclo transitivo."""
        client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "1"}],
        }, format="json")
        client.post(self.URL.format(product_b.id), {
            "lines": [{"ingredient_id": product_c.id, "qty": "1"}],
        }, format="json")

        r = client.post(self.URL.format(product_c.id), {
            "lines": [{"ingredient_id": product_a.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 400
        assert "circular" in r.json()["detail"].lower()

    def test_zero_qty_rejected(self, client, product_a, product_b):
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "0"}],
        }, format="json")
        assert r.status_code == 400

    def test_negative_qty_rejected(self, client, product_a, product_b):
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "-5"}],
        }, format="json")
        assert r.status_code == 400

    def test_empty_lines_rejected(self, client, product_a):
        r = client.post(self.URL.format(product_a.id), {
            "lines": [],
        }, format="json")
        assert r.status_code == 400

    def test_duplicate_ingredient_rejected(self, client, product_a, product_b):
        r = client.post(self.URL.format(product_a.id), {
            "lines": [
                {"ingredient_id": product_b.id, "qty": "1"},
                {"ingredient_id": product_b.id, "qty": "2"},
            ],
        }, format="json")
        assert r.status_code == 400

    def test_other_tenant_ingredient_rejected(self, client, product_a, other_product):
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": other_product.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 400

    def test_nonexistent_product_recipe(self, client):
        r = client.post(self.URL.format(99999), {
            "lines": [{"ingredient_id": 1, "qty": "1"}],
        }, format="json")
        assert r.status_code == 404

    def test_inactive_ingredient_rejected(self, client, product_a, product_b):
        product_b.is_active = False
        product_b.save()
        r = client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "1"}],
        }, format="json")
        assert r.status_code == 400

    def test_delete_recipe(self, client, product_a, product_b):
        client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "1"}],
        }, format="json")
        r = client.delete(self.URL.format(product_a.id))
        assert r.status_code == 204

    def test_delete_nonexistent_recipe(self, client, product_a):
        r = client.delete(self.URL.format(product_a.id))
        assert r.status_code == 404

    def test_get_recipe(self, client, product_a, product_b):
        client.post(self.URL.format(product_a.id), {
            "lines": [{"ingredient_id": product_b.id, "qty": "2.5"}],
        }, format="json")
        r = client.get(self.URL.format(product_a.id))
        assert r.status_code == 200
        assert len(r.json()["lines"]) == 1
        assert Decimal(r.json()["lines"][0]["qty"]) == Decimal("2.5000")


# ══════════════════════════════════════════════════════════════
# TABLES — ADVERSARIAL TESTS
# ══════════════════════════════════════════════════════════════

class TestTableAdversarial:
    URL_TABLES = "/api/tables/tables/"

    def test_create_table_empty_name(self, client):
        r = client.post(self.URL_TABLES, {"name": ""}, format="json")
        assert r.status_code == 400

    def test_create_table_whitespace_name(self, client):
        r = client.post(self.URL_TABLES, {"name": "   "}, format="json")
        assert r.status_code == 400

    def test_create_table_capacity_zero(self, client):
        """Capacity 0 should be clamped to 1."""
        r = client.post(self.URL_TABLES, {"name": "Mesa Zero", "capacity": 0}, format="json")
        assert r.status_code == 201
        assert r.json()["capacity"] >= 1

    def test_create_table_capacity_negative(self, client):
        """Capacity -5 should be clamped to 1."""
        r = client.post(self.URL_TABLES, {"name": "Mesa Neg", "capacity": -5}, format="json")
        assert r.status_code == 201
        assert r.json()["capacity"] >= 1

    def test_patch_name_empty(self, client):
        r = client.post(self.URL_TABLES, {"name": "Mesa Patch"}, format="json")
        table_id = r.json()["id"]
        r2 = client.patch(f"{self.URL_TABLES}{table_id}/", {"name": ""}, format="json")
        assert r2.status_code == 400

    def test_patch_capacity_zero(self, client):
        r = client.post(self.URL_TABLES, {"name": "Mesa Cap"}, format="json")
        table_id = r.json()["id"]
        r2 = client.patch(f"{self.URL_TABLES}{table_id}/", {"capacity": 0}, format="json")
        assert r2.status_code == 400

    def test_patch_capacity_negative(self, client):
        r = client.post(self.URL_TABLES, {"name": "Mesa Neg2"}, format="json")
        table_id = r.json()["id"]
        r2 = client.patch(f"{self.URL_TABLES}{table_id}/", {"capacity": -3}, format="json")
        assert r2.status_code == 400

    def test_patch_capacity_text(self, client):
        r = client.post(self.URL_TABLES, {"name": "Mesa Text"}, format="json")
        table_id = r.json()["id"]
        r2 = client.patch(f"{self.URL_TABLES}{table_id}/", {"capacity": "abc"}, format="json")
        assert r2.status_code == 400

    def test_duplicate_table_name(self, client):
        client.post(self.URL_TABLES, {"name": "Unique"}, format="json")
        r2 = client.post(self.URL_TABLES, {"name": "Unique"}, format="json")
        assert r2.status_code == 409 or r2.status_code == 400


# ══════════════════════════════════════════════════════════════
# ORDER LINES — ADVERSARIAL TESTS
# ══════════════════════════════════════════════════════════════

class TestAddLinesAdversarial:
    def _open_order(self, client, warehouse):
        r = client.post("/api/tables/tables/", {"name": f"M-{timezone.now().timestamp()}"}, format="json")
        tid = r.json()["id"]
        r2 = client.post(f"/api/tables/tables/{tid}/open/", {"warehouse_id": warehouse.id}, format="json")
        return r2.json()["id"]

    def test_add_line_negative_price(self, client, warehouse, product_a):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": product_a.id, "qty": 1, "unit_price": "-500"}]
        }, format="json")
        assert r.status_code == 400
        assert "negativo" in r.json()["detail"].lower()

    def test_add_line_zero_qty(self, client, warehouse, product_a):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": product_a.id, "qty": 0}]
        }, format="json")
        assert r.status_code == 400

    def test_add_line_negative_qty(self, client, warehouse, product_a):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": product_a.id, "qty": -3}]
        }, format="json")
        assert r.status_code == 400

    def test_add_line_empty_lines(self, client, warehouse):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": []
        }, format="json")
        assert r.status_code == 400

    def test_add_line_nonexistent_product(self, client, warehouse):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": 99999, "qty": 1}]
        }, format="json")
        assert r.status_code == 400

    def test_add_line_other_tenant_product(self, client, warehouse, other_product):
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": other_product.id, "qty": 1}]
        }, format="json")
        assert r.status_code == 400

    def test_add_line_inactive_product(self, client, warehouse, product_a):
        product_a.is_active = False
        product_a.save()
        oid = self._open_order(client, warehouse)
        r = client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": product_a.id, "qty": 1}]
        }, format="json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
# CHECKOUT — ADVERSARIAL TESTS
# ══════════════════════════════════════════════════════════════

class TestCheckoutAdversarial:
    def _create_order_with_line(self, client, warehouse, product):
        r = client.post("/api/tables/tables/", {"name": f"Chk-{timezone.now().timestamp()}"}, format="json")
        tid = r.json()["id"]
        client.post(f"/api/tables/tables/{tid}/open/", {"warehouse_id": warehouse.id}, format="json")
        order_r = client.get(f"/api/tables/tables/{tid}/order/")
        oid = order_r.json()["id"]
        client.post(f"/api/tables/orders/{oid}/add-lines/", {
            "lines": [{"product_id": product.id, "qty": 1}]
        }, format="json")
        return oid

    def test_checkout_negative_tip_clamped_to_zero(self, client, warehouse, product_a):
        from inventory.models import StockItem
        StockItem.objects.get_or_create(
            tenant=product_a.tenant, product=product_a, warehouse=warehouse,
            defaults={"on_hand": Decimal("100"), "avg_cost": Decimal("1000")},
        )
        oid = self._create_order_with_line(client, warehouse, product_a)
        r = client.post(f"/api/tables/orders/{oid}/checkout/", {
            "mode": "all",
            "tip": "-1000",
            "payments": [{"method": "cash", "amount": "5990"}],
        }, format="json")
        # Should succeed with tip clamped to 0
        assert r.status_code == 200 or r.status_code == 201

    def test_checkout_invalid_mode(self, client, warehouse, product_a):
        from inventory.models import StockItem
        StockItem.objects.get_or_create(
            tenant=product_a.tenant, product=product_a, warehouse=warehouse,
            defaults={"on_hand": Decimal("100"), "avg_cost": Decimal("1000")},
        )
        oid = self._create_order_with_line(client, warehouse, product_a)
        r = client.post(f"/api/tables/orders/{oid}/checkout/", {
            "mode": "HACKED",
            "payments": [{"method": "cash", "amount": "5990"}],
        }, format="json")
        assert r.status_code == 400

    def test_checkout_invalid_sale_type(self, client, warehouse, product_a):
        from inventory.models import StockItem
        StockItem.objects.get_or_create(
            tenant=product_a.tenant, product=product_a, warehouse=warehouse,
            defaults={"on_hand": Decimal("100"), "avg_cost": Decimal("1000")},
        )
        oid = self._create_order_with_line(client, warehouse, product_a)
        r = client.post(f"/api/tables/orders/{oid}/checkout/", {
            "mode": "all",
            "sale_type": "GRATIS",
            "payments": [{"method": "cash", "amount": "5990"}],
        }, format="json")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════
# RECIPE UNIT VALIDATION (blindaje 27/04/26)
# Mario lo pidió: bloquear recetas con unidades incoherentes
# (ej. Leche cargada como UN cuando la receta dice 0,15 L)
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def units(tenant):
    """Unidades comunes: KG/GR (masa), L/ML (volumen), UN (conteo)."""
    from catalog.models import Unit
    kg = Unit.objects.create(tenant=tenant, code="KG", name="Kilogramo", family="MASS", is_base=True, conversion_factor=Decimal("1"))
    gr = Unit.objects.create(tenant=tenant, code="GR", name="Gramo", family="MASS", base_unit=kg, conversion_factor=Decimal("0.001"))
    ml = Unit.objects.create(tenant=tenant, code="ML", name="Mililitro", family="VOLUME", is_base=False, conversion_factor=Decimal("0.001"))
    lt = Unit.objects.create(tenant=tenant, code="L", name="Litro", family="VOLUME", is_base=True, conversion_factor=Decimal("1"))
    un = Unit.objects.create(tenant=tenant, code="UN", name="Unidad", family="COUNT", is_base=True, conversion_factor=Decimal("1"))
    return {"KG": kg, "GR": gr, "ML": ml, "L": lt, "UN": un}


class TestRecipeUnitValidation:
    """Bloquea recetas con desalineación de unidades — Mario blindaje."""

    def test_ingredient_without_unit_obj_blocked(self, client, tenant, product_a, units):
        """Producto Leche sin unit_obj configurado → no se puede usar
        en receta con unit_id de volumen. Mensaje accionable."""
        leche = Product.objects.create(tenant=tenant, name="Leche", price=Decimal("1500"))
        # NO le seteamos unit_obj. Simula el caso típico de un producto
        # cargado con `unit="UN"` (string) sin asociar Unit.
        r = client.post(f"/api/catalog/products/{product_a.id}/recipe/", {
            "is_active": True,
            "lines": [{"ingredient_id": leche.id, "qty": "0.150", "unit_id": units["L"].id}],
        }, format="json")
        assert r.status_code == 400
        # El error debe mencionar el ingrediente y pedir configurar unidad
        msg = str(r.data)
        assert "Leche" in msg
        assert "unidad" in msg.lower()

    def test_mismatched_family_blocked(self, client, tenant, product_a, units):
        """Producto cargado en COUNT, receta dice volumen → bloqueado."""
        leche = Product.objects.create(
            tenant=tenant, name="Leche", price=Decimal("1500"),
            unit_obj=units["UN"],  # ← cargada como unidad de conteo
        )
        r = client.post(f"/api/catalog/products/{product_a.id}/recipe/", {
            "is_active": True,
            "lines": [{"ingredient_id": leche.id, "qty": "0.150", "unit_id": units["L"].id}],
        }, format="json")
        assert r.status_code == 400
        msg = str(r.data)
        assert "Leche" in msg
        # Debe mencionar las dos familias para que el usuario entienda
        assert "volumen" in msg.lower() or "L" in msg
        assert "conteo" in msg.lower() or "UN" in msg

    def test_same_family_different_unit_ok(self, client, tenant, product_a, units):
        """L vs ML (ambos volumen) → OK, se convierte automáticamente."""
        leche = Product.objects.create(
            tenant=tenant, name="Leche", price=Decimal("1500"),
            unit_obj=units["L"],
        )
        r = client.post(f"/api/catalog/products/{product_a.id}/recipe/", {
            "is_active": True,
            "lines": [{"ingredient_id": leche.id, "qty": "150", "unit_id": units["ML"].id}],
        }, format="json")
        assert r.status_code == 200, r.data

    def test_no_unit_id_uses_ingredient_unit_ok(self, client, tenant, product_a, units):
        """Sin unit_id explícito → asume unidad del ingrediente. OK."""
        leche = Product.objects.create(
            tenant=tenant, name="Leche", price=Decimal("1500"),
            unit_obj=units["L"],
        )
        r = client.post(f"/api/catalog/products/{product_a.id}/recipe/", {
            "is_active": True,
            "lines": [{"ingredient_id": leche.id, "qty": "0.150"}],  # sin unit_id
        }, format="json")
        assert r.status_code == 200, r.data

    def test_kg_to_gr_ok(self, client, tenant, product_a, units):
        """Café cargado en KG, receta en GR → OK (misma familia masa)."""
        cafe = Product.objects.create(
            tenant=tenant, name="Café molido", price=Decimal("8000"),
            unit_obj=units["KG"],
        )
        r = client.post(f"/api/catalog/products/{product_a.id}/recipe/", {
            "is_active": True,
            "lines": [{"ingredient_id": cafe.id, "qty": "7", "unit_id": units["GR"].id}],
        }, format="json")
        assert r.status_code == 200, r.data
