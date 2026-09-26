"""Check that the toy fixtures load, simulate and keep their known verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest
import roadrunner

FIXTURES_DIR = Path(__file__).parent / "fixtures"

#: Threshold used by the reference criterion of the product document.
NRMSE_LIMIT = 0.05

#: Solver settings shared by every simulation in this module.
ABSOLUTE_TOLERANCE = 1e-10
RELATIVE_TOLERANCE = 1e-8


@dataclass(frozen=True)
class Pair:
    """One original/simplified pair with its expected verdict."""

    name: str
    original: str
    simplified: str
    #: Variable of the simplified model -> variables of the original summed into it.
    mapping: dict[str, tuple[str, ...]]
    t_end: float
    n_points: int
    should_pass: bool
    #: Recorded range-normalized NRMSE per simplified variable.
    expected_nrmse: dict[str, float] = field(default_factory=dict)


PAIRS: tuple[Pair, ...] = (
    Pair(
        name="qssa_ok",
        original="qssa_ok_original",
        simplified="qssa_ok_simplified",
        mapping={"A": ("A",), "C": ("C",)},
        t_end=40.0,
        n_points=401,
        should_pass=True,
        expected_nrmse={"A": 0.0, "C": 0.00072},
    ),
    Pair(
        name="qssa_fail",
        original="qssa_fail_original",
        simplified="qssa_fail_simplified",
        mapping={"A": ("A",), "C": ("C",)},
        t_end=40.0,
        n_points=401,
        should_pass=False,
        expected_nrmse={"A": 0.0, "C": 0.52006},
    ),
    Pair(
        name="aggregation",
        original="aggregation_original",
        simplified="aggregation_simplified",
        mapping={"X": ("X1", "X2")},
        t_end=50.0,
        n_points=501,
        should_pass=True,
        expected_nrmse={"X": 0.00523},
    ),
)

ALL_MODELS = sorted(p.stem for p in FIXTURES_DIR.glob("*.xml"))


def simulate(model: str, selections: list[str], t_end: float, n_points: int) -> np.ndarray:
    """Simulate one fixture and return the requested columns as an array."""
    rr = roadrunner.RoadRunner(str(FIXTURES_DIR / f"{model}.xml"))
    rr.integrator.absolute_tolerance = ABSOLUTE_TOLERANCE
    rr.integrator.relative_tolerance = RELATIVE_TOLERANCE
    rr.selections = selections
    return np.asarray(rr.simulate(0.0, t_end, n_points))


def nrmse(reference: np.ndarray, candidate: np.ndarray) -> float:
    """Return the RMSE normalized by the range of the reference series."""
    rmse = float(np.sqrt(np.mean((reference - candidate) ** 2)))
    span = float(reference.max() - reference.min())
    return rmse / span


def test_every_ant_file_has_an_sbml_file() -> None:
    ant_files = sorted(p.stem for p in FIXTURES_DIR.glob("*.ant"))
    assert ant_files == ALL_MODELS
    assert len(ALL_MODELS) == 2 * len(PAIRS)


@pytest.mark.parametrize("model", ALL_MODELS)
def test_model_loads_and_simulates(model: str) -> None:
    result = simulate(model, ["time"], t_end=10.0, n_points=11)
    assert result.shape == (11, 1)
    assert np.isfinite(result).all()


@pytest.mark.parametrize("pair", PAIRS, ids=lambda pair: pair.name)
def test_pair_reproduces_the_recorded_nrmse(pair: Pair) -> None:
    originals = sorted({name for names in pair.mapping.values() for name in names})
    reference = simulate(pair.original, ["time", *originals], pair.t_end, pair.n_points)
    candidate = simulate(pair.simplified, ["time", *pair.mapping], pair.t_end, pair.n_points)

    np.testing.assert_allclose(reference[:, 0], candidate[:, 0])

    for variable, sources in pair.mapping.items():
        summed = sum(reference[:, 1 + originals.index(name)] for name in sources)
        measured = nrmse(summed, candidate[:, 1 + list(pair.mapping).index(variable)])
        assert measured == pytest.approx(pair.expected_nrmse[variable], abs=1e-4)


@pytest.mark.parametrize("pair", PAIRS, ids=lambda pair: pair.name)
def test_pair_verdict_is_unambiguous(pair: Pair) -> None:
    worst = max(pair.expected_nrmse.values())
    if pair.should_pass:
        assert worst < NRMSE_LIMIT / 2
    else:
        assert worst > NRMSE_LIMIT * 2
