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
        """Producto con demanda intermitente prefiere Croston, SALVO que otro
        algoritmo le gane CLARAMENTE por tasa.

        Sprint A (jul 2026): la selección en intermitente/lumpy ahora es por
        wape_total (la tasa del período — lo que decide compras), no por
        acierto diario. En esta serie adaptive_ma clava la tasa (wape_total
        ~25 vs ~66 de Croston) Y vence al naive (MASE<1) mientras Croston no
        (MASE 1.39) → que gane es correcto. Lo que este test SIGUE prohibiendo
        es el bug histórico: un ganador que 'promedia a 0' (colapso, tasa
        desastrosa) — eso daría wape_total ~100 y MASE sin mérito."""
        series = _make_intermittent_series(n_days=30)
        result = select_best_model(series, demand_pattern="intermittent")

        if result["algorithm"] not in ("croston", "croston_sba", "none"):
            fc_total = sum(
                float(f.get("qty_predicted", 0) or 0)
                for f in result.get("forecasts", [])
            )
            assert fc_total > 0.5, (
                f"{result['algorithm']} ganó con forecast colapsado (fc_total={fc_total:.2f})"
            )
            assert result["metrics"].get("mase", 999) < 1.0, (
                f"{result['algorithm']} ganó sin vencer al naive "
                f"(MASE={result['metrics'].get('mase')})"
            )
            assert result["metrics"].get("wape_total", 999) < 45, (
                f"{result['algorithm']} ganó sin clavar la tasa "
                f"(wape_total={result['metrics'].get('wape_total')}) — "
                f"el override exige ventaja CLARA sobre Croston"
            )

    def test_lumpy_pattern_no_colapsa_a_cero(self):
        """Pattern lumpy: el modelo ganador no debe colapsar a forecast ~0.
        Croston es preferido, pero adaptive_ma puede ganar si detecta un
        patrón day-of-week real y supera a Croston por >= 15% en MASE.
        El test original (Croston obligatorio) fue escrito antes de F8
        (day-of-week awareness en adaptive_ma), cuando el bug era que MA
        ganaba 'promediando a cero'. Ahora adaptive_ma produce forecasts
        reales para lumpy — si genuinamente gana, es el comportamiento correcto."""
        from datetime import date, timedelta
        base = date(2026, 4, 1)
        series = [(base + timedelta(days=d), 0.0) for d in range(30)]
        consume = {3: 1, 10: 50, 17: 2, 24: 100}
        for d, q in consume.items():
            series[d] = (series[d][0], float(q))

        result = select_best_model(series, demand_pattern="lumpy")
        fc_total = sum(
            float(f.get("qty_predicted", 0) or 0)
            for f in result.get("forecasts", [])
        )
        # El forecast no debe ser un cero colapsado (eso sería operativamente inútil).
        assert fc_total > 0.5, (
            f"Forecast colapsado a ~0: {result['algorithm']} fc_total={fc_total:.3f}"
        )
        # Si no es Croston, debe al menos vencer al naive (MASE < 1.0).
        if result["algorithm"] not in ("croston", "croston_sba", "none"):
            mase_val = result["metrics"].get("mase", 999)
            assert mase_val < 1.0, (
                f"Non-Croston '{result['algorithm']}' gana pero no vence al naive "
                f"(MASE={mase_val:.3f}). El guard debería haberlo bloqueado."
            )

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
