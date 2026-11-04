"""Compare the original NLRP3 notebook with its SBML translation.

The original model is ``dinamica_nlrp3`` from ``nlrp3_original.ipynb`` (an
untouched copy of the Google Colab notebook). The cells that define the
parameters and the functions are executed exactly as they are in the
notebook; the plotting and CSV cells are skipped.

Both models are integrated with tight tolerances, so that what is left is the
difference between the translation and the original, not the solver error:

* original: scipy ``solve_ivp`` with BDF (the notebook's method), rtol 1e-10,
  atol 1e-12;
* SBML: ``modelos/nlrp3_original.xml`` with libRoadRunner (CVODE), rtol 1e-10,
  atol 1e-12.

Both use the same time grid: 0 to 300 minutes with 1001 points. The notebook
itself uses rtol = atol = 1e-4 and lets the solver choose the output times;
the error of those settings against the tight run is printed too, as
context.

Usage::

    python referencia/nlrp3/comparar_sbml.py

It prints one line per state variable with the maximum relative error and
writes the overlaid plot to ``referencia/nlrp3/comparacao_sbml.png``.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import roadrunner  # noqa: E402
from scipy.integrate import solve_ivp  # noqa: E402

REFERENCE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = REFERENCE_DIR.parents[1]
NOTEBOOK_PATH = REFERENCE_DIR / "nlrp3_original.ipynb"
SBML_PATH = PROJECT_DIR / "modelos" / "nlrp3_original.xml"
PLOT_PATH = REFERENCE_DIR / "comparacao_sbml.png"

# Order of the vector returned by `dinamica_nlrp3`.
VARIABLES = [
    "NLRP3i",
    "NLRP3a",
    "NLRP3o",
    "ASCf",
    "ASCb",
    "proC1",
    "C1",
    "proIL1b",
    "IL1bc",
    "IL1be",
    "proIL18",
    "IL18c",
    "IL18e",
]

# `valores_iniciais` in the notebook.
INITIAL_CONDITIONS = [0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]

MINUTES = 300.0
POINTS = 1001
RTOL = 1e-10
ATOL = 1e-12

# Same threshold used for the Verly model (issue #4).
TOLERANCE = 1e-4

# A cell is executed when its source starts with one of these lines: the
# parameters, `nfkbn`, `hill`, `sinal` and `dinamica_nlrp3`.
CELLS_TO_RUN = (
    "#Par",  # "#Parâmetros NF-kB" (the accent is garbled in the notebook)
    "#Fun",  # "#Função para determinar NF-kB"
    "#Hill function",
    "#Fun",  # "#Função sinalizadora de ASC"
    "#EDOS para o NLRP3",
)


def load_original() -> tuple[Callable, Callable]:
    """Run the model cells of the notebook and return ``dinamica_nlrp3`` and ``nfkbn``."""
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    namespace: dict = {"np": np}
    executed = 0
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and source.startswith(CELLS_TO_RUN):
            exec(compile(source, NOTEBOOK_PATH.name, "exec"), namespace)  # noqa: S102
            executed += 1
    if executed != 5 or "dinamica_nlrp3" not in namespace:
        raise RuntimeError(
            f"esperava 5 celulas do modelo no notebook, encontrei {executed}"
        )
    return namespace["dinamica_nlrp3"], namespace["nfkbn"]


def simulate_original(
    times: np.ndarray, rtol: float = RTOL, atol: float = ATOL
) -> np.ndarray:
    """Integrate the notebook's model with BDF on the given time grid."""
    dinamica_nlrp3, _ = load_original()
    solution = solve_ivp(
        dinamica_nlrp3,
        (float(times[0]), float(times[-1])),
        np.array(INITIAL_CONDITIONS),
        method="BDF",
        t_eval=times,
        rtol=rtol,
        atol=atol,
    )
    if not solution.success:
        raise RuntimeError(f"solve_ivp falhou: {solution.message}")
    return solution.y.T


def simulate_sbml(times: np.ndarray) -> np.ndarray:
    """Integrate the SBML model with libRoadRunner (CVODE)."""
    runner = roadrunner.RoadRunner(str(SBML_PATH))
    runner.integrator.setValue("relative_tolerance", RTOL)
    runner.integrator.setValue("absolute_tolerance", ATOL)
    runner.selections = ["time", *VARIABLES]
    result = runner.simulate(float(times[0]), float(times[-1]), len(times))
    return np.array(result)[:, 1:]


def relative_errors(
    original: np.ndarray, other: np.ndarray
) -> list[tuple[str, float, float]]:
    """Return ``(variable, max absolute error, max relative error)`` per variable.

    The relative error is normalised by the largest absolute value the
    variable reaches in the original, because most variables start at zero.
    """
    rows: list[tuple[str, float, float]] = []
    for index, name in enumerate(VARIABLES):
        reference = original[:, index]
        absolute = float(np.max(np.abs(reference - other[:, index])))
        scale = float(np.max(np.abs(reference)))
        relative = absolute / scale if scale > 0 else absolute
        rows.append((name, absolute, relative))
    return rows


def plot_comparison(
    times: np.ndarray, original: np.ndarray, sbml: np.ndarray, path: Path
) -> None:
    """Save the overlaid curves of the thirteen variables."""
    figure, axes = plt.subplots(5, 3, figsize=(14, 16), sharex=True)
    for index, name in enumerate(VARIABLES):
        axis = axes.flat[index]
        axis.plot(times, original[:, index], label="original (scipy)", linewidth=2.5)
        axis.plot(
            times, sbml[:, index], label="SBML (roadrunner)", linewidth=1.2, ls="--"
        )
        axis.set_title(name)
        axis.set_xlabel("tempo (min)")
    axes.flat[-2].axis("off")
    axes.flat[-1].axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc="center")
    figure.suptitle("Modelo NLRP3: notebook original x SBML")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main() -> int:
    """Run both simulations, print the error tables and save the plot."""
    times = np.linspace(0.0, MINUTES, POINTS)
    original = simulate_original(times)
    sbml = simulate_sbml(times)

    print("Original (scipy BDF) x SBML (roadrunner CVODE), rtol 1e-10, atol 1e-12")
    print(f"{'variavel':<10}{'erro abs. max':>18}{'erro rel. max':>18}  situacao")
    worst = 0.0
    for name, absolute, relative in relative_errors(original, sbml):
        worst = max(worst, relative)
        status = "ok" if relative < TOLERANCE else "ACIMA DA TOLERANCIA"
        print(f"{name:<10}{absolute:>18.6e}{relative:>18.6e}  {status}")
    print(f"\nerro relativo maximo entre as variaveis: {worst:.6e}")
    print(f"tolerancia (a mesma da issue #4): {TOLERANCE:.0e}")

    notebook_run = simulate_original(times, rtol=1e-4, atol=1e-4)
    notebook_worst = max(r for _, _, r in relative_errors(original, notebook_run))
    print(
        "\npara contexto: com as tolerancias do notebook (rtol = atol = 1e-4), o "
        f"proprio original difere da execucao precisa em ate {notebook_worst:.3e}"
    )

    plot_comparison(times, original, sbml, PLOT_PATH)
    print(f"\ngrafico salvo em {PLOT_PATH.relative_to(PROJECT_DIR).as_posix()}")

    return 0 if worst < TOLERANCE else 1


if __name__ == "__main__":
    sys.exit(main())
