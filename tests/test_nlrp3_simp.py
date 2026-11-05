"""Checks on the SBML translation of the simplified NLRP3 model (Julia's test model).

The comparison against the simplified notebook lives in
``referencia/nlrp3/comparar_sbml.py``; these tests guard the SBML file against
typos and pin the result of the verification against the original, which is
the evidence that the library runs on a second model without code changes
(``estudo_de_caso/nlrp3/NOTAS.md``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import roadrunner

import reducheck

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "modelos" / "nlrp3_simp.xml"
CONFIG_PATH = ROOT / "estudo_de_caso" / "nlrp3" / "nlrp3_simp.yaml"

# Order of the vector returned by `edos`; all start at zero in the notebook.
STATE_VARIABLES = ["NLRP3a", "NLRP3o", "ASCb", "C1", "IL18c", "IL18e", "proIL1B", "IL1Be"]

# Every parameter of the simplified notebook, with its value.
PARAMETERS = {
    "nfkb0": 0.25,
    "gammaNF": 2,
    "NF_50": 0.3,
    "h": 0.55,
    "s": 0.8,
    "tau": 10,
    "S1": 1,
    "alpha1": 0.07,
    "S2": 1,
    "k1": 0.7,
    "novodelta1": 0.0025,
    "k2": 1,
    "k3": 0.04,
    "a": 1,
    "b": 2,
    "c": 1000,
    "k4": 0.03,
    "C1_50": 0.3,
    "gammaC1": 2,
    "Gnovo": 0.08,
    "alpha3": 0.06,
    "alpha4": 1,
    "alpha5": 1,
    "k5": 1,
    "delta2": 0.004,
    "k6": 1,
    "j": 0.7,
}


@pytest.fixture(scope="module")
def runner() -> roadrunner.RoadRunner:
    """Load the SBML model once for the whole module."""
    return roadrunner.RoadRunner(str(MODEL_PATH))


def test_sbml_is_valid() -> None:
    """libsbml reads the file without errors."""
    libsbml = pytest.importorskip("libsbml")
    document = libsbml.readSBMLFromFile(str(MODEL_PATH))
    assert document.getNumErrors() == 0


def test_state_variables(runner: roadrunner.RoadRunner) -> None:
    """The model has exactly the eight variables of `edos`."""
    model = runner.model
    ids = [model.getStateVectorId(i) for i in range(model.getNumRateRules())]
    assert sorted(ids) == sorted(STATE_VARIABLES)


@pytest.mark.parametrize(("name", "value"), sorted(PARAMETERS.items()))
def test_parameter_value(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every parameter has the name and the value of the notebook."""
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


@pytest.mark.parametrize("name", STATE_VARIABLES)
def test_initial_condition_is_zero(runner: roadrunner.RoadRunner, name: str) -> None:
    """Every state variable starts at zero, as in the notebook."""
    runner.reset()
    assert runner[name] == 0.0


def test_nfkb_input_is_025_at_time_zero(runner: roadrunner.RoadRunner) -> None:
    """Same input as the original, without a piecewise."""
    runner.reset()
    assert runner["nfkbn"] == 0.25


def test_il18_stays_within_the_conserved_total(runner: roadrunner.RoadRunner) -> None:
    """IL18c + IL18e never exceeds 1, the total that proIL18 = 1 - IL18c - IL18e assumes."""
    runner.reset()
    runner.integrator.setValue("relative_tolerance", 1e-10)
    runner.integrator.setValue("absolute_tolerance", 1e-12)
    runner.selections = ["IL18c", "IL18e"]
    result = runner.simulate(0, 300, 301)
    total = result[:, 0] + result[:, 1]
    assert total.max() <= 1.0 + 1e-9


def test_verification_runs_without_library_changes(tmp_path: Path) -> None:
    """The whole pipeline runs on this model and gives the verdict in NOTAS.md."""
    resultado = reducheck.verificar(CONFIG_PATH, pasta_de_saida=tmp_path)
    assert resultado.nivel == "REPROVADO"
    assert len(resultado.criterios) == 24
    falhas = {
        (c.metrica, c.variavel) for c in resultado.criterios if c.obrigatorio and not c.passou
    }
    # With the criteria chosen by behaviour (question 57), only the real infidelity is left:
    # IL1be, where j = 0.7 replaces the ~0.952 implied by the original.
    assert falhas == {("nrmse", "IL1be"), ("erro_estacionario", "IL1be")}
