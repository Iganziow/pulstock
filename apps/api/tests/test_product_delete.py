"""
Tests para el borrado lógico de productos (DELETE /api/catalog/products/{id}/).

Mario pidió poder borrar productos desde el catálogo. Decidimos hacer
borrado lógico (deleted_at) para conservar el historial de ventas.

Reglas:
  1. Si el producto es ingrediente de una receta activa → 409 Conflict.
  2. Si no, marca deleted_at = now() y desaparece del catálogo, POS,
     búsquedas. Las ventas históricas siguen mostrándolo (porque siguen
     en la DB y los serializers de ventas pasan por _base_manager).
  3. El producto borrado NO aparece en `Product.objects` pero SÍ en
     `Product.all_objects`.
"""
import pytest
from django.utils import timezone

from catalog.models import Product, Recipe, RecipeLine


@pytest.mark.django_db
class TestProductDelete:

    @pytest.fixture(autouse=True)
    def _setup(self, tenant):
        self.tenant = tenant
        self.product_simple = Product.objects.create(
            tenant=tenant, name="Producto Simple", sku="SIMPLE", price=1000
        )
        self.product_con_receta = Product.objects.create(
            tenant=tenant, name="Capuchino", sku="CAP", price=2500
        )
        self.ingrediente = Product.objects.create(
            tenant=tenant, name="Café molido", sku="CAFE-M", price=0
        )
        # Receta: Capuchino consume 1 Café molido
        recipe = Recipe.objects.create(tenant=tenant, product=self.product_con_receta, is_active=True)
        RecipeLine.objects.create(
            tenant=tenant, recipe=recipe, ingredient=self.ingrediente, qty=1
        )

    def test_delete_simple_product_marks_deleted_at(self, auth_client):
        """Producto sin receta ni dependencias → borrado lógico exitoso."""
        r = auth_client.delete(f"/api/catalog/products/{self.product_simple.id}/")
        assert r.status_code == 200, r.data
        assert r.data["deleted"] is True
        # En la DB el producto sigue, pero con deleted_at
        p = Product.all_objects.get(pk=self.product_simple.pk)
        assert p.deleted_at is not None
        assert p.is_active is False

    def test_delete_product_used_as_ingredient_returns_409(self, auth_client):
        """Producto usado como ingrediente activo → 409 con lista de recetas."""
        r = auth_client.delete(f"/api/catalog/products/{self.ingrediente.id}/")
        assert r.status_code == 409, r.data
        assert r.data["code"] == "in_use_as_ingredient"
        assert len(r.data["recipes"]) == 1
        assert r.data["recipes"][0]["product_name"] == "Capuchino"
        # Y el producto NO se borró
        p = Product.all_objects.get(pk=self.ingrediente.pk)
        assert p.deleted_at is None

    def test_deleted_product_excluded_from_default_manager(self, auth_client):
        """Después de borrar, Product.objects ya no lo trae."""
        auth_client.delete(f"/api/catalog/products/{self.product_simple.id}/")
        # objects (default manager) excluye borrados
        assert not Product.objects.filter(pk=self.product_simple.pk).exists()
        # all_objects los incluye
        assert Product.all_objects.filter(pk=self.product_simple.pk).exists()

    def test_deleted_product_not_in_catalog_list(self, auth_client):
        """Producto borrado no aparece en GET /catalog/products/."""
        auth_client.delete(f"/api/catalog/products/{self.product_simple.id}/")
        r = auth_client.get("/api/catalog/products/")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert "Producto Simple" not in names

    def test_deleted_product_404_on_subsequent_get(self, auth_client):
        """GET de producto borrado responde 404."""
        auth_client.delete(f"/api/catalog/products/{self.product_simple.id}/")
        r = auth_client.get(f"/api/catalog/products/{self.product_simple.id}/")
        assert r.status_code == 404

    def test_inactive_recipe_does_not_block_ingredient_delete(self, auth_client):
        """Si la receta que usa el ingrediente está INACTIVA, sí se puede borrar."""
        # Desactivamos la receta
        recipe = Recipe.objects.get(product=self.product_con_receta)
        recipe.is_active = False
        recipe.save()

        r = auth_client.delete(f"/api/catalog/products/{self.ingrediente.id}/")
        assert r.status_code == 200, r.data
        p = Product.all_objects.get(pk=self.ingrediente.pk)
        assert p.deleted_at is not None
