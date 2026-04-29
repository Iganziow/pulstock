"""
Tests para 2 fixes:

§2 — forecast.aggregate_daily_sales ahora usa StockMove (no SaleLine) para
qty_sold. Antes: si un producto se vendía directo Y como ingrediente, el
forecast solo contaba el directo. Ahora cuenta ambos correctamente.

§7 — sales.recipes._load_all_active_recipes acepta lock=True para
select_for_update. Llamado desde create_sale, evita race condition entre
edición de receta y venta concurrente. Crítico cuando hay múltiples POS.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from catalog.models import Product, Recipe, RecipeLine, Unit
from forecast.models import DailySales
from inventory.models import StockItem, StockMove
from sales.models import Sale


def _u(tenant, code, family="COUNT"):
    return Unit.objects.create(
        tenant=tenant, code=code, name=code,
        family=family, is_base=True, conversion_factor=Decimal("1"),
    )


def _p(tenant, name, unit_obj, sku=None):
    return Product.objects.create(
        tenant=tenant, name=name, sku=sku or name.replace(" ", "_").upper(),
        price=Decimal("1000"), unit_obj=unit_obj,
    )


def _stock(tenant, warehouse, product, qty="1000", avg_cost="1"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        stock_value=(Decimal(str(qty)) * Decimal(str(avg_cost))).quantize(Decimal("0.001")),
    )


def _backdate_sale(sale_id):
    """Mueve created_at de Sale + StockMoves a ayer mediodía local para que
    el aggregate los procese sin issues de TZ."""
    yesterday = (timezone.now() - timedelta(days=1)).date()
    yesterday_noon = timezone.make_aware(datetime.combine(yesterday, time(12, 0)))
    Sale.objects.filter(id=sale_id).update(created_at=yesterday_noon)
    StockMove.objects.filter(ref_id=sale_id).update(created_at=yesterday_noon)
    return yesterday


# ─── §2: Forecast subcuenta de ingredientes mixtos ───────────────────────


@pytest.mark.django_db
class TestForecastQtySoldFromStockMove:
    """qty_sold de DailySales debe reflejar la demanda TOTAL del producto:
    venta directa + consumo via recetas (recursivo)."""

    def test_pure_direct_product_unchanged(self, api_client, tenant, warehouse):
        """Producto solo vendido directo (sin receta, sin ser ingrediente):
        qty_sold = SaleLine.qty (igual que antes)."""
        un = _u(tenant, "UN")
        p = _p(tenant, "Galleta", un)
        _stock(tenant, warehouse, p, qty="100", avg_cost="500")

        resp = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": p.id, "qty": "5", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 5000}],
        }, format="json")
        assert resp.status_code == 201

        yesterday = _backdate_sale(resp.data["id"])
        call_command("aggregate_daily_sales", date=yesterday.isoformat(), tenant=tenant.id)

        ds = DailySales.objects.get(tenant=tenant, product=p, warehouse=warehouse, date=yesterday)
        assert ds.qty_sold == Decimal("5.000")

    def test_pure_ingredient_product_counts_recipe_consumption(
        self, api_client, tenant, warehouse,
    ):
        """Producto que solo es ingrediente (no se vende directo): qty_sold =
        consumo via StockMove."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche solo ing", ml)
        cap = _p(tenant, "Cap solo dir", un)
        _stock(tenant, warehouse, leche, qty="1000", avg_cost="1")
        _stock(tenant, warehouse, cap, qty="50", avg_cost="100")
        recipe = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche,
                                   qty=Decimal("150"), unit=ml)

        resp = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }, format="json")
        assert resp.status_code == 201

        yesterday = _backdate_sale(resp.data["id"])
        call_command("aggregate_daily_sales", date=yesterday.isoformat(), tenant=tenant.id)

        ds = DailySales.objects.get(tenant=tenant, product=leche, warehouse=warehouse, date=yesterday)
        assert ds.qty_sold == Decimal("150.000"), \
            f"Esperado qty_sold=150 para leche (consumo via receta), obtuvo {ds.qty_sold}"
        # Revenue=0 (la leche no se vendió directa, no tiene revenue propio)
        assert ds.revenue == Decimal("0.00")

    def test_mixed_product_sums_direct_and_recipe(
        self, api_client, tenant, warehouse,
    ):
        """BUG §2: leche se vende directa (5 ML) Y como ingrediente
        (150 ML via cap) → qty_sold = 5 + 150 = 155.

        Antes del fix: qty_sold = 5 (solo el directo, ingrediente excluido
        porque pertenecía a direct_sold_ids)."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche mixta", ml)
        cap = _p(tenant, "Cap mixto", un)
        _stock(tenant, warehouse, leche, qty="1000", avg_cost="1")
        _stock(tenant, warehouse, cap, qty="50", avg_cost="100")
        recipe = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche,
                                   qty=Decimal("150"), unit=ml)

        # Venta 1: leche directa, 5 ML
        p1 = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": leche.id, "qty": "5", "unit_price": "100"}],
            "payments": [{"method": "cash", "amount": 500}],
        }, format="json")
        assert p1.status_code == 201

        # Venta 2: cap (consume 150 ML leche via receta)
        p2 = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }, format="json")
        assert p2.status_code == 201

        _backdate_sale(p1.data["id"])
        yesterday = _backdate_sale(p2.data["id"])
        call_command("aggregate_daily_sales", date=yesterday.isoformat(), tenant=tenant.id)

        ds = DailySales.objects.get(tenant=tenant, product=leche, warehouse=warehouse, date=yesterday)
        assert ds.qty_sold == Decimal("155.000"), \
            f"BUG §2: qty_sold debería ser 155 (5 directo + 150 via receta), obtuvo {ds.qty_sold}"
        # Revenue solo del directo: 5 × 100 = 500
        assert ds.revenue == Decimal("500.00"), \
            "Revenue debe ser solo del directo (500), no incluir ingrediente"


# ─── §7: Race lock en recetas ────────────────────────────────────────────


@pytest.mark.django_db
class TestRecipeLockDuringSale:
    """Cuando se llama desde create_sale, expand_recipes debe usar
    select_for_update sobre las recetas para serializar contra ediciones
    concurrentes."""

    def test_load_recipes_with_lock_inside_transaction_works(
        self, tenant, warehouse,
    ):
        """Llamar _load_all_active_recipes(lock=True) dentro de transaction.atomic
        no debe romper el flujo (en SQLite es no-op, en Postgres bloquea)."""
        from sales.recipes import _load_all_active_recipes
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche L1", un)
        cap = _p(tenant, "Cap L1", un)
        recipe = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche,
                                   qty=Decimal("150"), unit=un)

        with transaction.atomic():
            recipes = _load_all_active_recipes(tenant.id, lock=True)
            assert cap.id in recipes
            assert recipes[cap.id].lines.count() == 1

    def test_load_recipes_without_lock_works_outside_transaction(
        self, tenant, warehouse,
    ):
        """Sin lock, sin transaction.atomic: debe funcionar (uso read-only)."""
        from sales.recipes import _load_all_active_recipes
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche L2", un)
        cap = _p(tenant, "Cap L2", un)
        recipe = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche,
                                   qty=Decimal("150"), unit=un)

        # Sin lock, sin transaction.atomic
        recipes = _load_all_active_recipes(tenant.id, lock=False)
        assert cap.id in recipes

    def test_create_sale_with_recipe_uses_lock_path(
        self, api_client, tenant, warehouse,
    ):
        """E2E: una venta con producto con receta ejecuta el path lock=True
        (vía create_sale) sin romper el flujo. Validamos resultado, no race."""
        ml = _u(tenant, "ML", family="VOLUME")
        un = _u(tenant, "UN")
        leche = _p(tenant, "Leche lock e2e", ml)
        cap = _p(tenant, "Cap lock e2e", un)
        _stock(tenant, warehouse, leche, qty="1000", avg_cost="1")
        recipe = Recipe.objects.create(tenant=tenant, product=cap, is_active=True)
        RecipeLine.objects.create(tenant=tenant, recipe=recipe, ingredient=leche,
                                   qty=Decimal("150"), unit=ml)

        resp = api_client.post("/api/sales/sales/", {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": cap.id, "qty": "1", "unit_price": "3000"}],
            "payments": [{"method": "cash", "amount": 3000}],
        }, format="json")
        assert resp.status_code == 201
        si = StockItem.objects.get(product=leche, warehouse=warehouse)
        assert si.on_hand == Decimal("850.000")  # 1000 - 150
