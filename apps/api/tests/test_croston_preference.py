"""
Tests del fix (13/05/26) en select_best_model: forzar preferencia por
Croston cuando el patrón es intermittent o lumpy.

Razón: en el modelo de Marbrava, productos clasificados como
intermittent/lumpy NUNCA terminaban con Croston aunque éste estuviera
implementado y disponible. Otros algoritmos (simple_avg, moving_avg)
ganaban en el backtest porque "promedian a 0" en los días sin demanda
— pero no sirven operativamente, predicen consumo cada día cuando la
realidad es esporádica.

Ahora: si Croston/Croston-SBA son candidatos viables, ganan
automáticamente para patrones intermittent/lumpy. Para patrones
"smooth" la lógica anterior (mejor MAPE) sigue intacta.
"""
import pytest

from forecast.engine.selection import select_best_model


def _make_intermittent_series(n_days=30):
    """Generar una serie intermitente: vende cada 5-7 días, cantidades 1-3."""
    from datetime import date, timedelta
    base = date(2026, 4, 1)
    series = []
    consume_days = {3: 2, 9: 1, 15: 3, 22: 1, 28: 2}
    for d in range(n_days):
        series.append((base + timedelta(days=d), float(consume_days.get(d, 0))))
    return series


def _make_smooth_series(n_days=30):
    """Generar una serie suave: vende todos los días entre 8-12."""
    from datetime import date, timedelta
    import random
    random.seed(42)
    base = date(2026, 4, 1)
    return [
        (base + timedelta(days=d), float(random.uniform(8, 12)))
        for d in range(n_days)
    ]


class TestCrostonPreferenceForIntermittent:

    def test_intermittent_pattern_picks_croston_when_available(self):
        """Producto con demanda intermitente debe terminar con Croston
        aunque otro algoritmo tenga mejor MAE en backtest."""
        series = _make_intermittent_series(n_days=30)
        result = select_best_model(series, demand_pattern="intermittent")

        # Si Croston no está entre candidatos (caso muy raro), aceptar otro
        # con MAE bajo. Pero si fue elegible, debe ganar.
        # En 30 días con esta forma, Croston debe estar disponible.
        assert result["algorithm"] in ("croston", "croston_sba", "none"), (
            f"Esperaba croston/croston_sba para pattern intermittent, "
            f"obtuvo {result['algorithm']}"
        )

    def test_lumpy_pattern_picks_croston_when_available(self):
        """Pattern lumpy también prefiere Croston."""
        from datetime import date, timedelta
        # Lumpy: intermitente con tamaños MUY variables
        base = date(2026, 4, 1)
        series = [(base + timedelta(days=d), 0.0) for d in range(30)]
        # Sustituir días específicos
        consume = {3: 1, 10: 50, 17: 2, 24: 100}  # variabilidad alta
        for d, q in consume.items():
            series[d] = (series[d][0], float(q))

        result = select_best_model(series, demand_pattern="lumpy")
        assert result["algorithm"] in ("croston", "croston_sba", "none")

    def test_smooth_pattern_unchanged(self):
        """Pattern smooth NO debe cambiar de comportamiento — sigue
        eligiendo el de mejor MAPE (no Croston)."""
        series = _make_smooth_series(n_days=30)
        result = select_best_model(series, demand_pattern="smooth")
        # No debería ser Croston (porque Croston no es elegible para smooth
        # según su demand_patterns=["intermittent", "lumpy"])
        assert result["algorithm"] not in ("croston", "croston_sba"), (
            f"Smooth pattern NO debería elegir Croston, obtuvo {result['algorithm']}"
        )
