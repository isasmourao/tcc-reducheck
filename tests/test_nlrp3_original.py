"""Checks on the SBML translation of the NLRP3 inflammasome model.

The full comparison against the original notebook lives in
``referencia/nlrp3/comparar_sbml.py``; these tests only guard the SBML file
itself, so that a typo in ``modelos/nlrp3_original.ant`` is caught by CI.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import roadrunner

MODEL_PATH = Path(__file__).resolve().parents[1] / "modelos" / "nlrp3_original.xml"

# `valores_iniciais` of the notebook, in the order of `dinamica_nlrp3`.
INITIAL_CONDITIONS = {
    "NLRP3i": 0.0,
    "NLRP3a": 0.0,
    "NLRP3o": 0.0,
    "ASCf": 1.0,
    "ASCb": 0.0,
    "proC1": 1.0,
    "C1": 0.0,
    "proIL1b": 0.0,
    "IL1bc": 0.0,
    "IL1be": 0.0,
    "proIL18": 1.0,
    "IL18c": 0.0,
    "IL18e": 0.0,
}

# Every parameter of the notebook, with its value.
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
    "delta1": 0.002,
    "k2": 1,
    "k3": 0.04,
    "a": 1,
    "b": 2,
    "c": 1000,
    "k4": 0.03,
    "C1_50": 0.3,
    "gammaC1": 2,
    "G": 0.08,
    "alpha3": 0.06,
    "alpha4": 1,
    "alpha5": 1,
    "k5": 1,
    "delta2": 0.004,
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
    """Every parameter has the name and the value of the notebook."""
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


@pytest.mark.parametrize(("name", "value"), sorted(INITIAL_CONDITIONS.items()))
def test_initial_condition(
    runner: roadrunner.RoadRunner, name: str, value: float
) -> None:
    """Every state variable starts at the value of the notebook."""
    runner.reset()
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


def test_nfkb_input_is_025_at_time_zero(runner: roadrunner.RoadRunner) -> None:
    """The notebook's special case nfkbn(0) = 0.25 holds without a piecewise."""
    runner.reset()
    assert runner["nfkbn"] == 0.25


@pytest.mark.parametrize("minutes", [1.0, 10.0, 37.5, 300.0])
def test_nfkb_input_matches_the_notebook_formula(minutes: float) -> None:
    """nfkbn(t) = S1*h*exp(-(ln(t/tau))^2/s) + nfkb0 for t > 0."""
    model = roadrunner.RoadRunner(str(MODEL_PATH))
    model.simulate(0, minutes, 2)
    p = PARAMETERS
    expected = (
        p["S1"] * p["h"] * math.exp(-(math.log(minutes / p["tau"]) ** 2) / p["s"])
        + p["nfkb0"]
    )
    assert model["nfkbn"] == pytest.approx(expected, rel=1e-12)


def test_conserved_totals(runner: roadrunner.RoadRunner) -> None:
    """ASC, caspase-1 and IL-18 only move between their own forms."""
    runner.reset()
    runner.integrator.setValue("relative_tolerance", 1e-10)
    runner.integrator.setValue("absolute_tolerance", 1e-12)
    runner.simulate(0, 300, 301)
    assert runner["ASCf"] + runner["ASCb"] == pytest.approx(1.0, abs=1e-8)
    assert runner["proC1"] + runner["C1"] == pytest.approx(1.0, abs=1e-8)
    assert runner["proIL18"] + runner["IL18c"] + runner["IL18e"] == pytest.approx(
        1.0, abs=1e-8
    )
