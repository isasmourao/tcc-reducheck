"""Checks on the SBML translation of simplification 1 of the Verly model.

These tests guard `modelos/verly_simp1.ant` against typos, and they pin the two
structural consequences of the simplification that the case study is about: the
variables removed with `Cm` and `Mc` are really gone, and with the provisional
`Es = 0` the osteoblasts never leave zero.

The equations come from `referencia/simplificacao_2026-04-22.md`; the numbers of
the comparison against the original live in `estudo_de_caso/NOTAS.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import roadrunner

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "modelos" / "verly_simp1.xml"
ORIGINAL_PATH = ROOT / "modelos" / "verly_original.xml"

STATE_VARIABLES = ["D", "Mo", "M1", "M2", "C1", "C2", "Cb", "Mb", "E2"]

# Removed with Cm and Mc, according to the note of 2026-04-22.
REMOVED_VARIABLES = ["Cm", "Mc"]
REMOVED_PARAMETERS = [
    "kpm",
    "apm",
    "apm1",
    "K_lm",
    "dm",
    "amb1",
    "p_cs",
    "q_cd1",
    "q_cd2",
    "k_3",
]

# Every parameter kept from the original, with the value of the original code,
# plus Es, which the note introduces in the place of the term F1 * Cm.
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
    "d_c2": 0.25,
    "k_lb": 1000000.0,
    "d_b": 0.15,
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
    "kpb": 0.2202,
    "apb": 10.0,
    "ae2": 0.5,
    "de2": 0.03,
    "E2max": 0.060,
    "Es": 0.0,
}

INITIAL_CONDITIONS = {
    "D": 1000000.0,
    "Mo": 4000.0,
    "M1": 0.0,
    "M2": 0.0,
    "C1": 0.0,
    "C2": 0.0,
    "Cb": 0.0,
    "Mb": 0.0,
    "E2": 0.060,
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


def test_has_nine_state_variables(runner: roadrunner.RoadRunner) -> None:
    """The simplification keeps exactly the nine variables of the note.

    As in `verly_original.ant`, the state variables are rate rules over plain
    parameters, not species in a compartment, so they are listed by
    `getRateRuleIds`.
    """
    assert sorted(runner.getRateRuleIds()) == sorted(STATE_VARIABLES)


@pytest.mark.parametrize("name", REMOVED_VARIABLES + REMOVED_PARAMETERS)
def test_removed_symbol_is_absent(runner: roadrunner.RoadRunner, name: str) -> None:
    """Nothing removed by the simplification survives in the SBML."""
    assert name not in runner.model.getGlobalParameterIds()


@pytest.mark.parametrize(("name", "value"), sorted(PARAMETERS.items()))
def test_parameter_value(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every kept parameter has the name and the value of the original code."""
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


@pytest.mark.parametrize(("name", "value"), sorted(INITIAL_CONDITIONS.items()))
def test_initial_condition(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every state variable starts at the value of the original script."""
    runner.reset()
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


def test_osteoblasts_stay_at_zero_while_es_is_zero(
    runner: roadrunner.RoadRunner,
) -> None:
    """With Es = 0 the equation of Cb is homogeneous, so Cb and Mb never leave 0.

    This is the central finding of the case study, not a defect of the library:
    `F1 * Cm` was the only term of `dCb/dt` that does not carry a factor of `Cb`,
    so removing it leaves bone formation with no source. It is what makes the
    open question about `Es` worth answering (see `docs/questoes-em-aberto.md`).
    """
    runner.reset()
    runner.selections = ["time", "Cb", "Mb"]
    result = runner.simulate(0, 720, 1000)
    assert result[:, 1].max() == 0.0
    assert result[:, 2].max() == 0.0


def test_a_positive_es_does_start_bone_formation(
    runner: roadrunner.RoadRunner,
) -> None:
    """The zero above comes from Es, not from a typo in the rest of the equation."""
    runner.reset()
    runner["Es"] = 1.0e4
    runner.selections = ["time", "Cb", "Mb"]
    result = runner.simulate(0, 720, 1000)
    runner["Es"] = 0.0
    assert result[:, 1].max() > 0.0
    assert result[:, 2].max() > 0.0


def test_estradiol_matches_the_original_exactly() -> None:
    """E2 is untouched by the simplification, so the two models must agree on it.

    `dE2/dt` does not depend on any other variable, so any difference here would
    mean a typo in the transcription rather than an effect of the simplification.
    """
    simplified = roadrunner.RoadRunner(str(MODEL_PATH))
    original = roadrunner.RoadRunner(str(ORIGINAL_PATH))
    for model in (simplified, original):
        model.integrator.relative_tolerance = 1e-8
        model.integrator.absolute_tolerance = 1e-10
        model.selections = ["time", "E2"]
    assert simplified.simulate(0, 720, 1000)[-1, 1] == pytest.approx(
        original.simulate(0, 720, 1000)[-1, 1], rel=1e-8
    )
