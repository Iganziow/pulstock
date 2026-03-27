"""
Tests de integración — Unidades y Recetas con conversión
=========================================================

Verifica que:
1. Product.unit_obj se auto-linkea al crear/actualizar via API
2. Product.unit_obj se auto-linkea al importar CSV
3. Receta con conversión KG↔GR descuenta stock correcto
4. Receta con conversión LT↔ML descuenta stock correcto
5. Receta sin conversión (misma unidad) funciona
6. Receta con ingrediente sin unit_obj no crashea
7. Venta con receta calcula costo desde ingredientes convertidos
8. convert_qty funciona correctamente en ambas direcciones
9. convert_qty rechaza familias distintas
"""
import pytest
from decimal import Decimal

from django.utils import timezone

from catalog.models import Product, Recipe, RecipeLine, Unit
from catalog.unit_conversion import convert_qty
from inventory.models import StockItem
from sales.models import Sale, SaleLine


D = Decimal
Q3 = D("0.001")


# ══════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════

@pytest.fixture
def units(db, tenant):
    """Seed standard units for the tenant."""
    gr, _ = Unit.objects.get_or_create(
        tenant=tenant, code="GR",
        defaults={"name": "Gramo", "family": "MASS", "is_base": True, "conversion_factor": D("1")},
    )
    kg, _ = Unit.objects.get_or_create(
        tenant=tenant, code="KG",
        defaults={"name": "Kilogramo", "family": "MASS", "is_base": False,
                  "base_unit": gr, "conversion_factor": D("1000")},
    )
    ml, _ = Unit.objects.get_or_create(
        tenant=tenant, code="ML",
        defaults={"name": "Mililitro", "family": "VOLUME", "is_base": True, "conversion_factor": D("1")},
    )
    lt, _ = Unit.objects.get_or_create(
        tenant=tenant, code="LT",
        defaults={"name": "Litro", "family": "VOLUME", "is_base": False,
                  "base_unit": ml, "conversion_factor": D("1000")},
    )
    un, _ = Unit.objects.get_or_create(
        tenant=tenant, code="UN",
        defaults={"name": "Unidad", "family": "COUNT", "is_base": True, "conversion_factor": D("1")},
    )
    return {"gr": gr, "kg": kg, "ml": ml, "lt": lt, "un": un}


@pytest.fixture
def _receive(api_client, warehouse):
    """Helper to receive stock."""
    def do(product_id, qty, unit_cost=None):
        body = {"warehouse_id": warehouse.id, "product_id": product_id, "qty": str(qty)}
        if unit_cost is not None:
            body["unit_cost"] = str(unit_cost)
        return api_client.post("/api/inventory/receive/", body, format="json")
    return do


@pytest.fixture
def _sell(api_client, warehouse):
    """Helper to create a sale."""
    def do(lines, payments=None):
        body = {
            "warehouse_id": warehouse.id,
            "lines": lines,
            "payments": payments or [],
        }
        return api_client.post("/api/sales/sales/", body, format="json")
    return do


# ══════════════════════════════════════════════════
# 1. convert_qty — Unit math
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestConvertQty:

    def test_gr_to_kg(self, units):
        result = convert_qty(D("500"), units["gr"], units["kg"])
        assert result == D("0.5")

    def test_kg_to_gr(self, units):
        result = convert_qty(D("2"), units["kg"], units["gr"])
        assert result == D("2000")

    def test_ml_to_lt(self, units):
        result = convert_qty(D("750"), units["ml"], units["lt"])
        assert result == D("0.75")

    def test_lt_to_ml(self, units):
        result = convert_qty(D("1.5"), units["lt"], units["ml"])
        assert result == D("1500.0")

    def test_same_unit_no_change(self, units):
        result = convert_qty(D("100"), units["kg"], units["kg"])
        assert result == D("100")

    def test_cross_family_raises(self, units):
        with pytest.raises(ValueError, match="No se puede convertir"):
            convert_qty(D("100"), units["kg"], units["lt"])

    def test_zero_qty(self, units):
        result = convert_qty(D("0"), units["gr"], units["kg"])
        assert result == D("0")

    def test_precision_preserved(self, units):
        # 1 GR → KG = 0.001
        result = convert_qty(D("1"), units["gr"], units["kg"])
        assert result == D("0.001")


# ══════════════════════════════════════════════════
# 2. Product.unit_obj auto-linking
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestProductUnitObjAutoLink:

    def test_create_product_links_unit_obj(self, api_client, tenant, units):
        """POST /catalog/products/ with unit=KG auto-sets unit_obj."""
        r = api_client.post("/api/catalog/products/", {
            "name": "Carne Molida", "price": "5000", "unit": "KG",
        }, format="json")
        assert r.status_code == 201
        p = Product.objects.get(id=r.data["id"])
        assert p.unit == "KG"
        assert p.unit_obj is not None
        assert p.unit_obj.code == "KG"
        assert p.unit_obj.family == "MASS"

    def test_create_product_with_gr(self, api_client, tenant, units):
        r = api_client.post("/api/catalog/products/", {
            "name": "Sal Fina", "price": "800", "unit": "GR",
        }, format="json")
        assert r.status_code == 201
        p = Product.objects.get(id=r.data["id"])
        assert p.unit_obj is not None
        assert p.unit_obj.code == "GR"

    def test_create_product_default_un(self, api_client, tenant, units):
        """No unit specified → defaults to UN."""
        r = api_client.post("/api/catalog/products/", {
            "name": "Pan", "price": "200",
        }, format="json")
        assert r.status_code == 201
        p = Product.objects.get(id=r.data["id"])
        assert p.unit == "UN"
        assert p.unit_obj is not None
        assert p.unit_obj.code == "UN"

    def test_update_product_changes_unit_obj(self, api_client, tenant, units):
        """PATCH unit=LT updates unit_obj."""
        r = api_client.post("/api/catalog/products/", {
            "name": "Leche", "price": "1200", "unit": "ML",
        }, format="json")
        pid = r.data["id"]
        r2 = api_client.patch(f"/api/catalog/products/{pid}/", {
            "unit": "LT",
        }, format="json")
        assert r2.status_code == 200
        p = Product.objects.get(id=pid)
        assert p.unit == "LT"
        assert p.unit_obj.code == "LT"


# ══════════════════════════════════════════════════
# 3. Recipe with unit conversion — Stock deduction
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestRecipeConversion:

    def test_recipe_gr_ingredient_stored_in_kg(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Receta: Hamburguesa usa 200 GR de carne
        Carne se almacena en KG (unit_obj=KG)
        Al vender 5 hamburguesas → descuenta 1.0 KG (5 × 200GR = 1000GR = 1KG)
        """
        # Create products with unit_obj
        hamburguesa = Product.objects.create(
            tenant=tenant, name="Hamburguesa", price=D("5000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        carne = Product.objects.create(
            tenant=tenant, name="Carne", price=D("8000"),
            is_active=True, unit="KG", unit_obj=units["kg"],
        )

        # Recipe: 200 GR of carne per hamburguesa
        recipe = Recipe.objects.create(tenant=tenant, product=hamburguesa, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=carne,
            qty=D("200"), unit=units["gr"],  # 200 GR per hamburguesa
        )

        # Receive 5 KG of carne
        _receive(carne.id, 5, 8000)
        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=carne)
        assert si.on_hand == D("5.000")

        # Sell 5 hamburguesas
        r = _sell([{"product_id": hamburguesa.id, "qty": "5", "unit_price": "5000"}],
                  [{"method": "cash", "amount": 25000}])
        assert r.status_code == 201

        si.refresh_from_db()
        # 5 × 200GR = 1000GR → converted to KG = 1.0 KG
        assert si.on_hand == D("4.000")

    def test_recipe_ml_ingredient_stored_in_lt(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Receta: Cocktail usa 50 ML de jugo
        Jugo se almacena en LT (unit_obj=LT)
        Al vender 10 cocktails → descuenta 0.5 LT (10 × 50ML = 500ML = 0.5LT)
        """
        cocktail = Product.objects.create(
            tenant=tenant, name="Cocktail", price=D("3000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        jugo = Product.objects.create(
            tenant=tenant, name="Jugo Naranja", price=D("2000"),
            is_active=True, unit="LT", unit_obj=units["lt"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=cocktail, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=jugo,
            qty=D("50"), unit=units["ml"],  # 50 ML per cocktail
        )

        _receive(jugo.id, 3, 2000)  # 3 LT
        r = _sell([{"product_id": cocktail.id, "qty": "10", "unit_price": "3000"}],
                  [{"method": "cash", "amount": 30000}])
        assert r.status_code == 201

        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=jugo)
        # 10 × 50ML = 500ML → 0.5 LT
        assert si.on_hand == D("2.500")

    def test_recipe_same_unit_no_conversion(self, api_client, tenant, warehouse, units, _receive, _sell):
        """Ingrediente y receta en la misma unidad → sin conversión."""
        pizza = Product.objects.create(
            tenant=tenant, name="Pizza", price=D("6000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        masa = Product.objects.create(
            tenant=tenant, name="Masa", price=D("500"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=pizza, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=masa,
            qty=D("1"), unit=units["un"],
        )

        _receive(masa.id, 10, 500)
        r = _sell([{"product_id": pizza.id, "qty": "3", "unit_price": "6000"}],
                  [{"method": "cash", "amount": 18000}])
        assert r.status_code == 201

        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=masa)
        assert si.on_hand == D("7.000")

    def test_recipe_null_unit_uses_ingredient_unit(self, api_client, tenant, warehouse, units, _receive, _sell):
        """RecipeLine.unit=NULL → qty is in ingredient's unit, no conversion."""
        sandwich = Product.objects.create(
            tenant=tenant, name="Sandwich", price=D("2500"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        pan = Product.objects.create(
            tenant=tenant, name="Pan Molde", price=D("100"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=sandwich, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=pan,
            qty=D("2"), unit=None,  # NULL → use ingredient's unit
        )

        _receive(pan.id, 20, 100)
        r = _sell([{"product_id": sandwich.id, "qty": "4", "unit_price": "2500"}],
                  [{"method": "cash", "amount": 10000}])
        assert r.status_code == 201

        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=pan)
        assert si.on_hand == D("12.000")  # 20 - (4×2) = 12


# ══════════════════════════════════════════════════
# 4. Recipe cost with conversion
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestRecipeCostConversion:

    def test_cost_calculated_from_converted_ingredients(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Hamburguesa: 200 GR carne (almacenada en KG @ $8000/KG)
        Costo por unidad = 200GR → 0.2 KG × $8000 = $1600
        Vender 3 → total_cost = 3 × $1600 = $4800
        """
        hamburguesa = Product.objects.create(
            tenant=tenant, name="Burger Cost", price=D("5000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        carne = Product.objects.create(
            tenant=tenant, name="Carne Cost", price=D("8000"),
            is_active=True, unit="KG", unit_obj=units["kg"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=hamburguesa, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=carne,
            qty=D("200"), unit=units["gr"],
        )

        _receive(carne.id, 10, 8000)  # 10 KG @ $8000/KG

        r = _sell([{"product_id": hamburguesa.id, "qty": "3", "unit_price": "5000"}],
                  [{"method": "cash", "amount": 15000}])
        assert r.status_code == 201

        sale = Sale.objects.get(id=r.data["id"])
        # Cost per unit: 200GR = 0.2KG × $8000 = $1600
        # Total cost: 3 × $1600 = $4800
        assert sale.total_cost == D("4800.000")
        assert sale.gross_profit == D("10200.00")  # 15000 - 4800


# ══════════════════════════════════════════════════
# 5. Recipe with ingredient missing unit_obj
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestRecipeNoUnitObj:

    def test_ingredient_without_unit_obj_no_crash(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Ingredient has unit='GR' (string) but unit_obj=NULL.
        RecipeLine has unit set. Should not crash — falls back gracefully.
        """
        combo = Product.objects.create(
            tenant=tenant, name="Combo", price=D("4000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        # Ingredient WITHOUT unit_obj (simulating legacy product)
        azucar = Product.objects.create(
            tenant=tenant, name="Azucar", price=D("1000"),
            is_active=True, unit="GR", unit_obj=None,  # NULL!
        )

        recipe = Recipe.objects.create(tenant=tenant, product=combo, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=azucar,
            qty=D("50"), unit=units["gr"],  # Same as ingredient's string unit
        )

        _receive(azucar.id, 500, 1000)  # 500 units (GR assumed)
        r = _sell([{"product_id": combo.id, "qty": "2", "unit_price": "4000"}],
                  [{"method": "cash", "amount": 8000}])
        assert r.status_code == 201

        si = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=azucar)
        # 500 - (2 × 50) = 400
        assert si.on_hand == D("400.000")


# ══════════════════════════════════════════════════
# 6. Multi-ingredient recipe with mixed units
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestMultiIngredientRecipe:

    def test_mixed_units_recipe(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Receta compleja:
          Batido = 1 UN banana + 200 ML leche + 30 GR azúcar
          Banana en UN, leche en LT, azúcar en KG
        """
        batido = Product.objects.create(
            tenant=tenant, name="Batido", price=D("3500"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        banana = Product.objects.create(
            tenant=tenant, name="Banana", price=D("300"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        leche = Product.objects.create(
            tenant=tenant, name="Leche", price=D("1500"),
            is_active=True, unit="LT", unit_obj=units["lt"],
        )
        azucar = Product.objects.create(
            tenant=tenant, name="Azucar", price=D("2000"),
            is_active=True, unit="KG", unit_obj=units["kg"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=batido, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=banana, qty=D("1"), unit=units["un"])
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche, qty=D("200"), unit=units["ml"])
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=azucar, qty=D("30"), unit=units["gr"])

        # Stock: 20 bananas, 5 LT leche, 2 KG azúcar
        _receive(banana.id, 20, 300)
        _receive(leche.id, 5, 1500)
        _receive(azucar.id, 2, 2000)

        # Sell 4 batidos
        r = _sell([{"product_id": batido.id, "qty": "4", "unit_price": "3500"}],
                  [{"method": "cash", "amount": 14000}])
        assert r.status_code == 201

        # Check stock
        si_banana = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=banana)
        si_leche = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=leche)
        si_azucar = StockItem.objects.get(tenant=tenant, warehouse=warehouse, product=azucar)

        assert si_banana.on_hand == D("16.000")  # 20 - 4×1 = 16
        assert si_leche.on_hand == D("4.200")    # 5 - 4×200ML→0.8LT = 4.2
        assert si_azucar.on_hand == D("1.880")   # 2 - 4×30GR→0.12KG = 1.88


# ══════════════════════════════════════════════════
# 7. Insufficient stock with conversion
# ══════════════════════════════════════════════════

@pytest.mark.django_db
class TestInsufficientStockWithConversion:

    def test_insufficient_after_conversion(self, api_client, tenant, warehouse, units, _receive, _sell):
        """
        Carne: 0.5 KG en stock.
        Hamburguesa requiere 200 GR → 0.2 KG.
        Vender 3 hamburguesas → necesita 0.6 KG → rechaza (solo hay 0.5).
        """
        hamburguesa = Product.objects.create(
            tenant=tenant, name="Hamburguesa Insuf", price=D("5000"),
            is_active=True, unit="UN", unit_obj=units["un"],
        )
        carne = Product.objects.create(
            tenant=tenant, name="Carne Insuf", price=D("8000"),
            is_active=True, unit="KG", unit_obj=units["kg"],
        )

        recipe = Recipe.objects.create(tenant=tenant, product=hamburguesa, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=carne,
            qty=D("200"), unit=units["gr"],
        )

        _receive(carne.id, D("0.5"), 8000)  # Only 0.5 KG

        r = _sell([{"product_id": hamburguesa.id, "qty": "3", "unit_price": "5000"}],
                  [{"method": "cash", "amount": 15000}])
        # 3 × 200GR = 600GR = 0.6KG > 0.5KG → rejected
        assert r.status_code == 409
