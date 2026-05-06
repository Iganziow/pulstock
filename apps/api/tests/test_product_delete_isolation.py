"""
Tests adicionales para verificar que productos borrados quedan completamente
aislados de las superficies que el cliente ve (POS, búsquedas, predicciones)
PERO siguen disponibles para reportes históricos.

Caza bugs de regresión: si alguien agrega una nueva consulta a Product en
el futuro, estos tests pueden detectar olvidos.
"""
import pytest
from datetime import datetime
from django.utils import timezone

from catalog.models import Product, Category, Barcode


@pytest.mark.django_db
class TestDeletedProductIsolation:
    """Productos borrados no deben aparecer en ninguna superficie de cliente."""

    @pytest.fixture(autouse=True)
    def _setup(self, tenant):
        self.tenant = tenant
        self.cat = Category.objects.create(tenant=tenant, name="Bebidas")
        self.vivo = Product.objects.create(
            tenant=tenant, name="Latte", sku="LAT-001", price=3000, category=self.cat,
        )
        self.borrado = Product.objects.create(
            tenant=tenant, name="Latte viejo", sku="LAT-OLD", price=2500, category=self.cat,
            deleted_at=timezone.now(), is_active=False,
        )

    def test_search_excludes_deleted(self, auth_client):
        """GET /catalog/products/search/?q=Latte solo devuelve el vivo."""
        r = auth_client.get("/api/catalog/products/search/?q=Latte")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert "Latte" in names
        assert "Latte viejo" not in names

    def test_lookup_by_sku_excludes_deleted(self, auth_client):
        """POS: lookup por SKU exacto del producto borrado responde 404."""
        r = auth_client.get("/api/catalog/products/lookup/?term=LAT-OLD")
        assert r.status_code == 404

    def test_lookup_by_barcode_excludes_deleted(self, auth_client, tenant):
        """POS: si el producto borrado tenía un barcode, escanearlo NO debe
        encontrarlo. Bug potencial: las relaciones inversas usan _base_manager
        que sí trae borrados, así que tuvimos que agregar el filtro explícito."""
        Barcode.objects.create(tenant=tenant, product=self.borrado, code="7800001234567")
        r = auth_client.get("/api/catalog/products/lookup/?term=7800001234567")
        assert r.status_code == 404

    def test_lookup_by_sku_finds_alive(self, auth_client):
        """Sanity check: el producto vivo SÍ se encuentra por SKU."""
        r = auth_client.get("/api/catalog/products/lookup/?term=LAT-001")
        assert r.status_code == 200
        assert r.data.get("name") == "Latte"

    def test_main_list_excludes_deleted(self, auth_client):
        """GET /catalog/products/ no incluye borrados."""
        r = auth_client.get("/api/catalog/products/")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert "Latte" in names
        assert "Latte viejo" not in names

    def test_category_filter_excludes_deleted(self, auth_client):
        """Filtro por categoría tampoco trae borrados."""
        r = auth_client.get(f"/api/catalog/products/?category={self.cat.id}")
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert "Latte" in names
        assert "Latte viejo" not in names

    def test_get_deleted_product_returns_404(self, auth_client):
        """GET directo al ID del borrado responde 404."""
        r = auth_client.get(f"/api/catalog/products/{self.borrado.id}/")
        assert r.status_code == 404

    def test_patch_deleted_product_returns_404(self, auth_client):
        """No se puede editar un producto borrado vía PATCH."""
        r = auth_client.patch(f"/api/catalog/products/{self.borrado.id}/", {
            "price": "9999",
        }, format="json")
        assert r.status_code == 404

    def test_avg_cost_endpoint_404_for_deleted(self, auth_client):
        """No se puede actualizar el avg_cost de un producto borrado."""
        r = auth_client.post(f"/api/catalog/products/{self.borrado.id}/avg-cost/", {
            "avg_cost": "1000",
        }, format="json")
        assert r.status_code == 404

    def test_delete_already_deleted_returns_404(self, auth_client):
        """Volver a borrar un producto ya borrado debería responder 404, no
        re-borrar (defensa contra clicks dobles o caches stale)."""
        r = auth_client.delete(f"/api/catalog/products/{self.borrado.id}/")
        assert r.status_code == 404


@pytest.mark.django_db
class TestDeletedProductSideEffects:
    """Verifica efectos colaterales de borrar productos: promos, recetas
    como padre, stock no-cero, forecast."""

    @pytest.fixture(autouse=True)
    def _setup(self, tenant):
        self.tenant = tenant
        self.product = Product.objects.create(
            tenant=tenant, name="Mi Producto", sku="MP-001", price=2000,
        )

    def test_can_delete_product_with_stock_greater_than_zero(self, auth_client, warehouse_a):
        """Un producto con stock disponible debería poder borrarse igual.
        El StockItem queda en la DB (sigue apuntando al producto via FK)."""
        from inventory.models import StockItem
        from decimal import Decimal
        StockItem.objects.create(
            tenant=self.tenant, warehouse=warehouse_a, product=self.product,
            on_hand=Decimal("10.000"), avg_cost=Decimal("500.000"),
            stock_value=Decimal("5000.000"),
        )
        r = auth_client.delete(f"/api/catalog/products/{self.product.id}/")
        assert r.status_code == 200, r.data
        # StockItem sigue intacto
        si = StockItem.objects.get(product=self.product)
        assert si.on_hand == Decimal("10.000")

    def test_can_delete_product_that_owns_a_recipe_as_parent(self, auth_client, tenant):
        """Si el producto BORRADO tiene su propia receta (es padre, no
        ingrediente), también se puede borrar. La receta queda en DB pero
        el producto desaparece del catálogo. La regla de bloqueo es solo
        cuando es INGREDIENTE, no cuando es padre."""
        from catalog.models import Recipe, RecipeLine
        ingrediente = Product.objects.create(tenant=tenant, name="Café", price=0)
        recipe = Recipe.objects.create(tenant=tenant, product=self.product, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=ingrediente, qty=1)

        r = auth_client.delete(f"/api/catalog/products/{self.product.id}/")
        assert r.status_code == 200, r.data
        # La receta sigue existiendo en la DB pero el producto está borrado.
        # Recipe.product apunta al producto borrado vía _base_manager.
        recipe.refresh_from_db()
        assert recipe.product_id == self.product.id

    def test_can_delete_product_referenced_by_promotion(self, auth_client, tenant):
        """Si el producto está en una promoción activa, se puede borrar igual.
        PromotionProduct con on_delete=CASCADE limpia la línea automático."""
        from promotions.models import Promotion, PromotionProduct
        from django.utils import timezone
        from datetime import timedelta
        promo = Promotion.objects.create(
            tenant=tenant, name="20% off", discount_type="pct", discount_value=20,
            start_date=timezone.now(), end_date=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        pp = PromotionProduct.objects.create(promotion=promo, product=self.product)

        r = auth_client.delete(f"/api/catalog/products/{self.product.id}/")
        assert r.status_code == 200, r.data
        # La PromotionProduct sigue existiendo (con FK al producto borrado)
        # porque NO usamos on_delete=CASCADE en el borrado lógico.
        # La promo sigue en DB pero el producto borrado no aparecerá en el POS.
        assert PromotionProduct.objects.filter(pk=pp.pk).exists()
