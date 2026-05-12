"""
Tests del fix (12/05/26): MissingCostsView excluye productos con receta.

Mario pregunto: "los productos creados que tienen receta es necesario
poner costo? esta duda la tengo porque sus ingredientes ya llevan costo".

La respuesta correcta es NO — el costo se calcula desde los ingredientes
(sales/pricing.py:123 usa recipe_costs[pid] sobre avg_cost). El bug
estaba en que MissingCostsView listaba TODOS los productos con cost=0
incluyendo los que tienen receta, confundiendo al dueño.

Fix: excluir productos con Recipe(is_active=True) del listado.
"""
from decimal import Decimal

import pytest

from catalog.models import Product, Recipe, RecipeLine


@pytest.mark.django_db
class TestMissingCostsExcludesProductsWithRecipe:

    def test_product_with_active_recipe_not_listed(
        self, api_client, tenant,
    ):
        """Un Latte con receta NO debe aparecer en la lista, aunque
        Product.cost=0, porque su costo se calcula desde los ingredientes."""
        # Ingrediente (necesita costo manual)
        leche = Product.objects.create(
            tenant=tenant, name="Leche entera",
            price=Decimal("0"), is_active=True, cost=Decimal("0"),
        )
        # Producto con receta (NO necesita costo manual)
        latte = Product.objects.create(
            tenant=tenant, name="Latte",
            price=Decimal("3000"), is_active=True, cost=Decimal("0"),
        )
        recipe = Recipe.objects.create(tenant=tenant, product=latte, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=leche, qty=Decimal("200"),
        )

        resp = api_client.get("/api/catalog/products/missing-costs/")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["results"]]

        assert latte.id not in ids, (
            "Latte (con receta) NO debería aparecer en 'productos sin costo' — "
            "su costo se calcula desde ingredientes."
        )
        assert leche.id in ids, (
            "Leche (ingrediente raw sin receta) SÍ debe aparecer — "
            "necesita costo manual."
        )

    def test_product_with_inactive_recipe_still_listed(
        self, api_client, tenant,
    ):
        """Si la receta del producto está desactivada (is_active=False), el
        producto SÍ aparece en la lista. Sin receta activa, el cálculo cae
        a avg_cost, así que el costo manual es relevante de nuevo."""
        prod = Product.objects.create(
            tenant=tenant, name="Latte (receta vieja)",
            price=Decimal("3000"), is_active=True, cost=Decimal("0"),
        )
        ingr = Product.objects.create(
            tenant=tenant, name="Ingrediente x",
            price=Decimal("0"), is_active=True, cost=Decimal("0"),
        )
        recipe = Recipe.objects.create(
            tenant=tenant, product=prod, is_active=False,  # ← desactivada
        )
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=ingr, qty=Decimal("1"),
        )

        resp = api_client.get("/api/catalog/products/missing-costs/")
        ids = [p["id"] for p in resp.json()["results"]]
        assert prod.id in ids, (
            "Con receta INACTIVA, el producto vuelve a depender de avg_cost "
            "manual y SÍ debe pedir costo."
        )

    def test_product_with_recipe_and_cost_already_set_not_listed(
        self, api_client, tenant,
    ):
        """Doble seguridad: aunque tuviera Product.cost > 0, igual el filtro
        principal lo descarta (cost=0)."""
        prod = Product.objects.create(
            tenant=tenant, name="Latte con costo",
            price=Decimal("3000"), is_active=True, cost=Decimal("500"),
        )
        recipe = Recipe.objects.create(tenant=tenant, product=prod, is_active=True)

        resp = api_client.get("/api/catalog/products/missing-costs/")
        ids = [p["id"] for p in resp.json()["results"]]
        assert prod.id not in ids  # tiene cost > 0 + receta = doble exclusión
