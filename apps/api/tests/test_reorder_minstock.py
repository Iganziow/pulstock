"""
Reorden por mínimo (jun 2026): insumos sin demanda de venta (papel higiénico,
cloro, servilletas) se consumen por uso, no por venta → no tienen forecast →
nunca aparecían en sugerencias. Ahora, si on_hand < min_stock, se sugiere
reponer SOLO hasta el mínimo, independiente del forecast.
"""
import pytest
from decimal import Decimal
from datetime import date

from catalog.models import Product, Recipe
from inventory.models import StockItem
from forecast.models import SuggestionLine
from forecast.services import generate_suggestions


def _consumable(tenant, name, min_stock):
    return Product.objects.create(
        tenant=tenant, name=name, price=Decimal("500"),
        is_active=True, min_stock=Decimal(str(min_stock)),
    )


def _stock(tenant, warehouse, product, on_hand, avg_cost="300"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(on_hand)), avg_cost=Decimal(str(avg_cost)),
        stock_value=Decimal(str(on_hand)) * Decimal(str(avg_cost)),
    )


def _pending_lines(tenant, product):
    return SuggestionLine.objects.filter(
        suggestion__tenant=tenant, suggestion__status="PENDING", product_id=product.id,
    )


@pytest.mark.django_db
def test_consumable_below_min_appears(tenant, store, warehouse):
    p = _consumable(tenant, "Papel higiénico", 10)
    _stock(tenant, warehouse, p, on_hand=5)
    generate_suggestions(tenant, date.today(), 14, 14)
    lines = _pending_lines(tenant, p)
    assert lines.count() == 1, "el insumo bajo el mínimo debe aparecer en sugerencias"
    line = lines.first()
    # Repone SOLO hasta el mínimo: 10 - 5 = 5
    assert line.suggested_qty == Decimal("5.000"), line.suggested_qty
    assert "mínimo" in line.reasoning.lower()
    # on_hand=5, mínimo=10 → no es <50% → MEDIUM
    assert line.suggestion.priority == "MEDIUM"


@pytest.mark.django_db
def test_consumable_out_of_stock_is_critical(tenant, store, warehouse):
    p = _consumable(tenant, "Cloro gel", 12)
    _stock(tenant, warehouse, p, on_hand=0)
    generate_suggestions(tenant, date.today(), 14, 14)
    line = _pending_lines(tenant, p).first()
    assert line is not None
    assert line.suggested_qty == Decimal("12.000")  # 12 - 0
    assert line.suggestion.priority == "CRITICAL"  # sin stock


@pytest.mark.django_db
def test_consumable_above_min_not_suggested(tenant, store, warehouse):
    p = _consumable(tenant, "Servilletas", 5)
    _stock(tenant, warehouse, p, on_hand=8)  # por encima del mínimo
    generate_suggestions(tenant, date.today(), 14, 14)
    assert _pending_lines(tenant, p).count() == 0


@pytest.mark.django_db
def test_min_stock_zero_no_suggestion(tenant, store, warehouse):
    p = _consumable(tenant, "Bolsa 50x70", 0)  # sin mínimo configurado
    _stock(tenant, warehouse, p, on_hand=0)
    generate_suggestions(tenant, date.today(), 14, 14)
    assert _pending_lines(tenant, p).count() == 0


@pytest.mark.django_db
def test_recipe_product_below_min_excluded(tenant, store, warehouse):
    # Producto con receta activa → se arma, no se compra → no reorden por mínimo.
    p = _consumable(tenant, "Latte", 10)
    Recipe.objects.create(tenant=tenant, product=p, is_active=True)
    _stock(tenant, warehouse, p, on_hand=2)
    generate_suggestions(tenant, date.today(), 14, 14)
    assert _pending_lines(tenant, p).count() == 0
