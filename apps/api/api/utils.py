"""
api/utils.py
============
Utilidades compartidas para validación de input en todo el proyecto.
Principio SOLID (SRP): cada helper tiene una única responsabilidad.
"""

from decimal import Decimal, InvalidOperation


def safe_int(value, default=None):
    """Convierte a int de forma segura. Retorna default si falla."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_decimal(value, default=None):
    """Convierte a Decimal de forma segura. Retorna default si falla."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default
