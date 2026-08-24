"""
tests/test_costo_de_receta.py — cuánto cuesta de verdad un capuccino.

`Product.cost` está en cero para todo lo que se prepara en la barra: un
capuccino no se compra, se arma. En Marbrava eso es media carta, y la Lista de
Precios mostraba "100,0% de margen" en verde para todos ellos.

El costo real vive en los ingredientes, y el motor de ventas ya sabe
calcularlo. Traerlo a la pantalla de precios parece obvio, pero tiene una
trampa que es la razón de la mitad de estos tests:

**Un ingrediente sin costo aporta CERO en silencio.**

Un capuccino al que le falta el costo de la leche daría $300 en vez de $800.
Ese número es verosímil —nadie sospecha de $300— y el margen que sale de ahí
está inflado sin que nada lo delate. Sería PEOR que mostrar 100%, que al menos
da desconfianza.

Por eso el costo de receta solo se muestra cuando está completo, y cuando no,
se dice qué ingrediente falta.
"""
from decimal import Decimal

import pytest

from catalog.models import Product, Recipe, RecipeLine
from catalog.recipe_costing import costos_de_receta
from inventory.models import StockItem

D = Decimal


@pytest.fixture
def cafeteria(db, tenant, warehouse):
    """Un capuccino de verdad: leche y café, cada uno con su costo."""
    def ingrediente(nombre, costo):
        p = Product.objects.create(tenant=tenant, name=nombre, unit="UN")
        StockItem.objects.create(
            tenant=tenant, warehouse=warehouse, product=p,
            on_hand=D("100"), avg_cost=D(str(costo)),
        )
        return p

    leche = ingrediente("Leche", 500)
    cafe = ingrediente("Café", 300)

    capuccino = Product.objects.create(
        tenant=tenant, name="Capuccino", unit="UN", price=D("3200"), cost=D("0"),
    )
    receta = Recipe.objects.create(tenant=tenant, product=capuccino)
    RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=leche, qty=D("1"))
    RecipeLine.objects.create(tenant=tenant, recipe=receta, ingredient=cafe, qty=D("1"))
    return {"tenant": tenant, "warehouse": warehouse, "capuccino": capuccino,
            "leche": leche, "cafe": cafe}


@pytest.mark.django_db
class TestCuandoLaRecetaEstaCompleta:
    def test_suma_el_costo_de_los_ingredientes(self, cafeteria):
        r = costos_de_receta(cafeteria["tenant"].id)[cafeteria["capuccino"].id]
        assert r["costo"] == D("800.000")
        assert r["completo"] is True

    def test_ese_costo_reemplaza_al_cero_del_producto(self, api_client, cafeteria):
        """LO QUE ARREGLA. Antes: costo $0 → margen 100% en verde."""
        r = api_client.get("/api/catalog/products/prices/")
        fila = next(f for f in r.json()["results"]
                    if f["id"] == cafeteria["capuccino"].id)

        assert float(fila["cost"]) == 800
        assert fila["cost_source"] == "receta"
        # 3200 de precio, 800 de costo → 75%
        assert float(fila["margin_pct"]) == pytest.approx(75.0, abs=0.1)


@pytest.mark.django_db
class TestCuandoFaltaUnIngrediente:
    """LA PARTE QUE IMPORTA. Un costo parcial es más peligroso que ninguno."""

    def test_no_muestra_un_costo_a_medias(self, api_client, cafeteria):
        StockItem.objects.filter(product=cafeteria["leche"]).update(avg_cost=D("0"))
        cafeteria["leche"].cost = D("0")
        cafeteria["leche"].save(update_fields=["cost"])

        fila = next(f for f in api_client.get("/api/catalog/products/prices/").json()["results"]
                    if f["id"] == cafeteria["capuccino"].id)

        assert float(fila["cost"]) == 0, (
            "mostró $300 (solo el café) como si fuera el costo del capuccino: "
            "verosímil, incompleto, y con el margen inflado"
        )
        assert fila["margin_pct"] is None, "un margen sobre un costo parcial es falso"

    def test_dice_QUE_ingrediente_falta(self, api_client, cafeteria):
        """Sin esto es un dato; con esto es una acción. En producción son
        cinco ingredientes los que bloquean las diez recetas incompletas."""
        StockItem.objects.filter(product=cafeteria["leche"]).update(avg_cost=D("0"))
        cafeteria["leche"].cost = D("0")
        cafeteria["leche"].save(update_fields=["cost"])

        fila = next(f for f in api_client.get("/api/catalog/products/prices/").json()["results"]
                    if f["id"] == cafeteria["capuccino"].id)
        assert fila["cost_source"] == "receta_incompleta"
        assert "Leche" in fila["missing_ingredients"]


@pytest.mark.django_db
class TestLoQueNoDebeCambiar:
    def test_un_producto_sin_receta_conserva_su_costo(self, api_client, tenant, warehouse):
        """Una botella de agua se compra: su costo es el de compra."""
        agua = Product.objects.create(
            tenant=tenant, name="Agua", unit="UN", price=D("1500"), cost=D("640"),
        )
        fila = next(f for f in api_client.get("/api/catalog/products/prices/").json()["results"]
                    if f["id"] == agua.id)
        assert float(fila["cost"]) == 640
        assert fila["cost_source"] == "propio"
        assert float(fila["margin_pct"]) == pytest.approx(57.3, abs=0.1)

    def test_sin_costo_ni_receta_sigue_sin_margen(self, api_client, tenant):
        """El arreglo anterior no se pierde: sin costo no hay margen."""
        p = Product.objects.create(
            tenant=tenant, name="Sin nada", unit="UN", price=D("1000"), cost=D("0"),
        )
        fila = next(f for f in api_client.get("/api/catalog/products/prices/").json()["results"]
                    if f["id"] == p.id)
        assert fila["margin_pct"] is None

    def test_no_mira_recetas_de_otro_negocio(self, cafeteria, db):
        from core.models import Tenant

        otro = Tenant(name="Rival", slug="rival-recetas")
        otro._skip_subscription = True
        otro.save()
        assert costos_de_receta(otro.id) == {}
