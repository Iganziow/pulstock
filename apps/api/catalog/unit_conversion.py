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

    qty_in_base = qty * from_unit.conversion_factor
    return qty_in_base / to_unit.conversion_factor
