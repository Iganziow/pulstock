"""
tests/test_catalogo_conteos.py — que el catálogo no mienta sobre sí mismo.

La pantalla de Catálogo mostraba, en producción:

    TOTAL 252  ·  ACTIVOS 46  ·  INACTIVOS 206

Cuando en la base había 242 activos y 10 inactivos. Le decía al dueño que
había dado de baja el 82% de su catálogo.

La causa era mezclar dos escalas distintas:

    activeCount = items.filter(p => p.is_active).length   // la PÁGINA (50)
    inactivos   = totalCount - activeCount                // el TOTAL (252)

O sea: total global menos los activos de la primera página. Un número que no
significa nada, y que empeora al pasar de página.

Solo el servidor puede contar sobre el conjunto completo, así que el conteo
se hace acá y el frontend lo muestra.
"""
import pytest

from catalog.models import Product


@pytest.mark.django_db
class TestElCatalogoSeCuentaEntero:
    def _catalogo(self, tenant, activos, inactivos):
        for i in range(activos):
            Product.objects.create(tenant=tenant, name=f"Activo {i:03d}", is_active=True)
        for i in range(inactivos):
            Product.objects.create(tenant=tenant, name=f"Baja {i:03d}", is_active=False)

    def test_cuenta_todo_el_catalogo_no_solo_la_pagina(self, api_client, tenant):
        """EL BUG. Con más productos que una página, contar lo visible da un
        número que se parece al correcto pero no lo es."""
        self._catalogo(tenant, activos=120, inactivos=8)

        r = api_client.get("/api/catalog/products/?page=1")
        assert r.status_code == 200, r.content
        d = r.json()

        assert d["active_count"] == 120, (
            f"contó {d['active_count']} activos: está mirando solo la página"
        )
        assert d["inactive_count"] == 8

    def test_los_dos_conteos_suman_el_total(self, api_client, tenant):
        """Si no suman, la pantalla se contradice sola."""
        self._catalogo(tenant, activos=30, inactivos=12)
        d = api_client.get("/api/catalog/products/").json()
        assert d["active_count"] + d["inactive_count"] == d["count"]

    def test_no_cambian_al_pasar_de_pagina(self, api_client, tenant):
        """Antes empeoraban página a página: cada una tiene otra mezcla."""
        self._catalogo(tenant, activos=120, inactivos=8)
        p1 = api_client.get("/api/catalog/products/?page=1").json()
        p2 = api_client.get("/api/catalog/products/?page=2").json()
        assert (p1["active_count"], p1["inactive_count"]) == \
               (p2["active_count"], p2["inactive_count"])

    def test_un_filtro_de_busqueda_no_altera_el_conteo(self, api_client, tenant):
        """Las tarjetas describen el catálogo completo, no el resultado de la
        búsqueda. Si cambiaran al escribir, dejarían de ser una referencia."""
        self._catalogo(tenant, activos=30, inactivos=12)
        d = api_client.get("/api/catalog/products/?q=Activo 001").json()
        assert d["active_count"] == 30
        assert d["inactive_count"] == 12

    def test_no_cuenta_el_catalogo_de_otro_negocio(self, api_client, tenant, db):
        """El conteo consulta sin el filtro de estado: hay que confirmar que
        no perdió el filtro de tenant en el camino."""
        from core.models import Tenant

        otro = Tenant(name="Rival", slug="rival-conteo")
        otro._skip_subscription = True
        otro.save()
        Product.objects.create(tenant=otro, name="Ajeno", is_active=True)

        self._catalogo(tenant, activos=5, inactivos=2)
        d = api_client.get("/api/catalog/products/").json()
        assert d["active_count"] == 5, "se filtró un producto de otro negocio"
