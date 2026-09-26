"""Match variables between the original and the simplified model.

This version only handles the 1:1 case (same name or renamed). Sum and weighted sum are a
later task; the type returned here already carries the *combined* original series, so those
will only change how :func:`mapear` fills it, not what the metrics receive.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from reducheck.config import Variavel
from reducheck.simulation import Trajetorias

__all__ = ["ErroDeMapeamento", "SerieComparada", "mapear"]


class ErroDeMapeamento(Exception):
    """As variáveis declaradas não puderam ser casadas com as séries simuladas."""


@dataclass(frozen=True)
class SerieComparada:
    """The two series a metric compares, already on the same time grid."""

    #: Name used in the report.
    nome: str
    tempo: np.ndarray
    #: Series of the original model, after combining its variables (here, just one).
    original: np.ndarray
    #: Series of the corresponding variable of the simplified model.
    simplificado: np.ndarray


def mapear(
    variaveis: Sequence[Variavel], original: Trajetorias, simplificado: Trajetorias
) -> dict[str, SerieComparada]:
    """Pair, for each declared variable, the original series with the simplified one."""
    if not np.array_equal(original.tempo, simplificado.tempo):
        raise ErroDeMapeamento(
            "Os dois modelos foram simulados em vetores de tempo diferentes; "
            "não é possível comparar as séries ponto a ponto."
        )

    series: dict[str, SerieComparada] = {}
    for variavel in variaveis:
        try:
            serie_original = original.serie(variavel.original)
            serie_simplificada = simplificado.serie(variavel.simplificado)
        except KeyError as erro:
            raise ErroDeMapeamento(
                f"variaveis: não foi possível mapear '{variavel.nome}'. {erro.args[0]}"
            ) from erro
        series[variavel.nome] = SerieComparada(
            nome=variavel.nome,
            tempo=original.tempo,
            original=serie_original,
            simplificado=serie_simplificada,
        )
    return series
