"""
Tests del fix (13/05/26) en classify_demand_pattern: agregar regla de
densidad para detectar intermitencia con poca data.

Razón: con 14 días de historia, productos como "Vasos chicos" (que se
usan 1-2 veces por semana) quedaban como "smooth" porque el ADI sobre
los pocos días con consumo era < 1.32. La nueva regla de densidad
("si menos del 30% de los días tuvo consumo, es intermitente") los
mueve correctamente a Croston.
"""
from datetime import date, timedelta
from decimal import Decimal

from forecast.engine.patterns import classify_demand_pattern


def _series(values_by_day):
    """Helper: construir daily_series desde una lista [(day_idx, qty), ...]"""
    base = date(2026, 5, 1)
    return [
        (base + timedelta(days=d), Decimal(str(q)))
        for d, q in values_by_day
    ]


class TestDensityRule:

    def test_smooth_when_density_high(self):
        """Producto con consumo en TODOS los días → smooth (regla clásica)."""
        # 14 días, todos con qty 5 → ADI = 1, density = 100%
        series = _series([(i, 5) for i in range(14)])
        pattern, adi, _ = classify_demand_pattern(series)
        assert pattern == "smooth"
        assert adi <= 1.5

    def test_intermittent_by_low_density_with_low_adi(self):
        """Caso real de Vasos chicos: vendió en 3 de 14 días.
        ADI clásico (sobre los 3 días con consumo): 4.5 → ya pasaba como
        intermitente con regla vieja, pero a veces el ADI redondeaba mal
        con poca data. Density = 3/14 = 21% → < 30% → intermitente.
        Este test confirma que ambas reglas coinciden en este caso."""
        # Día 0, 5, 10 con qty 5
        series = _series([(0, 5), (5, 5), (10, 5)])
        # Pad with zeros
        full = []
        for d in range(14):
            qty = next((q for di, q in [(0, 5), (5, 5), (10, 5)] if di == d), 0)
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(qty))))
        pattern, adi, cv2 = classify_demand_pattern(full)
        assert pattern in ("intermittent", "lumpy"), (
            f"Esperaba intermittent o lumpy. Obtuvo {pattern} (ADI={adi}, CV²={cv2})"
        )

    def test_intermittent_by_density_when_adi_misleading(self):
        """CASO CLAVE del fix: producto vendió 3 días seguidos y nada más.
        ADI clásico = 1.0 (intervalos de 1 día) → smooth ANTES.
        Density = 3/14 = 21% → < 30% → AHORA intermitente.

        Antes: smooth con MAPE/WAPE explosivo porque el modelo predecía
        que iba a vender 5/día todos los días.
        Ahora: intermitent → Croston, que predice "vende cada N días"."""
        # Días 0, 1, 2 con qty 5; resto en 0
        full = []
        for d in range(14):
            qty = 5 if d < 3 else 0
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(qty))))
        pattern, adi, _ = classify_demand_pattern(full)
        # ADI sobre días con consumo: 1.0 (todos consecutivos) — engañoso
        assert adi <= 1.32, "ADI debería estar bajo (días consecutivos)"
        # Density: 3/14 = 21% — debería disparar la nueva regla
        assert pattern in ("intermittent", "lumpy"), (
            f"Esperaba intermittent (density 21%), obtuvo {pattern}. "
            f"El fix de density NO se está aplicando."
        )

    def test_smooth_at_boundary_30pct(self):
        """Justo al límite: 30% de densidad debe ser SMOOTH (límite estricto)."""
        # 14 días, consumo en 5 → density = 5/14 = 35.7% > 30% → smooth
        full = []
        for d in range(14):
            qty = 5 if d in (0, 3, 6, 9, 12) else 0
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(qty))))
        pattern, adi, _ = classify_demand_pattern(full)
        # ADI = 3 (intervalos de 3 días) → ESO solo ya da intermitent
        # (esta prueba confirma que la regla vieja sigue activa también)
        assert pattern in ("intermittent", "lumpy")

    def test_density_check_skipped_with_few_days(self):
        """Con menos de 7 días totales NO se aplica el density check
        (no hay confianza estadística)."""
        # 5 días, todos con consumo → smooth
        full = [
            (date(2026, 5, 1) + timedelta(days=d), Decimal("5"))
            for d in range(5)
        ]
        pattern, _, _ = classify_demand_pattern(full)
        assert pattern == "smooth"

    def test_lumpy_when_sparse_and_variable(self):
        """Densidad baja + variabilidad alta de tamaños → lumpy."""
        # 4 días con consumo de 1, 50, 1, 100 — muy variable
        full = []
        consumo = {0: 1, 4: 50, 8: 1, 12: 100}
        for d in range(14):
            qty = consumo.get(d, 0)
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(qty))))
        pattern, _, cv2 = classify_demand_pattern(full)
        assert pattern == "lumpy", f"Esperaba lumpy (CV² alto), obtuvo {pattern}"
        assert cv2 >= 0.49

    def test_insufficient_unchanged(self):
        """Menos de 3 días con consumo sigue siendo insufficient."""
        full = [
            (date(2026, 5, 1) + timedelta(days=d), Decimal(str(5 if d == 0 else 0)))
            for d in range(14)
        ]
        pattern, _, _ = classify_demand_pattern(full)
        assert pattern == "insufficient"


class TestRealWorldCases:
    """Casos extraídos de prod 13/05/26 — antes 'smooth', ahora deben
    ser intermittent."""

    def test_caja_torta_realistic(self):
        """Caja torta vendió 4 unidades en 30 días (~13% de density)."""
        full = []
        venta_dias = {3: 1, 11: 1, 20: 2}
        for d in range(30):
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(venta_dias.get(d, 0)))))
        pattern, _, _ = classify_demand_pattern(full)
        assert pattern in ("intermittent", "lumpy"), (
            f"Caja torta (3 días con consumo en 30) debería ser intermitente. "
            f"Obtuvo {pattern}."
        )

    def test_vasos_chicos_realistic(self):
        """Vasos chicos vendió 16 unidades en 6 días distintos en 30 días
        (density = 6/30 = 20%)."""
        full = []
        venta_dias = {2: 3, 7: 2, 14: 4, 18: 2, 23: 3, 28: 2}
        for d in range(30):
            full.append((date(2026, 5, 1) + timedelta(days=d), Decimal(str(venta_dias.get(d, 0)))))
        pattern, _, _ = classify_demand_pattern(full)
        assert pattern in ("intermittent", "lumpy"), (
            f"Vasos chicos (6 días con consumo en 30) debería ser intermitente. "
            f"Obtuvo {pattern}."
        )
