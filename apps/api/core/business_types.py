"""
core.business_types — un solo lugar donde vive qué tipo de negocio es válido.

El bug que motiva esto (B19)
----------------------------
Habia tres verdades distintas sobre que valores existen:

  · El modelo acepta: retail, restaurant, hardware, wholesale, pharmacy, other
  · El trial mandaba: minimarket, ferreteria, farmacia, ropa, libreria,
    restaurant, otro — y el backend los guardaba SIN VALIDAR
  · El checkout mandaba los correctos… y el backend los DESCARTABA al crear
    el Tenant

Resultado: todo tenant que pagaba quedaba en "retail" (el default) y todo
tenant de trial quedaba con un valor que no le sirve a nadie.

Por que importa
---------------
`business_type` no es un dato decorativo de marketing. Decide tres cosas:

  1. Las unidades de medida que se siembran (una cafeteria necesita Porcion,
     Taza y Cucharada; una ferreteria necesita Pulgada, Pie y Galon).
  2. Los multiplicadores de feriado del forecast — un 18 de septiembre no
     mueve igual a un restaurant que a una farmacia.
  3. Es la llave del "Modo Apertura": la plantilla de demanda con la que
     arranca un local nuevo que todavia no tiene historia propia.

Guardar "minimarket" donde el codigo busca "retail" no rompe nada de forma
visible: simplemente las tres cosas caen al default y nadie se entera.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFECTO = "retail"

# Sinonimos que llegaron de formularios viejos. Se mapean en vez de
# descartarse: el dueno eligio algo y esa eleccion tiene informacion.
ALIAS = {
    "minimarket": "retail",
    "almacen": "retail",
    "ropa": "retail",
    "libreria": "retail",
    "tienda": "retail",
    "ferreteria": "hardware",
    "farmacia": "pharmacy",
    "distribuidora": "wholesale",
    "mayorista": "wholesale",
    "cafeteria": "restaurant",
    "cafe": "restaurant",
    "otro": "other",
}


def normalizar(valor: str | None) -> str:
    """Devuelve siempre un business_type válido del modelo.

    Acepta el valor correcto, un alias conocido, o cualquier basura — y en el
    peor caso cae al defecto. Nunca guarda algo que el resto del código no
    sepa leer.
    """
    from core.models import Tenant

    validos = {c[0] for c in Tenant.BUSINESS_TYPE_CHOICES}
    v = (valor or "").strip().lower()

    if v in validos:
        return v
    if v in ALIAS:
        return ALIAS[v]
    if v:
        logger.warning(
            "business_type desconocido %r — se usa %r. Si es un tipo nuevo, "
            "hay que agregarlo a Tenant.BUSINESS_TYPE_CHOICES, no solo al "
            "formulario.", valor, DEFECTO,
        )
    return DEFECTO
