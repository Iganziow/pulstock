"""
Tests para los filtros agregados a /api/catalog/products/.

Mario lo pidió: "en el apartado de categorías poder filtrar por
distintos motivos que ya usemos como por ejemplo categoría sku etc".

El search por SKU/nombre/barcode ya estaba (param `q`); estos tests
cubren los nuevos params: `category` y `is_active`.
"""
import pytest
from catalog.models import Product, Category


@pytest.mark.django_db
class TestProductFilters:

    @pytest.fixture(autouse=True)
    def _setup(self, tenant):
        # Dos categorías y 4 productos repartidos entre ellas, con
        # distintos estados activos para cubrir todas las combinaciones.
        self.cat_bebidas = Category.objects.create(tenant=tenant, name="Bebidas", code="BEB")
        self.cat_postres = Category.objects.create(tenant=tenant, name="Postres", code="POS")

        Product.objects.create(tenant=tenant, name="Café", sku="CAF1", price=2000, is_active=True, category=self.cat_bebidas)
        Product.objects.create(tenant=tenant, name="Té", sku="TE1", price=1800, is_active=False, category=self.cat_bebidas)
        Product.objects.create(tenant=tenant, name="Brownie", sku="BRO1", price=2500, is_active=True, category=self.cat_postres)
        Product.objects.create(tenant=tenant, name="Cheesecake", sku="CHC1", price=3000, is_active=True, category=None)

    def test_no_filters_returns_all(self, api_client):
        r = api_client.get("/api/catalog/products/")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 4

    def test_filter_by_category(self, api_client):
        r = api_client.get(f"/api/catalog/products/?category={self.cat_bebidas.id}")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        names = sorted(p["name"] for p in results)
        assert names == ["Café", "Té"]

    def test_filter_by_other_category(self, api_client):
        r = api_client.get(f"/api/catalog/products/?category={self.cat_postres.id}")
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert names == ["Brownie"]

    def test_filter_by_is_active_true(self, api_client):
        r = api_client.get("/api/catalog/products/?is_active=true")
        results = r.data.get("results", r.data)
        names = sorted(p["name"] for p in results)
        assert names == ["Brownie", "Café", "Cheesecake"]

    def test_filter_by_is_active_false(self, api_client):
        r = api_client.get("/api/catalog/products/?is_active=false")
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert names == ["Té"]

    def test_filter_by_is_active_with_1_0(self, api_client):
        # Acepta también 1/0 además de true/false (formato común en URL params).
        r1 = api_client.get("/api/catalog/products/?is_active=1")
        r0 = api_client.get("/api/catalog/products/?is_active=0")
        names1 = sorted(p["name"] for p in r1.data.get("results", r1.data))
        names0 = [p["name"] for p in r0.data.get("results", r0.data)]
        assert names1 == ["Brownie", "Café", "Cheesecake"]
        assert names0 == ["Té"]

    def test_combine_filters(self, api_client):
        # Activos + categoría bebidas = solo Café (Té es inactivo, Brownie es postres).
        r = api_client.get(f"/api/catalog/products/?category={self.cat_bebidas.id}&is_active=true")
        results = r.data.get("results", r.data)
        names = [p["name"] for p in results]
        assert names == ["Café"]

    def test_combine_q_with_filters(self, api_client):
        # Búsqueda "ca" + categoría postres → solo Cheesecake... no, Cheesecake
        # es categoría None. Con "ca" + activos → Café, Cheesecake.
        r = api_client.get("/api/catalog/products/?q=c&is_active=true")
        results = r.data.get("results", r.data)
        names = sorted(p["name"] for p in results)
        # "c" matches "Café" y "Cheesecake" (ambos activos). Brownie no
        # contiene "c" en name ni sku ("BRO1").
        assert "Café" in names
        assert "Cheesecake" in names
        assert "Té" not in names  # inactivo

    def test_invalid_category_id_ignored(self, api_client):
        # Si category no es número, se ignora silenciosamente (no 400).
        r = api_client.get("/api/catalog/products/?category=abc")
        assert r.status_code == 200
        results = r.data.get("results", r.data)
        assert len(results) == 4  # todos

    def test_invalid_is_active_value_ignored(self, api_client):
        # is_active=maybe → ignorado, devuelve todos.
        r = api_client.get("/api/catalog/products/?is_active=maybe")
        results = r.data.get("results", r.data)
        assert len(results) == 4

    def test_nonexistent_category_returns_empty(self, api_client):
        r = api_client.get("/api/catalog/products/?category=99999")
        results = r.data.get("results", r.data)
        assert len(results) == 0
