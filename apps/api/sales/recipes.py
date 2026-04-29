"""
Sales recipe expansion (BOM).

Expande productos vendidos en sus ingredientes finales (raw) para operaciones
de stock y cálculo de costo. Soporta recetas anidadas (un ingrediente puede
ser otro producto con receta), con detección de ciclos y límite de profundidad.

Ejemplo: vendo 1 Latte vainilla.
- Receta de Latte vainilla: 1 UN de Latte + 15 ML Syrup vainilla.
- Receta de Latte: 200 ML Leche + 8 GR Café.
- Resultado expandido (lo que se descuenta del stock):
    Leche entera: 200 ML
    Café:         8 GR
    Syrup vainilla: 15 ML
- El "Latte" intermedio NO se descuenta (no es stockeable, es virtual).

Sin la recursión, antes solo se descontaba "1 UN de Latte" + "15 ML syrup" y
la leche/café NO se rebajaba del stock real → reportes y forecast desfasados.
"""
import logging
from decimal import Decimal

from catalog.models import Recipe

logger = logging.getLogger(__name__)


# Profundidad máxima permitida en cadenas de recetas anidadas. Marbrava
# en la práctica usa máximo 2 niveles (Latte → Latte vainilla). 10 es un
# techo holgado que protege contra ciclos no detectados o configuraciones
# erróneas que disparen recursión infinita.
MAX_RECIPE_DEPTH = 10


def _load_all_active_recipes(tenant_id):
    """
    Carga TODAS las recetas activas del tenant en un dict pid → Recipe.
    Una sola query con prefetch_related para evitar N+1 durante la expansión
    recursiva (sin esto, cada nivel haría su propia query).
    """
    return {
        r.product_id: r
        for r in Recipe.objects.filter(tenant_id=tenant_id, is_active=True)
            .prefetch_related("lines__ingredient__unit_obj", "lines__unit")
    }


def _load_inactive_recipe_pids(tenant_id):
    """
    Set de product_ids con Recipe is_active=False. Lo usamos para detectar
    "receta intermedia desactivada" en una cadena anidada y dar mensaje
    claro al dueño en lugar de fallar con shortage confuso.
    """
    return set(
        Recipe.objects.filter(tenant_id=tenant_id, is_active=False)
        .values_list("product_id", flat=True)
    )


def _convert_line_qty(qty, line, tenant_id):
    """
    Aplica la conversión de unidad de una RecipeLine a una qty arbitraria.

    Casos:
      A) line.unit y ingredient.unit_obj ambos seteados y distintos → convertir.
      B) Legacy: line.unit seteado pero ingredient solo tiene unit string (sin
         unit_obj_id) → buscar Unit por code y convertir si difiere.
      C) Sin conversión necesaria → devuelve qty tal cual.

    Lanza SaleValidationError si la conversión falla en el caso A (es un dato
    mal configurado por el dueño y debe ver el error). En el caso B (legacy)
    solo loguea warning, porque mucha data antigua está en este estado.
    """
    from catalog.unit_conversion import convert_qty

    # Caso A: ambos con unit_obj_id, distintos → convertir
    if line.unit_id and line.ingredient.unit_obj_id and line.unit_id != line.ingredient.unit_obj_id:
        try:
            return convert_qty(qty, line.unit, line.ingredient.unit_obj)
        except (ValueError, ZeroDivisionError) as exc:
            logger.warning(
                "Recipe conversion error for ingredient %d: %s", line.ingredient_id, exc
            )
            from .services import SaleValidationError
            raise SaleValidationError({
                "detail": f"Error de conversión en receta: {line.ingredient.name} — {exc}"
            })

    # Caso B: fallback legacy
    if line.unit_id and not line.ingredient.unit_obj_id:
        from catalog.models import Unit as UnitModel
        ing_unit = UnitModel.objects.filter(
            tenant_id=tenant_id,
            code=(line.ingredient.unit or "").upper(),
            is_active=True,
        ).first()
        if ing_unit and ing_unit.pk != line.unit_id:
            try:
                return convert_qty(qty, line.unit, ing_unit)
            except (ValueError, ZeroDivisionError) as exc:
                logger.warning(
                    "Recipe unit conversion fallback failed for ingredient %d: %s",
                    line.ingredient_id, exc,
                )

    # Caso C: no hay conversión
    return qty


def _resolve_product_name(pid):
    """Solo para mensajes de error. Tolera que el producto no exista."""
    from catalog.models import Product as ProductModel
    try:
        return ProductModel.objects.get(id=pid).name
    except ProductModel.DoesNotExist:
        return f"id={pid}"


def expand_recipes(agg, tenant_id):
    """
    Expande líneas de venta agregadas en cantidades a nivel de ingrediente raw.

    Recursivo: si un ingrediente también tiene receta activa, se expande a
    SUS ingredientes (y así sucesivamente). El producto-intermedio NO se
    incluye en el stock a descontar (es virtual, no tiene stock físico).

    Args:
        agg: dict product_id → {qty, unit_price, ...}
        tenant_id: int

    Returns:
        tuple(expanded_agg, all_recipes):
            expanded_agg: dict raw_product_id → {qty, unit_price}
                Solo contiene productos sin receta (raw). Productos con receta
                desaparecen, reemplazados por sus ingredientes recursivamente.
            all_recipes: dict product_id → Recipe (todas las recetas activas
                del tenant). Lo usa compute_recipe_costs para no re-querear.

    Raises:
        SaleValidationError: si hay ciclo en las recetas (A → B → A) o si
            la profundidad excede MAX_RECIPE_DEPTH.
    """
    all_recipes = _load_all_active_recipes(tenant_id)
    inactive_pids = _load_inactive_recipe_pids(tenant_id)
    expanded_agg = {}

    for pid, data in agg.items():
        # leaf_unit_price solo aplica si el producto vendido NO tiene receta
        # (en ese caso pasa tal cual con su unit_price). Si tiene receta, sus
        # ingredientes raw quedan con unit_price=0 (no se "venden", solo se
        # descuentan del stock).
        leaf_price = data["unit_price"] if pid not in all_recipes else None
        _expand_one(
            pid=pid,
            qty=data["qty"],
            all_recipes=all_recipes,
            inactive_pids=inactive_pids,
            expanded_agg=expanded_agg,
            tenant_id=tenant_id,
            depth=0,
            visited=frozenset(),
            leaf_unit_price=leaf_price,
            parent_pid=None,
        )

    return expanded_agg, all_recipes


def _expand_one(*, pid, qty, all_recipes, inactive_pids, expanded_agg, tenant_id,
                depth, visited, leaf_unit_price, parent_pid):
    """
    Expande UN producto recursivamente acumulando qty en expanded_agg.

    visited es un frozenset con los pids YA en cadena (ancestros). Si pid
    ya está en visited → ciclo detectado.

    parent_pid permite distinguir si pid llegó como producto vendido (None)
    o como ingrediente de otro (pid del padre). Lo usamos para el chequeo
    de "receta intermedia inactiva" — si el padre lo trae como ingrediente
    pero su receta está inactiva, damos error claro.
    """
    if depth > MAX_RECIPE_DEPTH:
        from .services import SaleValidationError
        raise SaleValidationError({
            "detail": (
                f"Receta excede {MAX_RECIPE_DEPTH} niveles de profundidad. "
                f"Revisar configuración de recetas anidadas (posible ciclo no detectado)."
            )
        })

    if pid in visited:
        from .services import SaleValidationError
        raise SaleValidationError({
            "detail": (
                f"Receta circular detectada: el producto '{_resolve_product_name(pid)}' "
                f"aparece en su propia cadena de ingredientes. Revisar las recetas."
            )
        })

    if pid not in all_recipes:
        # Caso especial: el producto NO tiene receta activa, pero existe una
        # receta INACTIVA. Si llegamos a este pid como ingrediente de otro
        # producto compuesto, lo más probable es que el dueño desactivó
        # temporalmente la receta intermedia sin querer (ej. testeando) y la
        # venta del padre va a fallar después con "Insufficient stock"
        # confuso (porque el intermedio no tiene stock real). Mejor avisar
        # con mensaje claro acá.
        if parent_pid is not None and pid in inactive_pids:
            from .services import SaleValidationError
            raise SaleValidationError({
                "detail": (
                    f"El producto '{_resolve_product_name(pid)}' es ingrediente de "
                    f"'{_resolve_product_name(parent_pid)}', pero su receta está "
                    f"DESACTIVADA. Activá la receta o quitala de la receta padre "
                    f"para poder vender."
                )
            })

        # Caso base: producto sin receta → es un ingrediente raw, lo
        # acumulamos en expanded_agg.
        if pid not in expanded_agg:
            expanded_agg[pid] = {
                "qty": Decimal("0"),
                "unit_price": leaf_unit_price if leaf_unit_price is not None else Decimal("0"),
            }
        elif leaf_unit_price is not None:
            # Si por alguna razón el mismo pid llega como vendido directo Y
            # como ingrediente, preservamos el unit_price del que se vende
            # directo (no afecta stock pero sí algunos reportes que lean
            # unit_price del expanded_agg).
            expanded_agg[pid]["unit_price"] = leaf_unit_price
        expanded_agg[pid]["qty"] += qty
        return

    # Caso recursivo: tiene receta activa → expandir sus líneas.
    recipe = all_recipes[pid]
    lines = list(recipe.lines.all())

    # Receta activa pero SIN líneas: es una mala configuración. Si seguimos,
    # el for no itera, no se descuenta nada (ni el producto ni ingredientes),
    # y la venta pasa "fantasma" sin descontar stock → bug grave que
    # detectamos en auditoría 28/04/26. Mejor abortar con mensaje claro
    # para que el dueño arregle la receta o la desactive.
    if not lines:
        from .services import SaleValidationError
        raise SaleValidationError({
            "detail": (
                f"La receta de '{_resolve_product_name(pid)}' está activa pero no "
                f"tiene ingredientes configurados. Agregalos en Catálogo → Recetas, "
                f"o desactivá la receta si querés vender el producto sin descontar stock."
            )
        })

    new_visited = visited | {pid}
    for line in lines:
        line_qty = qty * line.qty
        line_qty = _convert_line_qty(line_qty, line, tenant_id)
        _expand_one(
            pid=line.ingredient_id,
            qty=line_qty,
            all_recipes=all_recipes,
            inactive_pids=inactive_pids,
            expanded_agg=expanded_agg,
            tenant_id=tenant_id,
            depth=depth + 1,
            visited=new_visited,
            leaf_unit_price=None,  # ingredientes intermedios no llevan precio
            parent_pid=pid,
        )


def compute_recipe_costs(agg, all_recipes, ingredient_avg_cost, tenant_id=None):
    """
    Calcula el costo unitario de cada producto VENDIDO que tiene receta,
    sumando recursivamente los costos de sus ingredientes raw.

    IMPORTANTE: la conversión de unidades acá usa el MISMO helper que
    expand_recipes. Sin esto, el stock se descontaba en una unidad pero el
    costo se calculaba en otra → SaleLine.line_cost y gross_profit
    silenciosamente erróneos.

    Args:
        agg: dict product_id → {qty, ...}. Productos vendidos.
        all_recipes: dict product_id → Recipe. TODAS las recetas activas
            del tenant (devuelto por expand_recipes).
        ingredient_avg_cost: dict product_id → Decimal. Costo unitario de
            los ingredientes raw (con fallback Product.cost si avg_cost=0).
        tenant_id: int (requerido para conversión legacy).

    Returns:
        dict: product_id → Decimal con el costo de 1 unidad del producto
        vendido. Solo incluye productos con receta (los sin receta toman
        su costo del ingredient_avg_cost directamente al armar SaleLines).
    """
    # Compatibilidad legacy: si pasan recipe_map (solo productos vendidos)
    # en lugar de all_recipes, todavía funciona pero sin recursión profunda.
    # Tests viejos podrían depender de la firma original.
    recipe_costs = {}
    for pid in agg:
        if pid in all_recipes:
            cost = _cost_recursive(
                pid=pid,
                all_recipes=all_recipes,
                ingredient_avg_cost=ingredient_avg_cost,
                tenant_id=tenant_id,
                depth=0,
                visited=frozenset(),
            )
            recipe_costs[pid] = Decimal(str(cost)).quantize(Decimal("0.000"))
    return recipe_costs


def _cost_recursive(*, pid, all_recipes, ingredient_avg_cost, tenant_id, depth, visited):
    """
    Costo de 1 unidad de pid. Si tiene receta, suma costos de ingredientes
    convertidos a la unidad correcta. Si no tiene receta, usa
    ingredient_avg_cost[pid] (fallback 0).
    """
    if depth > MAX_RECIPE_DEPTH or pid in visited:
        # Defensa silenciosa: si llegamos acá sin que expand_recipes haya
        # detectado el problema antes (no debería pasar), devolvemos 0
        # para no romper la venta. La validación dura ya la hizo expand.
        return Decimal("0")

    if pid not in all_recipes:
        return ingredient_avg_cost.get(pid, Decimal("0"))

    recipe = all_recipes[pid]
    new_visited = visited | {pid}
    cost = Decimal("0")
    for line in recipe.lines.all():
        converted_qty = _convert_line_qty(line.qty, line, tenant_id or line.tenant_id)
        ing_cost = _cost_recursive(
            pid=line.ingredient_id,
            all_recipes=all_recipes,
            ingredient_avg_cost=ingredient_avg_cost,
            tenant_id=tenant_id,
            depth=depth + 1,
            visited=new_visited,
        )
        cost += ing_cost * converted_qty

        # Warnings solo para ingredientes raw que faltan o tienen costo 0,
        # no para intermedios (su costo se calcula recursivamente).
        if line.ingredient_id not in all_recipes:
            if line.ingredient_id not in ingredient_avg_cost:
                logger.warning("Recipe ingredient %d not found in stock", line.ingredient_id)
            elif ingredient_avg_cost.get(line.ingredient_id, Decimal("0")) == 0:
                logger.warning("Ingredient %d has zero cost", line.ingredient_id)
    return cost
