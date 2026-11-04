"""Compare each NLRP3 notebook (original and simplified) with its SBML translation.

* original: ``dinamica_nlrp3`` from ``nlrp3_original.ipynb`` against
  ``modelos/nlrp3_original.xml``;
* simplified: ``edos`` from ``nlrp3_simplificado.ipynb`` against
  ``modelos/nlrp3_simp.xml``.

Both notebooks are untouched copies of the Google Colab notebooks. The cells
that define the parameters and the functions are executed exactly as they are
in the notebook; the plotting and CSV cells are skipped.

Both sides are integrated with tight tolerances, so that what is left is the
difference between the translation and the notebook, not the solver error:

* notebook: scipy ``solve_ivp`` with BDF (the notebooks' method), rtol 1e-10,
  atol 1e-12;
* SBML: libRoadRunner (CVODE), rtol 1e-10, atol 1e-12.

Both use the same time grid: 0 to 300 minutes with 1001 points. The notebooks
themselves use rtol = atol = 1e-4 and let the solver choose the output times;
the error of those settings against the tight run is printed too, as
context.

Usage::

    python referencia/nlrp3/comparar_sbml.py                # both models
    python referencia/nlrp3/comparar_sbml.py simplificado   # only one

It prints one line per state variable with the maximum relative error and
writes the overlaid plots to ``referencia/nlrp3/comparacao_sbml.png``
(original) and ``referencia/nlrp3/comparacao_sbml_simp.png`` (simplified).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import roadrunner  # noqa: E402
from scipy.integrate import solve_ivp  # noqa: E402

REFERENCE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = REFERENCE_DIR.parents[1]


@dataclass(frozen=True)
class ModelSpec:
    """Where one model lives and how to run its notebook."""

    label: str
    notebook: Path
    sbml: Path
    plot: Path
    function: str
    variables: list[str]
    initial_conditions: list[float]
    cells: tuple[str, ...]


MODELS = {
    "original": ModelSpec(
        label="original",
        notebook=REFERENCE_DIR / "nlrp3_original.ipynb",
        sbml=PROJECT_DIR / "modelos" / "nlrp3_original.xml",
        plot=REFERENCE_DIR / "comparacao_sbml.png",
        function="dinamica_nlrp3",
        # Order of the vector returned by `dinamica_nlrp3`.
        variables=[
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
        ],
        # `valores_iniciais` in the notebook.
        initial_conditions=[0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        # The cells that define the parameters, `nfkbn`, `hill`, `sinal` and
        # `dinamica_nlrp3` start with these lines (the accents are garbled in
        # the notebook, hence the short prefixes).
        cells=("#Par", "#Fun", "#Hill function", "#EDOS para o NLRP3"),
    ),
    "simplificado": ModelSpec(
        label="simplificado",
        notebook=REFERENCE_DIR / "nlrp3_simplificado.ipynb",
        sbml=PROJECT_DIR / "modelos" / "nlrp3_simp.xml",
        plot=REFERENCE_DIR / "comparacao_sbml_simp.png",
        function="edos",
        # Order of the vector returned by `edos`.
        variables=["NLRP3a", "NLRP3o", "ASCb", "C1", "IL18c", "IL18e", "proIL1B", "IL1Be"],
        # `valores_iniciais` in the notebook: all zero.
        initial_conditions=[0.0] * 8,
        cells=("#Par", "#Fun", "#Hill", "def edos"),
    ),
}

# Each notebook has five model cells: parameters, nfkbn, hill, sinal and the ODEs.
MODEL_CELLS = 5

MINUTES = 300.0
POINTS = 1001
RTOL = 1e-10
ATOL = 1e-12

# Same threshold used for the Verly model (issue #4).
TOLERANCE = 1e-4


def load_notebook(spec: ModelSpec) -> Callable:
    """Run the model cells of the notebook and return its ODE function."""
    notebook = json.loads(spec.notebook.read_text(encoding="utf-8"))
    namespace: dict = {"np": np}
    executed = 0
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and source.startswith(spec.cells):
            exec(compile(source, spec.notebook.name, "exec"), namespace)  # noqa: S102
            executed += 1
    if executed != MODEL_CELLS or spec.function not in namespace:
        raise RuntimeError(
            f"{spec.notebook.name}: esperava {MODEL_CELLS} celulas do modelo, "
            f"encontrei {executed}"
        )
    return namespace[spec.function]


def simulate_notebook(
    spec: ModelSpec, times: np.ndarray, rtol: float = RTOL, atol: float = ATOL
) -> np.ndarray:
    """Integrate the notebook's model with BDF on the given time grid."""
    rhs = load_notebook(spec)
    solution = solve_ivp(
        rhs,
        (float(times[0]), float(times[-1])),
        np.array(spec.initial_conditions),
        method="BDF",
        t_eval=times,
        rtol=rtol,
        atol=atol,
    )
    if not solution.success:
        raise RuntimeError(f"solve_ivp falhou: {solution.message}")
    return solution.y.T


def simulate_sbml(spec: ModelSpec, times: np.ndarray) -> np.ndarray:
    """Integrate the SBML model with libRoadRunner (CVODE)."""
    runner = roadrunner.RoadRunner(str(spec.sbml))
    runner.integrator.setValue("relative_tolerance", RTOL)
    runner.integrator.setValue("absolute_tolerance", ATOL)
    runner.selections = ["time", *spec.variables]
    result = runner.simulate(float(times[0]), float(times[-1]), len(times))
    return np.array(result)[:, 1:]


def relative_errors(
    variables: list[str], reference: np.ndarray, other: np.ndarray
) -> list[tuple[str, float, float]]:
    """Return ``(variable, max absolute error, max relative error)`` per variable.

    The relative error is normalised by the largest absolute value the
    variable reaches in the reference run, because most variables start at zero.
    """
    rows: list[tuple[str, float, float]] = []
    for index, name in enumerate(variables):
        absolute = float(np.max(np.abs(reference[:, index] - other[:, index])))
        scale = float(np.max(np.abs(reference[:, index])))
        relative = absolute / scale if scale > 0 else absolute
        rows.append((name, absolute, relative))
    return rows


def plot_comparison(
    spec: ModelSpec, times: np.ndarray, notebook: np.ndarray, sbml: np.ndarray
) -> None:
    """Save the overlaid curves of every state variable."""
    columns = 3
    rows = -(-(len(spec.variables) + 1) // columns)
    figure, axes = plt.subplots(
        rows, columns, figsize=(14, 3.2 * rows), sharex=True, squeeze=False
    )
    for index, name in enumerate(spec.variables):
        axis = axes.flat[index]
        axis.plot(times, notebook[:, index], label="notebook (scipy)", linewidth=2.5)
        axis.plot(
            times, sbml[:, index], label="SBML (roadrunner)", linewidth=1.2, ls="--"
        )
        axis.set_title(name)
        axis.set_xlabel("tempo (min)")
    for axis in list(axes.flat)[len(spec.variables) :]:
        axis.axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc="center")
    figure.suptitle(f"Modelo NLRP3 ({spec.label}): notebook x SBML")
    figure.tight_layout()
    figure.savefig(spec.plot, dpi=150)
    plt.close(figure)


def compare(spec: ModelSpec) -> float:
    """Compare one notebook with its SBML, print the tables and return the worst error."""
    times = np.linspace(0.0, MINUTES, POINTS)
    notebook = simulate_notebook(spec, times)
    sbml = simulate_sbml(spec, times)

    print(f"=== Modelo {spec.label}: {spec.notebook.name} x {spec.sbml.name}")
    print("notebook (scipy BDF) x SBML (roadrunner CVODE), rtol 1e-10, atol 1e-12")
    print(f"{'variavel':<10}{'erro abs. max':>18}{'erro rel. max':>18}  situacao")
    worst = 0.0
    for name, absolute, relative in relative_errors(spec.variables, notebook, sbml):
        worst = max(worst, relative)
        status = "ok" if relative < TOLERANCE else "ACIMA DA TOLERANCIA"
        print(f"{name:<10}{absolute:>18.6e}{relative:>18.6e}  {status}")
    print(f"\nerro relativo maximo entre as variaveis: {worst:.6e}")
    print(f"tolerancia (a mesma da issue #4): {TOLERANCE:.0e}")

    loose = simulate_notebook(spec, times, rtol=1e-4, atol=1e-4)
    loose_worst = max(r for _, _, r in relative_errors(spec.variables, notebook, loose))
    print(
        "\npara contexto: com as tolerancias do notebook (rtol = atol = 1e-4), o "
        f"proprio notebook difere da execucao precisa em ate {loose_worst:.3e}"
    )

    plot_comparison(spec, times, notebook, sbml)
    print(f"\ngrafico salvo em {spec.plot.relative_to(PROJECT_DIR).as_posix()}\n")
    return worst


def main(argv: list[str]) -> int:
    """Compare the models named in ``argv`` (default: both)."""
    names = argv or list(MODELS)
    unknown = [name for name in names if name not in MODELS]
    if unknown:
        print(f"modelo desconhecido: {', '.join(unknown)} (use: {', '.join(MODELS)})")
        return 2
    worst = max(compare(MODELS[name]) for name in names)
    return 0 if worst < TOLERANCE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
