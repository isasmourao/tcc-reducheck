"""Evaluate the declared criteria and decide the final verdict.

One item per (criterion, variable) pair, as described in ``docs/produto.md``. This version
uses the two-level rule -- approved only if every item passed. The three-level rule, with
mandatory and desirable criteria, is a later task and will change :func:`avaliar` alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from reducheck import metrics
from reducheck.config import Criterio
from reducheck.mapping import SerieComparada

__all__ = ["ItemAvaliado", "Veredito", "avaliar"]


@dataclass(frozen=True)
class ItemAvaliado:
    """One (criterion, variable) pair, with the measured value against its threshold."""

    metrica: str
    variavel: str
    valor: float
    limite: float
    passou: bool


@dataclass(frozen=True)
class Veredito:
    """The decision, plus every item that supports it."""

    aprovado: bool
    criterios: tuple[ItemAvaliado, ...]

    @property
    def porcentagem(self) -> float:
        """Percentage of items that passed."""
        if not self.criterios:
            return 0.0
        passaram = sum(1 for item in self.criterios if item.passou)
        return 100.0 * passaram / len(self.criterios)


def avaliar(
    criterios: Sequence[Criterio],
    series: Mapping[str, SerieComparada],
    core: Sequence[str] = (),
) -> Veredito:
    """Apply every criterion to its variables and decide whether the model is approved.

    A value exactly on the threshold passes: the threshold is the largest accepted error.
    ``core`` is the list a criterion written as ``variaveis: core`` expands to; expanding it
    here, and not when the file is read, is what keeps the configuration a faithful record
    of what the user wrote.
    """
    itens: list[ItemAvaliado] = []
    for criterio in criterios:
        metrica = metrics.obter(criterio.metrica)
        nomes = list(core) if criterio.variaveis == "core" else list(criterio.variaveis or [])
        for nome in nomes:
            try:
                serie = series[nome]
            except KeyError as erro:
                raise KeyError(
                    f"O critério '{criterio.metrica}' cita a variável '{nome}', "
                    "que não foi mapeada."
                ) from erro
            valor = metrica(serie.original, serie.simplificado)
            itens.append(
                ItemAvaliado(
                    metrica=criterio.metrica,
                    variavel=nome,
                    valor=valor,
                    limite=criterio.limite,
                    passou=valor <= criterio.limite,
                )
            )
    return Veredito(aprovado=all(item.passou for item in itens), criterios=tuple(itens))
