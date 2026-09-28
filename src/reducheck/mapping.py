"""Match variables between the original and the simplified model.

A declared variable names one *linear combination* on each side -- one term for the 1:1
case, several for a lumping such as ``M = Mo + M1 + M2``, with weights when the terms do not
enter equally. :func:`reducheck.config.normalizar_alvo` has already reduced the three YAML
spellings to ``name -> weight``, so this module only ever adds up weighted columns.

A variable the reduction dropped (``simplificado: null``) is skipped: there is no series to
compare it against. It stays in the configuration because it documents the reduction, and
because the validation uses it to refuse ``core: true`` on something that no longer exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from reducheck.config import Variavel, normalizar_alvo
from reducheck.simulation import Trajetorias

__all__ = ["ErroDeMapeamento", "SerieComparada", "combinar", "mapear", "nomes_simulados"]


class ErroDeMapeamento(Exception):
    """As variáveis declaradas não puderam ser casadas com as séries simuladas."""


@dataclass(frozen=True)
class SerieComparada:
    """The two series a metric compares, already on the same time grid."""

    #: Name used in the report.
    nome: str
    tempo: np.ndarray
    #: Series of the original model, after combining its variables.
    original: np.ndarray
    #: Series of the corresponding variable(s) of the simplified model.
    simplificado: np.ndarray
    #: Which variables of each model went into the two series, and with which weight. Kept
    #: so the report can state what was summed instead of only the name it was summed into.
    pesos_original: Mapping[str, float] = field(default_factory=dict)
    pesos_simplificado: Mapping[str, float] = field(default_factory=dict)


def nomes_simulados(variaveis: Sequence[Variavel], papel: str) -> list[str]:
    """Return every variable of one model the mapping reads, without repetitions.

    Two declared variables may read the same model variable, and a sum reads several at
    once; the simulation asks for each name once, in the order they were declared.
    """
    nomes = (
        nome
        for variavel in variaveis
        for nome in normalizar_alvo(getattr(variavel, papel) or {})
    )
    return list(dict.fromkeys(nomes))


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
        if variavel.simplificado is None:
            continue
        pesos_original = normalizar_alvo(variavel.original)
        pesos_simplificado = normalizar_alvo(variavel.simplificado)
        series[variavel.nome] = SerieComparada(
            nome=variavel.nome,
            tempo=original.tempo,
            original=combinar(original, pesos_original, variavel.nome, "original"),
            simplificado=combinar(
                simplificado, pesos_simplificado, variavel.nome, "simplificado"
            ),
            pesos_original=pesos_original,
            pesos_simplificado=pesos_simplificado,
        )
    return series


def combinar(
    trajetorias: Trajetorias, pesos: Mapping[str, float], nome: str, papel: str
) -> np.ndarray:
    """Return the weighted sum of the columns named in ``pesos``.

    Public because the reference numerical noise (:func:`reducheck.simulation.ruido_numerico`)
    measures itself on the same combinations the report compares, not on the raw columns of
    the model: a limit is written against ``M = Mo + M1 + M2``, so the floor it is compared
    to has to be measured on ``M`` too.
    """
    total = np.zeros_like(trajetorias.tempo, dtype=float)
    for variavel, peso in pesos.items():
        try:
            total = total + peso * trajetorias.serie(variavel)
        except KeyError as erro:
            raise ErroDeMapeamento(
                f"variaveis: não foi possível mapear '{nome}' no modelo {papel}. "
                f"{erro.args[0]}"
            ) from erro
    return total
