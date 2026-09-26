"""Pluggable quantitative metrics comparing the mapped trajectories.

Every metric has the same shape -- ``(original, simplificado) -> float``, both arrays on the
same time grid, smaller is better -- and registers itself under a name with :func:`registrar`.
Adding a metric therefore means adding a function here and its name to
``config.METRICAS_SUPORTADAS``; nothing in the pipeline changes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np

__all__ = ["ErroDeMetrica", "Metrica", "nrmse", "obter", "registrar"]


class ErroDeMetrica(Exception):
    """A métrica não existe, ou não pode ser aplicada a estas séries."""


class Metrica(Protocol):
    """Common signature of every metric: lower is better, 0 means identical."""

    def __call__(self, original: np.ndarray, simplificado: np.ndarray) -> float:
        """Return the error of ``simplificado`` with respect to ``original``."""
        ...


_REGISTRO: dict[str, Metrica] = {}


def registrar(nome: str) -> Callable[[Metrica], Metrica]:
    """Return a decorator that records a metric under ``nome``."""

    def decorador(funcao: Metrica) -> Metrica:
        if nome in _REGISTRO:
            raise ErroDeMetrica(f"A métrica '{nome}' já está registrada.")
        _REGISTRO[nome] = funcao
        return funcao

    return decorador


def obter(nome: str) -> Metrica:
    """Return the metric registered under ``nome``."""
    try:
        return _REGISTRO[nome]
    except KeyError as erro:
        disponiveis = ", ".join(sorted(_REGISTRO))
        raise ErroDeMetrica(
            f"A métrica '{nome}' não existe. Disponíveis: {disponiveis}."
        ) from erro


@registrar("nrmse")
def nrmse(original: np.ndarray, simplificado: np.ndarray) -> float:
    """Return the RMSE normalized by the range (``max - min``) of the original series.

    Normalizing by the range, and not by the mean, is what ``docs/produto.md`` and the toy
    fixtures use; the choice is still open with the supervisor (see
    ``docs/questoes-em-aberto.md``), which is why the report records it next to the number.
    """
    original, simplificado = _conferir_formato(original, simplificado)
    amplitude = float(original.max() - original.min())
    if amplitude == 0.0:
        raise ErroDeMetrica(
            "nrmse: a série do original é constante, então a amplitude usada para normalizar "
            "é zero. Use outra métrica para esta variável."
        )
    rmse = float(np.sqrt(np.mean((original - simplificado) ** 2)))
    return rmse / amplitude


def _conferir_formato(
    original: np.ndarray, simplificado: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    original = np.asarray(original, dtype=float)
    simplificado = np.asarray(simplificado, dtype=float)
    if original.shape != simplificado.shape:
        raise ErroDeMetrica(
            f"As duas séries têm tamanhos diferentes: {original.shape} e {simplificado.shape}."
        )
    if original.size == 0:
        raise ErroDeMetrica("As séries comparadas estão vazias.")
    return original, simplificado
