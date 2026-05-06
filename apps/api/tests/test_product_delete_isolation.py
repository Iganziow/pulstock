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

    def test_can_delete_product_with_empty_sku(self, auth_client, tenant):
        """Producto sin SKU (sku='') se puede borrar y se puede crear otro
        sin SKU también — el constraint solo aplica con sku no vacío."""
        p1 = Product.objects.create(tenant=tenant, name="Sin SKU 1", price=1000, sku="")
        r = auth_client.delete(f"/api/catalog/products/{p1.id}/")
        assert r.status_code == 200, r.data

        # Crear otro sin SKU debe funcionar (no hay conflicto de unicidad)
        r = auth_client.post("/api/catalog/products/", {
            "name": "Sin SKU 2", "sku": "", "price": "1000", "is_active": True, "unit": "UN",
        }, format="json")
        assert r.status_code == 201, r.data

    def test_double_delete_concurrent_safe(self, auth_client):
        """Dos requests DELETE casi simultáneos: el segundo devuelve 404
        en vez de petar con error. Defensa contra clicks dobles del usuario."""
        r1 = auth_client.delete(f"/api/catalog/products/{self.product.id}/")
        r2 = auth_client.delete(f"/api/catalog/products/{self.product.id}/")
        assert r1.status_code == 200
        assert r2.status_code == 404

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


@pytest.mark.django_db
class TestDeleteSecurity:
    """Tests de seguridad: cross-tenant + permisos por rol."""

    @pytest.fixture(autouse=True)
    def _setup(self, db, tenant):
        from core.models import Tenant, User
        # Tenant A (default fixture) y producto suyo
        self.tenant_a = tenant
        self.product_a = Product.objects.create(tenant=tenant, name="Prod A", price=1000)

        # Tenant B distinto + usuario propio
        self.tenant_b = Tenant.objects.create(name="Otro Local", slug="otro-local")
        self.user_b = User.objects.create_user(username="userb", password="pass")
        self.user_b.tenant = self.tenant_b
        self.user_b.role = User.Role.OWNER
        self.user_b.save()
        self.product_b = Product.objects.create(tenant=self.tenant_b, name="Prod B", price=2000)

    def test_cannot_delete_product_from_other_tenant(self, db):
        """Owner del tenant B intenta borrar producto del tenant A → 404."""
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(user=self.user_b)
        r = c.delete(f"/api/catalog/products/{self.product_a.id}/")
        assert r.status_code == 404, r.data
        # El producto sigue vivo
        self.product_a.refresh_from_db()
        assert self.product_a.deleted_at is None

    def test_cashier_cannot_delete_products(self, db, tenant, store):
        """CASHIER tiene permisos limitados — DELETE debe responder 403."""
        from core.models import User
        from rest_framework.test import APIClient
        cashier = User.objects.create_user(username="cashier", password="pass")
        cashier.tenant = tenant
        cashier.active_store = store
        cashier.role = User.Role.CASHIER
        cashier.save()
        c = APIClient()
        c.force_authenticate(user=cashier)
        r = c.delete(f"/api/catalog/products/{self.product_a.id}/")
        assert r.status_code == 403, r.data

    def test_inventory_role_cannot_delete_products(self, db, tenant, store):
        """INVENTORY tampoco — solo MANAGER+ y OWNER."""
        from core.models import User
        from rest_framework.test import APIClient
        inv = User.objects.create_user(username="inv", password="pass")
        inv.tenant = tenant
        inv.active_store = store
        inv.role = User.Role.INVENTORY
        inv.save()
        c = APIClient()
        c.force_authenticate(user=inv)
        r = c.delete(f"/api/catalog/products/{self.product_a.id}/")
        assert r.status_code == 403, r.data

    def test_anonymous_cannot_delete_products(self, db):
        """Sin autenticación → 401."""
        from rest_framework.test import APIClient
        c = APIClient()
        r = c.delete(f"/api/catalog/products/{self.product_a.id}/")
        assert r.status_code == 401


@pytest.mark.django_db
class TestDeletedProductInOtherEndpoints:
    """Verifica que los endpoints custom (bulk price/cost, missing-costs,
    assign-barcode) no toquen productos borrados."""

    @pytest.fixture(autouse=True)
    def _setup(self, tenant):
        self.tenant = tenant
        self.vivo = Product.objects.create(
            tenant=tenant, name="Vivo", sku="V1", price=1000, cost=100,
        )
        self.borrado = Product.objects.create(
            tenant=tenant, name="Borrado", sku="B1", price=2000, cost=200,
            deleted_at=timezone.now(), is_active=False,
        )

    def test_bulk_price_update_skips_deleted(self, auth_client):
        """Bulk price update no debe afectar productos borrados."""
        r = auth_client.post("/api/catalog/products/prices/bulk/", {
            "updates": [
                {"product_id": self.vivo.id, "price": "999"},
                {"product_id": self.borrado.id, "price": "999"},  # borrado: no debe actualizarse
            ],
        }, format="json")
        assert r.status_code == 200
        # Solo el vivo se actualizó
        self.vivo.refresh_from_db()
        self.borrado.refresh_from_db()
        assert str(self.vivo.price) == "999.00"
        assert str(self.borrado.price) == "2000.00"  # sin cambios

    def test_bulk_cost_update_skips_deleted(self, auth_client):
        """Bulk cost update tampoco debe afectar borrados."""
        r = auth_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": self.vivo.id, "cost": "150"},
                {"product_id": self.borrado.id, "cost": "150"},
            ],
        }, format="json")
        assert r.status_code == 200
        self.vivo.refresh_from_db()
        self.borrado.refresh_from_db()
        assert str(self.vivo.cost) == "150.00"
        assert str(self.borrado.cost) == "200.00"  # sin cambios

    def test_missing_costs_excludes_deleted(self, auth_client, tenant):
        """missing-costs (productos sin costo cargado) debe excluir borrados.
        Si no, aparecerían productos borrados en el editor inline."""
        # Producto borrado SIN costo (vamos a chequear que NO aparezca)
        sin_costo_borrado = Product.objects.create(
            tenant=tenant, name="Sin costo borrado", price=1000, cost=0,
            deleted_at=timezone.now(), is_active=False,
        )
        sin_costo_vivo = Product.objects.create(
            tenant=tenant, name="Sin costo vivo", price=1000, cost=0,
        )
        r = auth_client.get("/api/catalog/products/missing-costs/")
        assert r.status_code == 200
        names = [p["name"] for p in r.data["results"]]
        assert "Sin costo vivo" in names
        assert "Sin costo borrado" not in names

    def test_assign_barcode_to_deleted_returns_404(self, auth_client):
        """No se puede asignar un código de barras a un producto borrado."""
        r = auth_client.post(f"/api/catalog/products/{self.borrado.id}/assign-barcode/", {
            "code": "7800009999999",
        }, format="json")
        assert r.status_code == 404


@pytest.mark.django_db
class TestSalesHistoryShowsDeletedProduct:
    """El historial de ventas DEBE seguir mostrando el nombre del producto
    aunque éste haya sido borrado del catálogo. Es la razón principal del
    diseño con borrado lógico (vs físico)."""

    def test_sale_line_keeps_product_relation_after_delete(self, db, tenant, store, owner, warehouse_a):
        """Si un producto se vendió y después se borró, la SaleLine todavía
        puede acceder a Product.name vía la FK (que pasa por _base_manager
        = all_objects, así que SÍ trae el borrado)."""
        from sales.models import Sale, SaleLine
        from decimal import Decimal
        from django.utils import timezone

        prod = Product.objects.create(tenant=tenant, name="Latte", price=3000, cost=500)
        sale = Sale.objects.create(
            tenant=tenant, store=store, warehouse=warehouse_a, created_by=owner,
            sale_number=12345,
            total=Decimal("3000.00"), subtotal=Decimal("3000.00"),
        )
        line = SaleLine.objects.create(
            tenant=tenant, sale=sale, product=prod,
            qty=Decimal("1.000"), unit_price=Decimal("3000.00"),
            line_total=Decimal("3000.00"), line_cost=Decimal("500.000"),
        )
        # Borrar el producto
        prod.deleted_at = timezone.now()
        prod.is_active = False
        prod.save()

        # SaleLine sigue accediendo al producto vía FK (usa _base_manager =
        # all_objects, configurado vía Meta.base_manager_name).
        line.refresh_from_db()
        assert line.product.id == prod.id
        assert line.product.name == "Latte"  # ← lo crítico: el nombre sigue accesible
        assert line.product.deleted_at is not None  # marcado como borrado


@pytest.mark.django_db
class TestPosRaceWithDeletedProduct:
    """Race condition: cajero abre el POS con un producto en el carrito,
    OTRO usuario borra ese producto desde otro dispositivo, cajero cobra.
    El sistema debe rechazar la venta con un error claro, no completarla
    silenciosamente con un producto borrado."""

    def test_create_sale_with_deleted_product_raises_validation_error(
        self, db, tenant, store, owner, warehouse_a
    ):
        """create_sale debe rechazar líneas con productos borrados."""
        from sales.services import create_sale, SaleValidationError
        from decimal import Decimal

        prod = Product.objects.create(tenant=tenant, name="Latte", price=3000, cost=500)
        # El producto fue borrado entre que el cajero lo agregó al carrito y cobró
        prod.deleted_at = timezone.now()
        prod.is_active = False
        prod.save()

        with pytest.raises(SaleValidationError):
            create_sale(
                user=owner,
                tenant_id=tenant.id,
                store_id=store.id,
                warehouse_id=warehouse_a.id,
                lines_in=[{
                    "product_id": prod.id,
                    "qty": "1",
                    "unit_price": "3000",
                }],
                payments_in=[{"method": "cash", "amount": "3000"}],
            )


@pytest.mark.django_db
class TestForecastIgnoresDeletedProducts:
    """Forecast y reportes no deben contar/predecir productos borrados."""

    def test_dashboard_kpis_excludes_deleted_from_total_active(self, db, tenant, warehouse_a):
        """KPIs del dashboard de forecast cuentan productos activos.
        Borrados NO deben contar."""
        from forecast.services import get_dashboard_kpis

        Product.objects.create(tenant=tenant, name="Vivo 1", price=100)
        Product.objects.create(tenant=tenant, name="Vivo 2", price=200)
        Product.objects.create(
            tenant=tenant, name="Borrado", price=300,
            deleted_at=timezone.now(), is_active=False,
        )
        kpis = get_dashboard_kpis(tenant_id=tenant.id, warehouse_ids=[warehouse_a.id])
        # products_with_forecast + products_without_forecast = total_active
        # debe ser 2 (los vivos), no 3.
        total = kpis["products_with_forecast"] + kpis["products_without_forecast"]
        assert total == 2, f"Debería contar 2 productos vivos, contó {total}"
