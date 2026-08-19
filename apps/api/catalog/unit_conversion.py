"""
Unit conversion utility for recipes.

Usage:
    from catalog.unit_conversion import convert_qty
    result = convert_qty(Decimal("300"), from_unit=gr_unit, to_unit=kg_unit)
    # → Decimal("0.3")
"""
from decimal import Decimal


def convert_qty(qty: Decimal, from_unit, to_unit) -> Decimal:
    """
    Convert qty from one unit to another within the same family.

    Both units must share the same `family`. Conversion goes through the
    base unit: qty_base = qty × from_unit.conversion_factor, then
    result = qty_base / to_unit.conversion_factor.

    Returns the converted Decimal quantity.
    Raises ValueError if units are from different families.
    """
    if from_unit.pk == to_unit.pk:
        return qty

    if from_unit.family != to_unit.family:
        raise ValueError(
            f"No se puede convertir entre {from_unit.code} ({from_unit.get_family_display()}) "
            f"y {to_unit.code} ({to_unit.get_family_display()})"
        )

    # B11: antes esto devolvía `qty` sin convertir y EN SILENCIO cuando el
    # factor faltaba o era 0. En un motor que descuenta leche en mililitros
    # desde recetas, "no convertir" no es un fallback benigno: mezcla unidades
    # y corrompe el consumo, el costo y la demanda del forecast sin que nadie
    # se entere. Mejor fallar fuerte y que se note al configurar la unidad.
    if not to_unit.conversion_factor or to_unit.conversion_factor == 0:
        raise ValueError(
            f"La unidad {to_unit.code} no tiene factor de conversión configurado. "
            f"Defínelo en el catálogo de unidades para poder convertir desde "
            f"{from_unit.code}."
        )
    if not from_unit.conversion_factor or from_unit.conversion_factor == 0:
        raise ValueError(
            f"La unidad {from_unit.code} no tiene factor de conversión configurado. "
            f"Defínelo en el catálogo de unidades."
        )

    qty_in_base = qty * from_unit.conversion_factor
    return qty_in_base / to_unit.conversion_factor
