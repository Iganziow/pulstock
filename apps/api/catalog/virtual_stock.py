"""
Virtual stock — cálculo de cuántas unidades de un producto compuesto
(con receta activa) se pueden armar con el stock actual de ingredientes raw.

Ejemplo: Latte vainilla tiene receta = 1 UN Latte + 15 ML Syrup vainilla.
Latte tiene receta = 200 ML Leche + 8 GR Café. Si tenemos:
    Leche entera: 1.000 ML
    Café tolva:   100 GR
    Syrup vain.:  60 ML

Entonces max producible de Latte = min(1000/200, 100/8) = min(5, 12.5) = 5
Y max producible de Latte vainilla = min(5/1, 60/15) = min(5, 4) = 4

Antes este cálculo no existía → reportes ABC y top-sellers mostraban
"Stock: 0" para Latte vainilla porque no tiene StockItem propio (es
virtual, se "fabrica" al momento de la venta vía expansión de receta).
Ahora podemos mostrar "Stock virtual: 4" — cuántos se pueden armar con
los ingredientes disponibles.

USO TÍPICO:
    from catalog.virtual_stock import compute_virtual_stock_map
    stock_map = compute_virtual_stock_map(tenant_id, store_id)
    for pid, qty in stock_map.items():
        ...

El map devuelto incluye tanto productos raw (su on_hand sumado por
warehouse) como productos compuestos (max producible recursivo). Reusa
los helpers de sales.recipes (`_load_all_active_recipes`, `_convert_line_qty`,
MAX_RECIPE_DEPTH) para garantizar que la conversión de unidades y el
guard de ciclos sean idénticos a los de la venta real.
"""
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from inventory.models import StockItem
from sales.recipes import (
    MAX_RECIPE_DEPTH,
    _convert_line_qty,
    _load_all_active_recipes,
)


def _build_stock_map(tenant_id, store_id, warehouse_id=None):
    """
    Stock raw on_hand sumado por producto. Si warehouse_id=None, suma
    todos los warehouses del store (mismo criterio que get_abc_analysis
    en reports/services.py).
    """
    qs = StockItem.objects.filter(tenant_id=tenant_id, warehouse__store_id=store_id)
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)
    rows = qs.values("product_id").annotate(
        total=Coalesce(Sum("on_hand"), Decimal("0"))
    )
    return {row["product_id"]: row["total"] for row in rows}


def compute_virtual_stock_map(tenant_id, store_id, warehouse_id=None):
    """
    Devuelve dict: product_id → Decimal con la cantidad disponible para venta.

    Para productos sin receta: devuelve `on_hand` total (sumado por warehouses
    del store, o filtrado a un warehouse si se pasa).

    Para productos CON receta activa: calcula recursivamente el máximo
    producible basado en stock de ingredientes raw, aplicando la conversión
    de unidades de cada RecipeLine (mismo helper que `expand_recipes` para
    consistencia).

    Edge cases manejados:
    - Receta con un ingrediente sin stock → max producible = 0
    - Receta con qty_needed = 0 (configuración rara) → ingrediente ignorado
    - Ciclos en recetas → guard interno devuelve 0 para no colgar
    - Profundidad excesiva → guard interno devuelve 0

    NOTA: el cálculo NO considera `allow_negative_stock`. Si el dueño tiene
    leche en 0 con la flag activa, técnicamente la venta se "permite" (con
    clamping del stock real), pero el `virtual_stock` reportará 0 porque
    refleja lo que se puede armar con stock REAL. Eso es lo que el dueño
    espera ver en reportes — no inflar el "disponible" por una flag.
    """
    all_recipes = _load_all_active_recipes(tenant_id, lock=False)
    stock_map = _build_stock_map(tenant_id, store_id, warehouse_id)

    # Memoización: cuando una receta usa el mismo intermedio en varias ramas
    # (raro pero posible), evitamos recalcular.
    cache = {}

    def _max_producible(pid, depth, visited):
        if pid in cache:
            return cache[pid]
        if depth > MAX_RECIPE_DEPTH or pid in visited:
            # Defensa silenciosa: si hay ciclo o profundidad excesiva,
            # devolvemos 0 para no colgar. La validación dura ya la hace
            # expand_recipes (al momento de la venta) con mensaje claro.
            return Decimal("0")

        if pid not in all_recipes:
            # Producto raw: su disponibilidad es su stock real.
            result = stock_map.get(pid, Decimal("0"))
            cache[pid] = result
            return result

        recipe = all_recipes[pid]
        new_visited = visited | {pid}
        per_ingredient = []
        for line in recipe.lines.all():
            try:
                qty_needed = _convert_line_qty(line.qty, line, tenant_id)
            except Exception:
                # Si la conversión de unidad falla (ej. unit incompatible),
                # no podemos calcular → ese ingrediente bloquea producción.
                qty_needed = Decimal("0")
            if qty_needed <= 0:
                # qty_needed=0 significa receta mal configurada o conversión
                # rota. No contribuye al min (se ignora). Si TODOS los
                # ingredientes están así, el producto queda en 0.
                continue
            ing_available = _max_producible(line.ingredient_id, depth + 1, new_visited)
            per_ingredient.append(ing_available / qty_needed)

        if not per_ingredient:
            # Receta vacía o todos los ingredientes con qty_needed=0.
            # max producible = 0. (Notar que expand_recipes ya rechaza
            # recetas vacías al momento de la venta — esto es defensa.)
            result = Decimal("0")
        else:
            result = min(per_ingredient)
        cache[pid] = result.quantize(Decimal("0.001"))
        return cache[pid]

    # Resultado: incluye TODOS los productos con receta (calculados) +
    # productos raw que aparecen en stock_map (su on_hand directo).
    result = {}
    # Raw products (con StockItem)
    for pid, qty in stock_map.items():
        if pid not in all_recipes:
            result[pid] = qty
    # Composed products (con receta activa)
    for pid in all_recipes:
        result[pid] = _max_producible(pid, depth=0, visited=frozenset())

    return result


def is_virtual_product(product_id, tenant_id):
    """
    True si el producto tiene una receta activa (= se "fabrica" vía
    expansión de ingredientes, no tiene stock físico propio).
    Útil para que la UI muestre badge "compuesto" / "virtual".
    """
    from catalog.models import Recipe
    return Recipe.objects.filter(
        tenant_id=tenant_id, product_id=product_id, is_active=True,
    ).exists()
