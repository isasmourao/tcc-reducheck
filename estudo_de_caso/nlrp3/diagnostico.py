"""Diagnose why the simplified NLRP3 model fails each criterion.

Separates the possible causes of a failed criterion in Julia's test model:
values close to zero inflating a relative metric, delays in the cascade, and
the effect of the recalibrated parameter ``novodelta1``. The numbers are
recorded in ``estudo_de_caso/nlrp3/NOTAS.md`` (section "Diagnóstico").

Usage, from the repository root::

    python estudo_de_caso/nlrp3/diagnostico.py

Both models are simulated with libRoadRunner under the same conditions as
``nlrp3_simp.yaml`` (0 to 300 min, 1001 points, rtol 1e-8, atol 1e-10).
Nothing here changes the models or the verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import roadrunner

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "modelos" / "nlrp3_original.xml"
SIMPLIFIED = ROOT / "modelos" / "nlrp3_simp.xml"

TIMES = np.linspace(0.0, 300.0, 1001)

# (name in the original, name in the simplified)
PAIRS = [
    ("NLRP3a", "NLRP3a"),
    ("NLRP3o", "NLRP3o"),
    ("ASCb", "ASCb"),
    ("C1", "C1"),
    ("IL18c", "IL18c"),
    ("IL18e", "IL18e"),
    ("proIL1b", "proIL1B"),
    ("IL1be", "IL1Be"),
]

# MAPE is recomputed leaving out the points below this fraction of the peak.
PEAK_FRACTION = 0.05


def simulate(path: Path, variables: list[str], **parameters: float) -> np.ndarray:
    """Simulate one model and return one column per variable."""
    runner = roadrunner.RoadRunner(str(path))
    runner.integrator.relative_tolerance = 1e-8
    runner.integrator.absolute_tolerance = 1e-10
    for name, value in parameters.items():
        runner[name] = value
    runner.selections = ["time", *variables]
    result = runner.simulate(float(TIMES[0]), float(TIMES[-1]), len(TIMES))
    return np.array(result)[:, 1:]


def crossing_time(series: np.ndarray, level: float) -> float:
    """Return the first time the series reaches ``level``, or NaN if it never does."""
    index = int(np.argmax(series >= level))
    return float(TIMES[index]) if series[index] >= level else float("nan")


def mape(original: np.ndarray, simplified: np.ndarray, mask: np.ndarray) -> float:
    """Return the mean relative error over the points selected by ``mask``."""
    return float(np.mean(np.abs(simplified[mask] - original[mask]) / np.abs(original[mask])))


def main() -> int:
    """Print the four diagnostic tables."""
    original = simulate(ORIGINAL, [pair[0] for pair in PAIRS])
    simplified = simulate(SIMPLIFIED, [pair[1] for pair in PAIRS])

    print("1) Valor final em relacao ao pico (o erro estacionario divide pelo valor final)")
    for index, (name, _) in enumerate(PAIRS):
        o, s = original[:, index], simplified[:, index]
        peak = o.max()
        print(
            f"  {name:<8} pico {peak:.4f}  final orig {o[-1]:.3e}  final simp {s[-1]:.3e}  "
            f"final/pico {o[-1] / peak:7.2%}  diferenca final/pico {abs(s[-1] - o[-1]) / peak:.2%}"
        )

    print(f"\n2) MAPE: todos os pontos x so os pontos acima de {PEAK_FRACTION:.0%} do pico")
    for index, (name, _) in enumerate(PAIRS):
        o, s = original[:, index], simplified[:, index]
        every = o > 1e-6 * max(o.max(), 1.0)
        above = o > PEAK_FRACTION * o.max()
        print(f"  {name:<8} todos {mape(o, s, every):7.1%}   acima {mape(o, s, above):7.1%}")

    print("\n3) Atraso: quando chega a 50% do pico (NLRP3o: quando cruza 1)")
    for index, (name, _) in enumerate(PAIRS):
        o, s = original[:, index], simplified[:, index]
        level = 1.0 if name == "NLRP3o" else 0.5 * o.max()
        t_o, t_s = crossing_time(o, level), crossing_time(s, level)
        print(f"  {name:<8} orig {t_o:6.1f} min  simp {t_s:6.1f} min  diferenca {t_s - t_o:+5.1f}")

    print("\n4) Papel do novodelta1 (o original usa delta1 = 0.002)")
    for value in (0.0025, 0.002):
        run = simulate(SIMPLIFIED, ["NLRP3o", "ASCb"], novodelta1=value)
        print(
            f"  novodelta1 = {value}: NLRP3o final {run[-1, 0]:.5f}, "
            f"cruza 1 em {crossing_time(run[:, 0], 1.0):.1f} min, "
            f"ASCb a 50% em {crossing_time(run[:, 1], 0.5):.1f} min"
        )
    o_nlrp3o = original[:, [p[0] for p in PAIRS].index("NLRP3o")]
    print(
        f"  original: NLRP3o final {o_nlrp3o[-1]:.5f}, "
        f"cruza 1 em {crossing_time(o_nlrp3o, 1.0):.1f} min"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
