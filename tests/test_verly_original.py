"""Checks on the SBML translation of the Verly et al. (2024) model.

The full comparison against the original Python code lives in
``referencia/comparar_sbml.py``; these tests only guard the SBML file itself,
so that a typo in ``modelos/verly_original.ant`` is caught by CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import roadrunner

MODEL_PATH = Path(__file__).resolve().parents[1] / "modelos" / "verly_original.xml"

STATE_VARIABLES = ["D", "Mo", "M1", "M2", "C1", "C2", "Cm", "Cb", "Mc", "Mb", "E2"]

INITIAL_CONDITIONS = {
    "D": 1000000.0,
    "Mo": 4000.0,
    "M1": 0.0,
    "M2": 0.0,
    "C1": 0.0,
    "C2": 0.0,
    "Cm": 2500.0,
    "Cb": 0.0,
    "Mc": 0.0,
    "Mb": 0.0,
    "E2": 0.060,
}

# Every parameter of `bonerepair`, with the value of the original code.
PARAMETERS = {
    "ke_1": 3.0,
    "ke_2": 3.0,
    "a_ed": 4.71e6,
    "d_o": 0.156,
    "k_12": 0.075,
    "k_21": 0.005,
    "d_1": 0.121,
    "d_2": 0.163,
    "k_o": 0.0000005,
    "k_1": 0.0000083,
    "d_c1": 0.2,
    "k_2": 0.00000372,
    "k_3": 0.0000007,
    "d_c2": 0.25,
    "K_lm": 1000000.0,
    "k_lb": 1000000.0,
    "d_b": 0.15,
    "p_cs": 0.000003,
    "q_cd1": 0.000003,
    "q_cd2": 0.000002,
    "p_bs": 0.00000005,
    "q_bd": 0.00000005,
    "aed": 4.71e6,
    "kmax": 0.015,
    "Mmax": 6.0e5,
    "k_01": 0.55,
    "a_01": 0.01,
    "k_02": 0.3,
    "a_02": 0.005,
    "a_12": 0.025,
    "a_22": 0.1,
    "kpm": 0.5,
    "apm": 3.162,
    "apm1": 13.0,
    "dm": 1.0,
    "amb1": 0.1,
    "kpb": 0.2202,
    "apb": 10.0,
    "ae2": 0.5,
    "de2": 0.03,
    "E2max": 0.060,
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


@pytest.mark.parametrize(("name", "value"), sorted(PARAMETERS.items()))
def test_parameter_value(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every parameter has the name and the value of the original code."""
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


@pytest.mark.parametrize(("name", "value"), sorted(INITIAL_CONDITIONS.items()))
def test_initial_condition(
    runner: roadrunner.RoadRunner, name: str, value: float
) -> None:
    """Every state variable starts at the value of the original script."""
    runner.reset()
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


def test_simulation_reaches_the_expected_estradiol_equilibrium(
    runner: roadrunner.RoadRunner,
) -> None:
    """E2 settles at E2max * (1 - de2 / ae2), as the equation implies."""
    runner.reset()
    runner.selections = ["time", *STATE_VARIABLES]
    result = runner.simulate(0, 720, 1000)
    expected = PARAMETERS["E2max"] * (1 - PARAMETERS["de2"] / PARAMETERS["ae2"])
    assert result[-1, -1] == pytest.approx(expected, rel=1e-6)
