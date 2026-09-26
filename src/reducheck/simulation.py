"""Simulate both models under identical time grid, solver and tolerances.

Every simulation goes through :func:`simular`, which takes the same
:class:`~reducheck.config.Simulacao` for both models. That is what makes the two
trajectories comparable point by point: the caller cannot accidentally give one model a
different horizon, solver or tolerance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import roadrunner

from reducheck.config import SOLVERS_SUPORTADOS, Simulacao

__all__ = ["ErroDeSimulacao", "Trajetorias", "simular"]


class ErroDeSimulacao(Exception):
    """O modelo não pôde ser carregado ou simulado nas condições pedidas."""


@dataclass(frozen=True)
class Trajetorias:
    """The result of one simulation: a time vector plus one column per requested variable."""

    #: Shape (n,), the same for both models of a comparison.
    tempo: np.ndarray
    #: Names of the columns of :attr:`estados`, in order.
    nomes: tuple[str, ...]
    #: Shape (n, len(nomes)).
    estados: np.ndarray

    def serie(self, nome: str) -> np.ndarray:
        """Return the column of ``nome``."""
        try:
            return self.estados[:, self.nomes.index(nome)]
        except ValueError as erro:
            disponiveis = ", ".join(self.nomes)
            raise KeyError(
                f"A variável '{nome}' não foi simulada. Disponíveis: {disponiveis}."
            ) from erro


def simular(
    caminho_sbml: Path | str, condicoes: Simulacao, variaveis: Sequence[str]
) -> Trajetorias:
    """Simulate the SBML model at ``caminho_sbml`` and return ``variaveis`` over time."""
    if condicoes.solver not in SOLVERS_SUPORTADOS:
        suportados = ", ".join(sorted(SOLVERS_SUPORTADOS))
        raise ErroDeSimulacao(
            f"O solver '{condicoes.solver}' não é suportado. Disponíveis: {suportados}."
        )
    if not variaveis:
        raise ErroDeSimulacao(f"Nenhuma variável pedida para '{caminho_sbml}'.")

    modelo = _carregar(caminho_sbml)
    _exigir_variaveis_existentes(modelo, variaveis, caminho_sbml)

    modelo.setIntegrator(condicoes.solver)
    modelo.integrator.relative_tolerance = condicoes.tol_relativa
    modelo.integrator.absolute_tolerance = condicoes.tol_absoluta
    modelo.selections = ["time", *variaveis]

    try:
        saida = np.asarray(
            modelo.simulate(condicoes.t_inicio, condicoes.t_fim, condicoes.pontos), dtype=float
        )
    except RuntimeError as erro:
        raise ErroDeSimulacao(f"A simulação de '{caminho_sbml}' falhou: {erro}") from erro

    if not np.isfinite(saida).all():
        raise ErroDeSimulacao(
            f"A simulação de '{caminho_sbml}' produziu valores não finitos (NaN ou infinito)."
        )

    return Trajetorias(tempo=saida[:, 0], nomes=tuple(variaveis), estados=saida[:, 1:])


def _carregar(caminho_sbml: Path | str) -> roadrunner.RoadRunner:
    try:
        return roadrunner.RoadRunner(str(caminho_sbml))
    except RuntimeError as erro:
        raise ErroDeSimulacao(
            f"Não foi possível carregar o SBML '{caminho_sbml}': {erro}"
        ) from erro


def _exigir_variaveis_existentes(
    modelo: roadrunner.RoadRunner, variaveis: Sequence[str], caminho_sbml: Path | str
) -> None:
    """Fail before simulating when a requested name is not in the model."""
    conhecidas = {
        *modelo.model.getFloatingSpeciesIds(),
        *modelo.model.getBoundarySpeciesIds(),
        *modelo.model.getGlobalParameterIds(),
    }
    ausentes = [nome for nome in variaveis if nome not in conhecidas]
    if ausentes:
        disponiveis = ", ".join(sorted(conhecidas))
        raise ErroDeSimulacao(
            f"O modelo '{caminho_sbml}' não tem a variável {', '.join(ausentes)}. "
            f"Disponíveis: {disponiveis}."
        )
