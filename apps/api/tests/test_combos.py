"""
tests/test_combos.py — Combos / packs (Mario 28/05/26).

Un combo es un Product (is_combo=True) con receta de productos vendibles a
precio fijo. Cubre:
  - Crear combo (producto + receta) vía POST /catalog/combos/
  - Validaciones (≥2 unidades, productos del tenant, sin anidar combos)
  - El combo aparece en el buscador de productos de mesas (es Product activo)
  - E2E: cobrar una mesa con el combo descuenta el stock de los componentes
    y el precio cobrado es el del combo (no la suma)
"""
from decimal import Decimal

import pytest

from catalog.models import Product, Recipe, RecipeLine
from inventory.models import StockItem
from tables.models import Table, OpenOrder
from sales.models import Sale


URL_COMBOS = "/api/catalog/combos/"


def _product(tenant, name, price, category=None):
    return Product.objects.create(
        tenant=tenant, name=name, price=Decimal(str(price)),
        category=category, is_active=True,
    )


def _stock(tenant, warehouse, product, qty="100", cost="500"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(qty), avg_cost=Decimal(cost),
        stock_value=(Decimal(qty) * Decimal(cost)).quantize(Decimal("0.001")),
    )


@pytest.mark.django_db
class TestComboCRUD:
    def test_create_combo_creates_product_and_recipe(self, api_client, tenant, category):
        capu = _product(tenant, "Capuccino amaretto", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)

        resp = api_client.post(URL_COMBOS, {
            "name": "Combo Capu + Brownie",
            "price": "5600",
            "components": [
                {"product_id": capu.id, "qty": 1},
                {"product_id": brownie.id, "qty": 1},
            ],
        }, format="json")
        assert resp.status_code == 201, resp.content
        data = resp.json()
        assert data["name"] == "Combo Capu + Brownie"
        assert data["price"] == "5600"
        # precio normal = 3500 + 2900 = 6400; ahorro = 800
        assert data["normal_price"] == "6400.00"
        assert data["savings"] == "800.00"
        assert len(data["components"]) == 2

        # En la DB: producto combo + receta con 2 líneas
        combo = Product.objects.get(id=data["id"])
        assert combo.is_combo is True
        assert combo.price == Decimal("5600.00")
        recipe = Recipe.objects.get(product=combo)
        assert recipe.lines.count() == 2
        ings = {l.ingredient_id for l in recipe.lines.all()}
        assert ings == {capu.id, brownie.id}

    def test_combo_appears_in_product_search_for_mesas(self, api_client, tenant, category):
        """El combo debe aparecer en /catalog/products/ (buscador de mesas)
        porque es un Product activo."""
        capu = _product(tenant, "Capuccino", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        r = api_client.post(URL_COMBOS, {
            "name": "Combo Desayuno", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")
        combo_id = r.json()["id"]

        # Buscador de productos (lo que usa el panel de mesas)
        resp = api_client.get("/api/catalog/products/?q=Combo&is_active=true")
        assert resp.status_code == 200
        body = resp.json()
        rows = body["results"] if isinstance(body, dict) and "results" in body else body
        ids = {p["id"] for p in rows}
        assert combo_id in ids, "El combo debe aparecer en el buscador de productos"

    def test_list_combos(self, api_client, tenant, category):
        capu = _product(tenant, "Capu", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        api_client.post(URL_COMBOS, {
            "name": "Combo X", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")

        resp = api_client.get(URL_COMBOS)
        assert resp.status_code == 200
        combos = resp.json()
        assert len(combos) == 1
        assert combos[0]["name"] == "Combo X"

    def test_create_combo_rejects_single_unit(self, api_client, tenant, category):
        """Un combo de 1 producto qty 1 es un producto renombrado, no combo."""
        capu = _product(tenant, "Capu", 3500, category)
        resp = api_client.post(URL_COMBOS, {
            "name": "Falso combo", "price": "3000",
            "components": [{"product_id": capu.id, "qty": 1}],
        }, format="json")
        assert resp.status_code == 400
        assert "2 o más" in str(resp.json()).lower() or "2 o m" in str(resp.json())

    def test_create_combo_allows_pack_same_product(self, api_client, tenant, category):
        """Pack de varias unidades del MISMO producto (ej: 6 cervezas) sí vale."""
        beer = _product(tenant, "Cerveza", 2000, category)
        resp = api_client.post(URL_COMBOS, {
            "name": "Six Pack", "price": "10000",
            "components": [{"product_id": beer.id, "qty": 6}],
        }, format="json")
        assert resp.status_code == 201, resp.content
        assert resp.json()["normal_price"] == "12000.00"

    def test_create_combo_rejects_nested_combo(self, api_client, tenant, category):
        """Un combo no puede contener otro combo."""
        capu = _product(tenant, "Capu", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        r = api_client.post(URL_COMBOS, {
            "name": "Combo base", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")
        combo_id = r.json()["id"]

        resp = api_client.post(URL_COMBOS, {
            "name": "Combo de combos", "price": "9000",
            "components": [{"product_id": combo_id, "qty": 1}, {"product_id": capu.id, "qty": 1}],
        }, format="json")
        assert resp.status_code == 400
        assert "combo" in str(resp.json()).lower()

    def test_create_combo_rejects_other_tenant_product(self, api_client, tenant, category):
        from core.models import Tenant
        other = Tenant.objects.create(name="Otro", slug="otro-combo")
        intruso = Product.objects.create(tenant=other, name="Ajeno", price=Decimal("1000"), is_active=True)
        capu = _product(tenant, "Capu", 3500, category)
        resp = api_client.post(URL_COMBOS, {
            "name": "Combo intruso", "price": "5000",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": intruso.id, "qty": 1}],
        }, format="json")
        assert resp.status_code == 400

    def test_edit_combo_price_and_components(self, api_client, tenant, category):
        capu = _product(tenant, "Capu", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        torta = _product(tenant, "Torta", 4000, category)
        r = api_client.post(URL_COMBOS, {
            "name": "Combo", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")
        combo_id = r.json()["id"]

        # Cambiar precio y reemplazar brownie por torta
        resp = api_client.patch(f"{URL_COMBOS}{combo_id}/", {
            "price": "6500",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": torta.id, "qty": 1}],
        }, format="json")
        assert resp.status_code == 200, resp.content
        data = resp.json()
        assert data["price"] == "6500"
        ings = {c["product_id"] for c in data["components"]}
        assert ings == {capu.id, torta.id}

    def test_delete_combo_soft_deletes(self, api_client, tenant, category):
        capu = _product(tenant, "Capu", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        r = api_client.post(URL_COMBOS, {
            "name": "Combo Del", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")
        combo_id = r.json()["id"]

        resp = api_client.delete(f"{URL_COMBOS}{combo_id}/")
        assert resp.status_code == 204
        # Ya no aparece en la lista
        assert api_client.get(URL_COMBOS).json() == []


@pytest.mark.django_db
class TestComboE2EVenta:
    def test_cobrar_combo_descuenta_componentes_y_precio_es_del_combo(
        self, api_client, tenant, store, warehouse, category,
    ):
        """E2E: combo en mesa → cobrar → descuenta stock de los 2
        componentes (1 c/u) y cobra el precio del combo, NO la suma."""
        capu = _product(tenant, "Capuccino amaretto", 3500, category)
        brownie = _product(tenant, "Brownie", 2900, category)
        si_capu = _stock(tenant, warehouse, capu, qty="10", cost="800")
        si_brownie = _stock(tenant, warehouse, brownie, qty="10", cost="600")

        # Crear combo $5600
        r = api_client.post(URL_COMBOS, {
            "name": "Combo Capu + Brownie", "price": "5600",
            "components": [{"product_id": capu.id, "qty": 1}, {"product_id": brownie.id, "qty": 1}],
        }, format="json")
        assert r.status_code == 201, r.content
        combo_id = r.json()["id"]

        # Mesa: abrir, agregar el combo, cobrar
        t = api_client.post("/api/tables/tables/", {"name": "Mesa Combo", "capacity": 4}, format="json").json()
        o = api_client.post(f"/api/tables/tables/{t['id']}/open/", {"warehouse_id": warehouse.id}, format="json").json()
        api_client.post(f"/api/tables/orders/{o['id']}/add-lines/", {
            "lines": [{"product_id": combo_id, "qty": 1, "unit_price": "5600"}],
        }, format="json")

        resp = api_client.post(f"/api/tables/orders/{o['id']}/checkout/", {
            "mode": "all",
            "payments": [{"method": "cash", "amount": "5600"}],
        }, format="json")
        assert resp.status_code == 201, resp.content
        sale = Sale.objects.get(id=resp.json()["id"])

        # Precio cobrado = el del combo ($5600), NO la suma (6400)
        assert sale.total == Decimal("5600.00")

        # Stock: descontó 1 capuccino + 1 brownie (los componentes)
        si_capu.refresh_from_db()
        si_brownie.refresh_from_db()
        assert si_capu.on_hand == Decimal("9.000"), f"capu={si_capu.on_hand}"
        assert si_brownie.on_hand == Decimal("9.000"), f"brownie={si_brownie.on_hand}"

        # Costo del combo = costo de los componentes (800 + 600 = 1400)
        assert sale.total_cost == Decimal("1400.00"), f"cost={sale.total_cost}"
        # Margen = 5600 − 1400 = 4200
        assert sale.gross_profit == Decimal("4200.00"), f"profit={sale.gross_profit}"
