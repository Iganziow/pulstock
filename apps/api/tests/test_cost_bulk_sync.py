"""
Tests del fix de sincronización de costos (09/05/26).

Bug reportado por Mario: cuando editaba un costo desde
/dashboard/forecast/costos (Predicción → Costos faltantes), el cambio
NO se reflejaba en el cálculo de utilidad. Tenía que volver al catálogo
y editarlo de nuevo — doble trabajo.

Causa: CostBulkUpdateView solo escribía Product.cost (legacy), pero
todos los cálculos importantes leen StockItem.avg_cost.

Fix: el endpoint ahora escribe StockItem.avg_cost en TODAS las bodegas
del producto (decisión de Mario), además de Product.cost para
compatibilidad con el listado missing-costs.
"""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from catalog.models import Product
from inventory.models import StockItem, StockMove
from core.models import Warehouse


@pytest.fixture
def warehouse_b(db, tenant, store):
    """Segunda bodega para verificar el "todas las bodegas" del fix."""
    return Warehouse.objects.create(tenant=tenant, store=store, name="Bodega B")


@pytest.fixture
def product_in_two_warehouses(db, tenant, warehouse, warehouse_b):
    """Producto con StockItem en bodega A y bodega B, cada una con su
    propio avg_cost. Simula la realidad de Marbrava (sucursal Local
    Principal + otra sucursal)."""
    p = Product.objects.create(
        tenant=tenant, name="Café molido", price=Decimal("3000"),
        is_active=True, cost=Decimal("0"),
    )
    StockItem.objects.create(
        tenant=tenant, product=p, warehouse=warehouse,
        on_hand=Decimal("100"), avg_cost=Decimal("999"),  # valor viejo
    )
    StockItem.objects.create(
        tenant=tenant, product=p, warehouse=warehouse_b,
        on_hand=Decimal("50"), avg_cost=Decimal("999"),
    )
    return p


@pytest.mark.django_db
class TestCostBulkUpdateSyncsAvgCost:
    """El endpoint que usa Mario en /dashboard/forecast/costos."""

    def test_updates_avg_cost_in_all_warehouses(
        self, api_client, product_in_two_warehouses, tenant,
    ):
        """Mario sube un costo desde Predicción. Debe afectar AMBAS
        bodegas del producto (decisión 09/05/26)."""
        resp = api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": product_in_two_warehouses.id, "cost": "30"},
            ],
        }, format="json")

        assert resp.status_code == 200, resp.content
        assert resp.json()["updated"] == 1

        # Las dos bodegas tienen el nuevo avg_cost
        items = StockItem.objects.filter(
            tenant=tenant, product=product_in_two_warehouses,
        )
        assert items.count() == 2
        for si in items:
            assert si.avg_cost == Decimal("30.000"), (
                f"Bodega {si.warehouse_id}: avg_cost={si.avg_cost} "
                f"esperaba 30. El fix de 'todas las bodegas' falló."
            )

    def test_also_updates_product_cost_legacy(
        self, api_client, product_in_two_warehouses,
    ):
        """Product.cost se sigue actualizando para el listado missing-costs."""
        api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": product_in_two_warehouses.id, "cost": "30"},
            ],
        }, format="json")
        product_in_two_warehouses.refresh_from_db()
        assert product_in_two_warehouses.cost == Decimal("30")

    def test_creates_kardex_entries(
        self, api_client, product_in_two_warehouses, tenant,
    ):
        """Cada cambio de avg_cost queda registrado en StockMove (auditoría)."""
        api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": product_in_two_warehouses.id, "cost": "30"},
            ],
        }, format="json")
        moves = StockMove.objects.filter(
            tenant=tenant, product=product_in_two_warehouses,
            reason="cost_only",
        )
        # Una entrada por bodega
        assert moves.count() == 2
        for m in moves:
            assert m.qty == Decimal("0.000")
            assert m.unit_cost == Decimal("30.000")
            assert m.move_type == "ADJ"

    def test_creates_stockitem_if_product_has_none(
        self, api_client, tenant, warehouse,
    ):
        """Si el producto NO tiene StockItem en ninguna bodega, se crea
        uno en la bodega del usuario (no nos quedamos con el costo solo
        en Product.cost, sin efecto en cálculos)."""
        p = Product.objects.create(
            tenant=tenant, name="Producto nuevo sin stock",
            price=Decimal("1000"), is_active=True, cost=Decimal("0"),
        )
        assert StockItem.objects.filter(product=p).count() == 0

        resp = api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [{"product_id": p.id, "cost": "250"}],
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

        # Se creó un StockItem con el costo aplicado
        items = StockItem.objects.filter(product=p)
        assert items.count() == 1
        assert items.first().avg_cost == Decimal("250.000")

    def test_negative_cost_rejected(
        self, api_client, product_in_two_warehouses,
    ):
        resp = api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": product_in_two_warehouses.id, "cost": "-100"},
            ],
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0
        assert len(resp.json()["errors"]) == 1

    def test_cross_tenant_rejected(self, api_client, db, warehouse):
        """Usuario tenant A no puede actualizar costo de producto tenant B."""
        from core.models import Tenant
        from stores.models import Store
        t2 = Tenant.objects.create(name="Otro", slug="otro-09")
        t2._skip_subscription = True
        s2 = Store.objects.create(tenant=t2, name="Otro Local")
        p_ajeno = Product.objects.create(
            tenant=t2, name="Producto ajeno", price=Decimal("100"),
            is_active=True,
        )

        resp = api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [{"product_id": p_ajeno.id, "cost": "999"}],
        }, format="json")
        assert resp.status_code == 200
        # NO se actualizó nada del tenant ajeno
        p_ajeno.refresh_from_db()
        assert p_ajeno.cost == Decimal("0"), "FUGA DE TENANT — costo cross-tenant"

    def test_bulk_update_multiple_products(
        self, api_client, tenant, warehouse,
    ):
        """Varios productos en un solo request — happy path completo."""
        productos = []
        for i, (name, new_cost) in enumerate([
            ("Latte", "1200"), ("Brownie", "800"), ("Espresso", "600"),
        ]):
            p = Product.objects.create(
                tenant=tenant, name=name, price=Decimal("3000"),
                is_active=True, cost=Decimal("0"),
            )
            StockItem.objects.create(
                tenant=tenant, product=p, warehouse=warehouse,
                on_hand=Decimal("10"), avg_cost=Decimal("0"),
            )
            productos.append((p, new_cost))

        resp = api_client.post("/api/catalog/products/costs/bulk/", {
            "updates": [
                {"product_id": p.id, "cost": c} for p, c in productos
            ],
        }, format="json")
        assert resp.status_code == 200
        assert resp.json()["updated"] == 3

        for p, expected in productos:
            si = StockItem.objects.get(product=p, warehouse=warehouse)
            assert si.avg_cost == Decimal(expected + ".000"), (
                f"{p.name}: esperaba {expected}, obtuve {si.avg_cost}"
            )
