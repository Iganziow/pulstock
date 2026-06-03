"""
Elegibilidad por patrón + guard del kept-path.

Nota (01/06/26): se PROBÓ restringir theta/ETS/HW a smooth (capa 1) pero se
revirtió — era demasiado brusco: theta ajusta bien ~15 productos intermitentes
y sacarlo de todos hundió las métricas. El colapso se ataca quirúrgicamente con
el filtro anti-colapso en choose_best (ver test_selection_mase). Aquí queda el
estado vigente: los continuos compiten en todos los patrones; Croston solo en
intermitente/lumpy; y el kept-path no conserva algoritmos inelegibles.
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
def test_continuos_compiten_en_todos_los_patrones(cls):
    """Los continuos vuelven a competir en todos (capa 1 revertida)."""
    a = cls()
    for p in ("smooth", "intermittent", "lumpy"):
        assert a.is_eligible(120, p), f"{a.name} debe competir en {p}"


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
    """El kept-path no debe conservar un modelo cuyo algoritmo ya no aplica
    al patrón actual (helper general, sigue vigente tras revertir capa 1)."""

    def test_croston_inelegible_en_smooth(self):
        from forecast.services import _algo_eligible_for_pattern
        # Croston está restringido a intermitente/lumpy → inelegible en smooth.
        assert not _algo_eligible_for_pattern("croston_sba", "smooth")
        assert _algo_eligible_for_pattern("croston_sba", "intermittent")

    def test_continuos_elegibles_en_todo(self):
        from forecast.services import _algo_eligible_for_pattern
        for p in ("smooth", "intermittent", "lumpy"):
            assert _algo_eligible_for_pattern("theta", p)

    def test_algoritmo_fuera_de_registry_no_fuerza(self):
        from forecast.services import _algo_eligible_for_pattern
        # ingredient_derived no está en el registry → True (no forzar reemplazo)
        assert _algo_eligible_for_pattern("ingredient_derived", "intermittent")
        assert _algo_eligible_for_pattern("category_prior", "intermittent")
