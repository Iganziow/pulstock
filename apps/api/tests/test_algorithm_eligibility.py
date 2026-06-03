"""
F (01/06/26) capa 1 — elegibilidad por patrón. Los modelos CONTINUOS
(theta, ETS, Holt-Winters) NO deben competir en demanda intermitente/lumpy
(ahí colapsan a 0 y MASE los premia falsamente). Croston sí, y solo ahí.
"""
import pytest

from forecast.engine.algorithms.theta import ThetaForecast
from forecast.engine.algorithms.ets import ETSForecast
from forecast.engine.algorithms.holt_winters import HoltWinters
from forecast.engine.algorithms.holt_winters_damped import HoltWintersDamped
from forecast.engine.algorithms.croston import CrostonForecast, CrostonSBA
from forecast.engine.algorithms.adaptive_moving_average import AdaptiveMovingAverage

CONTINUOS = [ThetaForecast, ETSForecast, HoltWinters, HoltWintersDamped]


@pytest.mark.parametrize("cls", CONTINUOS)
def test_continuos_no_compiten_en_intermitente(cls):
    a = cls()
    n = 120  # datos de sobra (descarta el gate de min_data_points)
    assert not a.is_eligible(n, "intermittent"), f"{a.name} no debe competir en intermittent"
    assert not a.is_eligible(n, "lumpy"), f"{a.name} no debe competir en lumpy"


@pytest.mark.parametrize("cls", CONTINUOS)
def test_continuos_si_compiten_en_smooth(cls):
    a = cls()
    assert a.is_eligible(120, "smooth"), f"{a.name} SÍ debe competir en smooth (su terreno)"


@pytest.mark.parametrize("cls", [CrostonForecast, CrostonSBA])
def test_croston_solo_en_intermitente(cls):
    a = cls()
    assert a.is_eligible(120, "intermittent")
    assert a.is_eligible(120, "lumpy")
    assert not a.is_eligible(120, "smooth"), "Croston no es para demanda regular"


def test_adaptive_ma_compite_en_todos():
    a = AdaptiveMovingAverage()
    for p in ("smooth", "intermittent", "lumpy"):
        assert a.is_eligible(120, p), f"adaptive_ma debe competir en {p} (fallback robusto)"


class TestKeptPathEligibilityGuard:
    """El kept-path no debe conservar un modelo cuyo algoritmo ya no aplica."""

    def test_theta_no_elegible_en_intermitente(self):
        from forecast.services import _algo_eligible_for_pattern
        assert not _algo_eligible_for_pattern("theta", "intermittent")
        assert not _algo_eligible_for_pattern("theta", "lumpy")
        assert _algo_eligible_for_pattern("theta", "smooth")

    def test_croston_elegible_en_intermitente(self):
        from forecast.services import _algo_eligible_for_pattern
        assert _algo_eligible_for_pattern("croston_sba", "intermittent")
        assert not _algo_eligible_for_pattern("croston_sba", "smooth")

    def test_algoritmo_fuera_de_registry_no_fuerza(self):
        from forecast.services import _algo_eligible_for_pattern
        # ingredient_derived no está en el registry → True (no forzar reemplazo)
        assert _algo_eligible_for_pattern("ingredient_derived", "intermittent")
        assert _algo_eligible_for_pattern("category_prior", "intermittent")
