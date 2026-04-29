"""
Tests para la expansión recursiva de recetas anidadas.

Bug encontrado en Marbrava 28/04/26: las recetas de Latte vainilla/caramelo/
iris cream/avellana usan "Latte" como ingrediente, y "Latte" tiene su propia
receta (200 ML leche + 8 GR café). Antes del fix recursivo, el sistema solo
expandía 1 nivel: descontaba "1 UN de Latte" en lugar de descontar leche +
café del stock real → divergencia entre stock físico y registrado, forecast
subestimado, márgenes mal calculados.

Cubre:
- Expansión 2 y 3 niveles
- Multiplicación correcta a través de niveles
- Detección de ciclos (auto-referencia, indirecto, profundo)
- Límite de profundidad (MAX_RECIPE_DEPTH)
- Conversión de unidades en cada nivel
- allow_negative_stock se respeta en ingredientes raw alcanzados por recursión
- Costo recursivo (suma todos los costos raw)
- Flujo end-to-end: venta real crea StockMoves correctos
"""
import pytest
from decimal import Decimal

from catalog.models import Product, Recipe, RecipeLine, Unit
from inventory.models import StockItem, StockMove
from sales.models import Sale, SaleLine
from sales.recipes import expand_recipes, compute_recipe_costs, MAX_RECIPE_DEPTH
from sales.services import SaleValidationError


# ─── Helpers ──────────────────────────────────────────────────────────────


def _unit(tenant, code, family="COUNT", base=True, factor="1"):
    return Unit.objects.create(
        tenant=tenant, code=code, name=code,
        family=family, is_base=base, conversion_factor=Decimal(factor),
    )


def _product(tenant, name, unit_obj, cost="0", allow_neg=False, sku=None):
    return Product.objects.create(
        tenant=tenant, name=name,
        sku=sku or name.replace(" ", "_").upper(),
        price=Decimal("1000"),
        cost=Decimal(cost),
        unit_obj=unit_obj,
        allow_negative_stock=allow_neg,
    )


def _stock(tenant, warehouse, product, qty, avg_cost="0"):
    return StockItem.objects.create(
        tenant=tenant, warehouse=warehouse, product=product,
        on_hand=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        stock_value=(Decimal(str(qty)) * Decimal(str(avg_cost))).quantize(Decimal("0.001")),
    )


def _recipe(tenant, product, lines):
    """lines: [(ingredient, qty, unit), ...]"""
    r = Recipe.objects.create(tenant=tenant, product=product, is_active=True)
    for ing, qty, unit in lines:
        RecipeLine.objects.create(
            tenant=tenant, recipe=r, ingredient=ing,
            qty=Decimal(str(qty)), unit=unit,
        )
    return r


def _agg(*items):
    """items: [(product, qty, unit_price), ...] → dict para expand_recipes"""
    return {
        p.id: {
            "qty": Decimal(str(qty)),
            "unit_price": Decimal(str(price)),
            "discount_type": "none",
            "discount_value": Decimal("0"),
            "promotion_id": None,
        }
        for p, qty, price in items
    }


# ─── Tests de expansión ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestRecursiveExpansion:
    """Casos puros de expand_recipes sin pasar por create_sale."""

    def test_one_level_baseline_unchanged(self, tenant, warehouse):
        """Receta simple (1 nivel) sigue funcionando igual que antes."""
        ml = _unit(tenant, "ML", family="VOLUME")
        un = _unit(tenant, "UN", family="COUNT")
        cap = _product(tenant, "Cappuccino", un)
        leche = _product(tenant, "Leche", ml, cost="1.2")
        _recipe(tenant, cap, [(leche, "150", ml)])

        expanded, all_recipes = expand_recipes(_agg((cap, 1, 3000)), tenant.id)

        assert len(expanded) == 1
        assert leche.id in expanded
        assert expanded[leche.id]["qty"] == Decimal("150")
        assert cap.id not in expanded  # el padre con receta NO está

    def test_two_level_expansion(self, tenant, warehouse):
        """Latte vainilla → Latte → leche + café. Todos los raw deben aparecer."""
        ml = _unit(tenant, "ML", family="VOLUME")
        gr = _unit(tenant, "GR", family="MASS")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche", ml, cost="1.2")
        cafe = _product(tenant, "Cafe", gr, cost="30")
        syrup = _product(tenant, "Syrup vainilla", ml, cost="5")
        latte = _product(tenant, "Latte", un)
        latte_v = _product(tenant, "Latte vainilla", un)

        # Latte: 200 ML leche + 8 GR cafe
        _recipe(tenant, latte, [(leche, "200", ml), (cafe, "8", gr)])
        # Latte vainilla: 1 UN Latte + 15 ML syrup
        _recipe(tenant, latte_v, [(latte, "1", un), (syrup, "15", ml)])

        expanded, _ = expand_recipes(_agg((latte_v, 1, 4500)), tenant.id)

        # Debe expandir TODO a raw: leche + cafe + syrup
        assert leche.id in expanded
        assert cafe.id in expanded
        assert syrup.id in expanded
        assert latte.id not in expanded, "Latte intermedio NO debe estar en expanded"
        assert latte_v.id not in expanded, "Latte vainilla NO debe estar en expanded"

        assert expanded[leche.id]["qty"] == Decimal("200")
        assert expanded[cafe.id]["qty"] == Decimal("8")
        assert expanded[syrup.id]["qty"] == Decimal("15")

    def test_two_level_multiplication(self, tenant, warehouse):
        """Vendo 2 Latte vainilla → debe descontar 400 ML leche, 16 GR café, 30 ML syrup."""
        ml = _unit(tenant, "ML", family="VOLUME")
        gr = _unit(tenant, "GR", family="MASS")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche", ml)
        cafe = _product(tenant, "Cafe", gr)
        syrup = _product(tenant, "Syrup", ml)
        latte = _product(tenant, "Latte", un)
        latte_v = _product(tenant, "Latte vainilla", un)
        _recipe(tenant, latte, [(leche, "200", ml), (cafe, "8", gr)])
        _recipe(tenant, latte_v, [(latte, "1", un), (syrup, "15", ml)])

        expanded, _ = expand_recipes(_agg((latte_v, 2, 4500)), tenant.id)

        assert expanded[leche.id]["qty"] == Decimal("400")
        assert expanded[cafe.id]["qty"] == Decimal("16")
        assert expanded[syrup.id]["qty"] == Decimal("30")

    def test_three_levels_deep(self, tenant, warehouse):
        """A (4 unid) → B (3 c/u) → C (2 c/u) → D (raw). Total: 4*3*2 = 24 D."""
        un = _unit(tenant, "UN", family="COUNT")
        d = _product(tenant, "D", un)
        c = _product(tenant, "C", un)
        b = _product(tenant, "B", un)
        a = _product(tenant, "A", un)
        _recipe(tenant, c, [(d, "2", un)])
        _recipe(tenant, b, [(c, "3", un)])
        _recipe(tenant, a, [(b, "5", un)])

        expanded, _ = expand_recipes(_agg((a, 4, 100)), tenant.id)

        assert d.id in expanded
        assert expanded[d.id]["qty"] == Decimal("4") * Decimal("5") * Decimal("3") * Decimal("2")
        assert b.id not in expanded
        assert c.id not in expanded

    def test_mixed_raw_and_recipe_at_same_level(self, tenant, warehouse):
        """A tiene receta con: 1 B (raw) + 1 C (con receta → D). expanded: B + D."""
        un = _unit(tenant, "UN", family="COUNT")
        d = _product(tenant, "D", un)
        b = _product(tenant, "B", un)
        c = _product(tenant, "C", un)
        a = _product(tenant, "A", un)
        _recipe(tenant, c, [(d, "10", un)])
        _recipe(tenant, a, [(b, "1", un), (c, "1", un)])

        expanded, _ = expand_recipes(_agg((a, 1, 100)), tenant.id)

        assert b.id in expanded
        assert d.id in expanded
        assert c.id not in expanded
        assert expanded[b.id]["qty"] == Decimal("1")
        assert expanded[d.id]["qty"] == Decimal("10")

    def test_same_raw_from_multiple_branches_accumulates(self, tenant, warehouse):
        """A → B (con leche) + C (con leche) → leche se suma de ambas ramas."""
        ml = _unit(tenant, "ML", family="VOLUME")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche", ml)
        b = _product(tenant, "B", un)
        c = _product(tenant, "C", un)
        a = _product(tenant, "A", un)
        _recipe(tenant, b, [(leche, "100", ml)])
        _recipe(tenant, c, [(leche, "50", ml)])
        _recipe(tenant, a, [(b, "1", un), (c, "1", un)])

        expanded, _ = expand_recipes(_agg((a, 1, 100)), tenant.id)

        assert expanded[leche.id]["qty"] == Decimal("150"), \
            "Leche debe sumar las dos ramas (100+50)"


# ─── Tests de detección de ciclos ────────────────────────────────────────


@pytest.mark.django_db
class TestCycleDetection:
    """Tests para asegurar que ciclos en recetas dan error claro y no
    cuelgan el servidor con stack overflow."""

    def test_self_reference_cycle(self, tenant, warehouse):
        """A → A (autoreferencia directa)."""
        un = _unit(tenant, "UN")
        a = _product(tenant, "A", un)
        _recipe(tenant, a, [(a, "1", un)])

        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(_agg((a, 1, 100)), tenant.id)
        # El mensaje puede ser "circular" o "profundidad" según qué se chequee primero
        msg = str(exc.value.detail).lower()
        assert "circular" in msg or "profundidad" in msg, \
            f"Mensaje inesperado: {msg}"

    def test_indirect_cycle_a_b_a(self, tenant, warehouse):
        """A → B → A."""
        un = _unit(tenant, "UN")
        a = _product(tenant, "A", un)
        b = _product(tenant, "B", un)
        _recipe(tenant, a, [(b, "1", un)])
        _recipe(tenant, b, [(a, "1", un)])

        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(_agg((a, 1, 100)), tenant.id)
        msg = str(exc.value.detail).lower()
        assert "circular" in msg or "profundidad" in msg

    def test_deep_cycle_a_b_c_a(self, tenant, warehouse):
        """A → B → C → A (ciclo de 3)."""
        un = _unit(tenant, "UN")
        a = _product(tenant, "A", un)
        b = _product(tenant, "B", un)
        c = _product(tenant, "C", un)
        _recipe(tenant, a, [(b, "1", un)])
        _recipe(tenant, b, [(c, "1", un)])
        _recipe(tenant, c, [(a, "1", un)])

        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(_agg((a, 1, 100)), tenant.id)
        msg = str(exc.value.detail).lower()
        assert "circular" in msg or "profundidad" in msg


@pytest.mark.django_db
class TestDepthLimit:
    """El límite de profundidad evita stack overflow incluso si la
    detección de ciclos fallara por algún edge case."""

    def test_chain_at_limit_works(self, tenant, warehouse):
        """Cadena lineal de exactamente MAX_RECIPE_DEPTH niveles funciona."""
        un = _unit(tenant, "UN")
        # Cadena: P0 ← P1 ← P2 ← ... ← P{MAX}
        # P0 es raw, P{MAX} es el vendido. Hay MAX recetas (P1..P_MAX).
        products = [_product(tenant, f"P{i}", un, sku=f"P{i}") for i in range(MAX_RECIPE_DEPTH + 1)]
        for i in range(1, MAX_RECIPE_DEPTH + 1):
            _recipe(tenant, products[i], [(products[i - 1], "1", un)])

        # Vender P_MAX expande exactamente MAX niveles → debe funcionar
        expanded, _ = expand_recipes(_agg((products[MAX_RECIPE_DEPTH], 1, 100)), tenant.id)
        assert products[0].id in expanded
        assert expanded[products[0].id]["qty"] == Decimal("1")

    def test_chain_over_limit_raises(self, tenant, warehouse):
        """Cadena más larga que MAX_RECIPE_DEPTH → error."""
        un = _unit(tenant, "UN")
        n = MAX_RECIPE_DEPTH + 2
        products = [_product(tenant, f"P{i}", un, sku=f"PD{i}") for i in range(n + 1)]
        for i in range(1, n + 1):
            _recipe(tenant, products[i], [(products[i - 1], "1", un)])

        with pytest.raises(SaleValidationError) as exc:
            expand_recipes(_agg((products[n], 1, 100)), tenant.id)
        assert "profundidad" in str(exc.value.detail).lower()


# ─── Tests de conversión de unidades a través de niveles ─────────────────


@pytest.mark.django_db
class TestNestedUnitConversion:
    """La conversión de unidad debe aplicarse en cada nivel correctamente."""

    def test_l_to_ml_in_nested_recipe(self, tenant, warehouse):
        """A pide 0.2 L de B; B (en ML) tiene receta con leche en ML.
        Cuando expanda B, el qty pasa a ML correctamente, y B descuenta su
        propia receta."""
        ml = _unit(tenant, "ML", family="VOLUME", base=True, factor="1")
        l = _unit(tenant, "L", family="VOLUME", base=False, factor="1000")
        un = _unit(tenant, "UN", family="COUNT")

        leche = _product(tenant, "Leche", ml)
        # B está en ML; receta de B = 200 ML leche
        b = _product(tenant, "B", ml)
        _recipe(tenant, b, [(leche, "200", ml)])

        # A está en UN; pide 0.2 L (= 200 ML) de B
        a = _product(tenant, "A", un)
        _recipe(tenant, a, [(b, "0.2", l)])

        expanded, _ = expand_recipes(_agg((a, 1, 100)), tenant.id)

        # 0.2 L de B = 200 ML de B → B tiene receta de 200 ML leche por
        # cada 1 ML de B (relación 1:1) → 200 * 200 = 40000 ML de leche
        # Wait, no: 200 ML de B (=200 unidades de B en su unidad ML).
        # B tiene receta "1 ML B = 200 ML leche" (1:200). Para 200 ML de B
        # → 200 * 200 = 40000 ML leche.
        # Esto es semánticamente raro pero es lo que sale del cálculo.
        assert leche.id in expanded
        assert expanded[leche.id]["qty"] == Decimal("200") * Decimal("200")


# ─── Tests de allow_negative_stock con recursión ─────────────────────────


@pytest.mark.django_db
class TestAllowNegativeWithRecursion:
    """allow_negative en ingrediente raw debe respetarse aunque el ingrediente
    haya llegado al expanded_agg vía recursión profunda."""

    def test_allow_negative_on_deep_raw_lets_sale_pass(
        self, api_client, tenant, store, warehouse,
    ):
        """A → B → leche con allow_negative=True y stock 0 → venta pasa."""
        ml = _unit(tenant, "ML", family="VOLUME")
        un = _unit(tenant, "UN", family="COUNT")

        leche = _product(tenant, "Leche", ml, cost="1", allow_neg=True)
        _stock(tenant, warehouse, leche, "0", avg_cost="1")

        b = _product(tenant, "B", un)
        _recipe(tenant, b, [(leche, "100", ml)])

        a = _product(tenant, "A", un)
        _recipe(tenant, a, [(b, "1", un)])

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": a.id, "qty": "1", "unit_price": "1000"}],
            "payments": [{"method": "cash", "amount": 1000}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data

        # Stock leche debe quedar en 0 (clampeado, no negativo)
        si = StockItem.objects.get(product=leche, warehouse=warehouse)
        assert si.on_hand == Decimal("0.000")


# ─── Tests de costo recursivo ────────────────────────────────────────────


@pytest.mark.django_db
class TestRecursiveCost:
    """compute_recipe_costs debe sumar recursivamente los costos de raw."""

    def test_cost_of_two_level_recipe(self, tenant, warehouse):
        """Latte vainilla = 200 ML leche ($1.2/ML) + 8 GR café ($30/GR) + 15 ML syrup ($5/ML)
        Esperado: 200*1.2 + 8*30 + 15*5 = 240 + 240 + 75 = 555"""
        ml = _unit(tenant, "ML", family="VOLUME")
        gr = _unit(tenant, "GR", family="MASS")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche", ml)
        cafe = _product(tenant, "Cafe", gr)
        syrup = _product(tenant, "Syrup", ml)
        latte = _product(tenant, "Latte", un)
        latte_v = _product(tenant, "Latte vainilla", un)
        _recipe(tenant, latte, [(leche, "200", ml), (cafe, "8", gr)])
        _recipe(tenant, latte_v, [(latte, "1", un), (syrup, "15", ml)])

        expanded, all_recipes = expand_recipes(_agg((latte_v, 1, 4500)), tenant.id)
        ingredient_costs = {
            leche.id: Decimal("1.2"),
            cafe.id: Decimal("30"),
            syrup.id: Decimal("5"),
        }
        recipe_costs = compute_recipe_costs(
            _agg((latte_v, 1, 4500)),
            all_recipes,
            ingredient_costs,
            tenant_id=tenant.id,
        )

        # 200*1.2 + 8*30 + 15*5 = 240 + 240 + 75 = 555
        assert latte_v.id in recipe_costs
        assert recipe_costs[latte_v.id] == Decimal("555.000")


# ─── Tests end-to-end (venta real, valida StockMoves) ────────────────────


@pytest.mark.django_db
class TestEndToEndNestedRecipeSale:
    """Test integral: vender un producto con receta anidada y verificar
    que los StockMoves se crean para los ingredientes RAW correctos."""

    def test_sale_decrements_raw_ingredients_via_recursion(
        self, api_client, tenant, store, warehouse,
    ):
        """Vendo Latte vainilla → StockMoves por leche, café, syrup. NO por Latte intermedio."""
        ml = _unit(tenant, "ML", family="VOLUME")
        gr = _unit(tenant, "GR", family="MASS")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche entera", ml, cost="1.2")
        cafe = _product(tenant, "Cafe tolva", gr, cost="30")
        syrup = _product(tenant, "Syrup vainilla", ml, cost="5")
        _stock(tenant, warehouse, leche, "1000", avg_cost="1.2")
        _stock(tenant, warehouse, cafe, "100", avg_cost="30")
        _stock(tenant, warehouse, syrup, "200", avg_cost="5")

        latte = _product(tenant, "Latte", un)
        latte_v = _product(tenant, "Latte vainilla", un)
        _recipe(tenant, latte, [(leche, "200", ml), (cafe, "8", gr)])
        _recipe(tenant, latte_v, [(latte, "1", un), (syrup, "15", ml)])

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": latte_v.id, "qty": "1", "unit_price": "4500"}],
            "payments": [{"method": "cash", "amount": 4500}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201, r.data
        sale_id = r.data["id"]

        # Stock debe haber bajado de los RAW
        leche_si = StockItem.objects.get(product=leche, warehouse=warehouse)
        cafe_si = StockItem.objects.get(product=cafe, warehouse=warehouse)
        syrup_si = StockItem.objects.get(product=syrup, warehouse=warehouse)
        assert leche_si.on_hand == Decimal("800.000")  # 1000 - 200
        assert cafe_si.on_hand == Decimal("92.000")    # 100 - 8
        assert syrup_si.on_hand == Decimal("185.000")  # 200 - 15

        # Latte intermedio NO debe tener StockItem (nunca se creó)
        assert not StockItem.objects.filter(product=latte, warehouse=warehouse).exists()

        # StockMoves: deben ser de los RAW, no del Latte intermedio
        moves = StockMove.objects.filter(ref_type="SALE", ref_id=sale_id)
        move_pids = {m.product_id for m in moves}
        assert leche.id in move_pids
        assert cafe.id in move_pids
        assert syrup.id in move_pids
        assert latte.id not in move_pids, \
            "Latte intermedio NO debe generar StockMove (no tiene stock real)"

        # Cost del SaleLine = 200*1.2 + 8*30 + 15*5 = 555 por unidad
        # qty=1 → line_cost = 555 * 1 = 555
        line = SaleLine.objects.get(sale_id=sale_id, product=latte_v)
        assert line.unit_cost_snapshot == Decimal("555.000"), \
            f"unit_cost_snapshot esperado 555, obtuvo {line.unit_cost_snapshot}"
        assert line.line_cost == Decimal("555.000"), \
            f"line_cost esperado 555, obtuvo {line.line_cost}"

    def test_sale_void_restores_all_raw_ingredients(
        self, api_client, tenant, store, warehouse,
    ):
        """Anular venta de producto con receta anidada → restaura stock de
        TODOS los raw, no solo de los del primer nivel."""
        ml = _unit(tenant, "ML", family="VOLUME")
        gr = _unit(tenant, "GR", family="MASS")
        un = _unit(tenant, "UN", family="COUNT")
        leche = _product(tenant, "Leche", ml, cost="1.2")
        cafe = _product(tenant, "Cafe", gr, cost="30")
        syrup = _product(tenant, "Syrup", ml, cost="5")
        _stock(tenant, warehouse, leche, "1000", avg_cost="1.2")
        _stock(tenant, warehouse, cafe, "100", avg_cost="30")
        _stock(tenant, warehouse, syrup, "200", avg_cost="5")

        latte = _product(tenant, "Latte", un)
        latte_v = _product(tenant, "Latte vainilla", un)
        _recipe(tenant, latte, [(leche, "200", ml), (cafe, "8", gr)])
        _recipe(tenant, latte_v, [(latte, "1", un), (syrup, "15", ml)])

        payload = {
            "warehouse_id": warehouse.id,
            "lines": [{"product_id": latte_v.id, "qty": "1", "unit_price": "4500"}],
            "payments": [{"method": "cash", "amount": 4500}],
        }
        r = api_client.post("/api/sales/sales/", payload, format="json")
        assert r.status_code == 201
        sale_id = r.data["id"]

        # Anular
        rv = api_client.post(f"/api/sales/sales/{sale_id}/void/")
        assert rv.status_code == 200, rv.data

        # Stock debe volver al inicial
        assert StockItem.objects.get(product=leche, warehouse=warehouse).on_hand == Decimal("1000.000")
        assert StockItem.objects.get(product=cafe, warehouse=warehouse).on_hand == Decimal("100.000")
        assert StockItem.objects.get(product=syrup, warehouse=warehouse).on_hand == Decimal("200.000")
