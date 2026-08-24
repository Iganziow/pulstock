"""
catalog.recipe_costing — cuanto cuesta de verdad un producto con receta.

El problema
-----------
`Product.cost` esta en cero para los productos que se preparan: un capuccino
no se compra, se arma. En Marbrava eso es la mitad del catalogo, y la Lista de
Precios mostraba "100,0% de margen" en verde para todos ellos.

Su costo real vive en los ingredientes, y el motor de ventas ya sabe
calcularlo --`sales.recipes.compute_recipe_costs`, que maneja recetas
anidadas, detecta ciclos y convierte unidades--. Este modulo lo trae a la
pantalla de precios.

Por que NO alcanza con llamar a esa funcion y mostrar el numero
---------------------------------------------------------------
Porque un ingrediente sin costo aporta CERO en silencio. Solo deja una
advertencia en un log que nadie abre.

Un capuccino al que le falta el costo de la leche daria, digamos, $300 en vez
de $800. Ese numero es verosimil --nadie sospecha de $300-- y el margen que
sale de ahi esta inflado sin que nada lo delate.

Seria peor que la situacion actual: hoy la pantalla miente con "100%", que al
menos da desconfianza. Cambiarlo por una mentira creible es retroceder.

Por eso este modulo devuelve, ademas del costo, **si esta completo y que le
falta**. La pantalla muestra el numero solo cuando se lo gano, y cuando no,
dice exactamente que ingrediente cargar. Eso convierte un dato en una accion:
en Marbrava, cinco ingredientes bloquean las diez recetas incompletas.
"""
from decimal import Decimal


def costos_de_receta(tenant_id, product_ids=None):
    """Costo unitario de los productos con receta.

    Devuelve `{product_id: {"costo": Decimal, "completo": bool,
    "faltantes": [nombres]}}`. Solo incluye productos que tienen receta.
    """
    from catalog.models import Product
    from inventory.models import StockItem
    from sales.recipes import _load_all_active_recipes, compute_recipe_costs

    recetas = _load_all_active_recipes(tenant_id)
    if not recetas:
        return {}

    # Costo de los ingredientes: el promedio ponderado del stock, con
    # respaldo en Product.cost. Es la misma fuente que usa la venta, para que
    # el costo que se ve al fijar el precio sea el mismo que se registra al
    # vender.
    costo_ing = {}
    for si in (StockItem.objects
               .filter(tenant_id=tenant_id)
               .select_related("product")):
        c = si.avg_cost or Decimal("0")
        if c == 0:
            c = (si.product.cost if si.product else None) or Decimal("0")
        if c:
            costo_ing[si.product_id] = c

    interesan = set(product_ids) & set(recetas) if product_ids else set(recetas)
    if not interesan:
        return {}

    def _faltantes(pid, prof=0, visto=frozenset()):
        """Ingredientes crudos sin costo, recorriendo la receta completa.

        Mismo techo de profundidad y misma deteccion de ciclos que el motor
        de ventas: si las dos mitades no recorrieran igual, una podria decir
        "completo" sobre algo que la otra no puede costear.
        """
        if prof > 10 or pid in visto:
            return set()
        if pid not in recetas:
            return set() if costo_ing.get(pid) else {pid}
        faltan = set()
        for linea in recetas[pid].lines.all():
            faltan |= _faltantes(linea.ingredient_id, prof + 1, visto | {pid})
        return faltan

    calculados = compute_recipe_costs(
        {pid: {} for pid in interesan}, recetas, costo_ing, tenant_id=tenant_id,
    )

    sin_costo = set()
    por_producto = {}
    for pid in interesan:
        faltan = _faltantes(pid)
        sin_costo |= faltan
        por_producto[pid] = {
            "costo": calculados.get(pid, Decimal("0")),
            "completo": not faltan,
            "faltan_ids": faltan,
        }

    # Los nombres en una sola consulta: la pantalla necesita decir "falta el
    # costo de Soda espresso", no un id.
    nombres = dict(Product.objects.filter(id__in=sin_costo).values_list("id", "name"))
    for datos in por_producto.values():
        datos["faltantes"] = sorted(
            nombres.get(i, f"producto {i}") for i in datos.pop("faltan_ids")
        )
    return por_producto
