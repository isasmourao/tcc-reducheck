"""Compare the original Python model with the SBML translation.

The original model (``referencia/bone_estradiol.py``, an untouched copy of
``original_Model/bone_estradiol.py`` from isasmourao/TCC-bone_estradiol) is
integrated with scipy's ``odeint`` (LSODA), exactly as in the original script.
The SBML model (``modelos/verly_original.xml``) is integrated with
libRoadRunner (CVODE, rtol 1e-10, atol 1e-12). Both use the same time grid:
0 to 720 days with 1000 points.

Usage::

    python referencia/comparar_sbml.py

It prints one line per state variable with the maximum relative error and
writes the overlaid plot to ``referencia/comparacao_sbml.png``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import roadrunner  # noqa: E402
from scipy.integrate import odeint  # noqa: E402

REFERENCE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = REFERENCE_DIR.parent
SBML_PATH = PROJECT_DIR / "modelos" / "verly_original.xml"
PLOT_PATH = REFERENCE_DIR / "comparacao_sbml.png"

VARIABLES = ["D", "Mo", "M1", "M2", "C1", "C2", "Cm", "Cb", "Mc", "Mb", "E2"]

# Initial conditions of the original script, in the order of `bonerepair`.
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

# In the original script `bonerepair` is always called with E2_max equal to
# the initial value of E2; this comparison reproduces the first run (0.060).
E2_MAX = 0.060

DAYS = 720
POINTS = 1000

# Threshold accepted in issue #4 for the maximum relative error.
TOLERANCE = 1e-4


def load_bonerepair():
    """Import ``bonerepair`` from the untouched copy of the original script.

    The original file imports ``post_processing`` and plots at import time, so
    a no-op stand-in is installed before importing it. The file itself is
    never modified.
    """
    stub = types.ModuleType("post_processing")
    stub.plots = lambda *args, **kwargs: None
    stub.plots_estradiol = lambda *args, **kwargs: None
    sys.modules["post_processing"] = stub

    path = REFERENCE_DIR / "bone_estradiol.py"
    spec = importlib.util.spec_from_file_location("bone_estradiol", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"nao foi possivel carregar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bone_estradiol"] = module
    spec.loader.exec_module(module)
    return module.bonerepair


def simulate_original(times: np.ndarray) -> np.ndarray:
    """Integrate the original Python model with LSODA, as in the script."""
    bonerepair = load_bonerepair()
    y0 = np.array([INITIAL_CONDITIONS[name] for name in VARIABLES])
    return odeint(bonerepair, y0, times, args=(E2_MAX,))


def simulate_sbml(times: np.ndarray) -> np.ndarray:
    """Integrate the SBML model with libRoadRunner (CVODE)."""
    runner = roadrunner.RoadRunner(str(SBML_PATH))
    runner.integrator.setValue("relative_tolerance", 1e-10)
    runner.integrator.setValue("absolute_tolerance", 1e-12)
    runner.selections = ["time", *VARIABLES]
    result = runner.simulate(float(times[0]), float(times[-1]), len(times))
    return np.array(result)[:, 1:]


def relative_errors(
    original: np.ndarray, sbml: np.ndarray
) -> list[tuple[str, float, float]]:
    """Return ``(variable, max absolute error, max relative error)`` per variable.

    The relative error of each variable is normalised by the scale of its own
    trajectory (the maximum absolute value reached in the original model),
    because six of the eleven variables start at zero and a pointwise ratio
    would be undefined there.
    """
    rows: list[tuple[str, float, float]] = []
    for index, name in enumerate(VARIABLES):
        reference = original[:, index]
        difference = np.abs(reference - sbml[:, index])
        scale = np.max(np.abs(reference))
        absolute = float(np.max(difference))
        relative = float(absolute / scale) if scale > 0 else absolute
        rows.append((name, absolute, relative))
    return rows


def plot_comparison(
    times: np.ndarray, original: np.ndarray, sbml: np.ndarray, path: Path
) -> None:
    """Save the overlaid curves of the eleven variables."""
    figure, axes = plt.subplots(4, 3, figsize=(14, 12), sharex=True)
    for index, name in enumerate(VARIABLES):
        axis = axes.flat[index]
        axis.plot(times, original[:, index], label="original (scipy)", linewidth=2.5)
        axis.plot(
            times, sbml[:, index], label="SBML (roadrunner)", linewidth=1.2, ls="--"
        )
        axis.set_title(name)
        axis.set_xlabel("tempo (dias)")
    axes.flat[-1].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc="center")
    figure.suptitle("Modelo de Verly et al. (2024): codigo original x SBML")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main() -> int:
    """Run both simulations, print the error table and save the plot."""
    times = np.linspace(0, DAYS, POINTS)
    original = simulate_original(times)
    sbml = simulate_sbml(times)

    rows = relative_errors(original, sbml)
    print(f"{'variavel':<10}{'erro abs. max':>18}{'erro rel. max':>18}  situacao")
    worst = 0.0
    for name, absolute, relative in rows:
        worst = max(worst, relative)
        status = "ok" if relative < TOLERANCE else "ACIMA DA TOLERANCIA"
        print(f"{name:<10}{absolute:>18.6e}{relative:>18.6e}  {status}")
    print(f"\nerro relativo maximo entre as variaveis: {worst:.6e}")
    print(f"tolerancia da issue #4: {TOLERANCE:.0e}")

    plot_comparison(times, original, sbml, PLOT_PATH)
    print(f"grafico salvo em {PLOT_PATH.relative_to(PROJECT_DIR)}")

    return 0 if worst < TOLERANCE else 1


if __name__ == "__main__":
    sys.exit(main())
