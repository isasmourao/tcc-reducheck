"""Evaluate the declared criteria and decide the final verdict.

One item per (criterion, variable) pair, and the three-level rule of the "Output" section of
``docs/produto.md``: a mandatory criterion that fails rejects the model whatever the
percentage says, which is the reason mandatory criteria exist at all.

The number of levels is still an open decision with the advisor (D01, issue #1), so
``relatorio.niveis: 2`` collapses "com ressalvas" into ``APROVADO`` without changing any
measurement: what the option switches off is the level, not the item that failed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from reducheck import metrics
from reducheck.config import Criterio
from reducheck.mapping import SerieComparada

__all__ = [
    "APROVADO",
    "COM_RESSALVAS",
    "NIVEIS",
    "REPROVADO",
    "Contagem",
    "ItemAvaliado",
    "Veredito",
    "avaliar",
]

#: The three levels, spelled as they are printed in the report.
APROVADO = "APROVADO"
COM_RESSALVAS = "APROVADO COM RESSALVAS"
REPROVADO = "REPROVADO"

#: How many levels the verdict may have, pending D01.
NIVEIS = frozenset({2, 3})


class Contagem(NamedTuple):
    """How many items of one kind passed, out of how many there were."""

    passados: int
    total: int


@dataclass(frozen=True)
class ItemAvaliado:
    """One (criterion, variable) pair, with the measured value against its threshold."""

    metrica: str
    variavel: str
    valor: float
    limite: float
    passou: bool
    #: Whether the criterion this item came from is mandatory. A mandatory item that fails
    #: rejects the model on its own; a desirable one only adds a reservation.
    obrigatorio: bool = True
    #: What the metric says the number means; printed next to the value in the report.
    descricao: str = ""
    #: What the metric had to warn about, such as points excluded near zero. A warning
    #: never changes whether the item passed: it is there so the reader can judge the
    #: number, as ``docs/produto.md`` asks ("avisa, sem parar").
    avisos: tuple[str, ...] = ()
    #: Extra numbers the metric produced (when the maximum happened, points dropped).
    detalhes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Veredito:
    """The decision, plus every item that supports it."""

    #: One of :data:`APROVADO`, :data:`COM_RESSALVAS` or :data:`REPROVADO`.
    nivel: str
    criterios: tuple[ItemAvaliado, ...]

    @property
    def aprovado(self) -> bool:
        """Whether the verdict is the plain approval, with no reservation.

        Deliberately strict: "com ressalvas" is a level of its own, which the command line
        of issue #15 reports with its own exit code. With ``relatorio.niveis: 2`` there is
        no intermediate level, so a run that would be approved with reservations arrives
        here already as :data:`APROVADO` and this is ``True``.
        """
        return self.nivel == APROVADO

    @property
    def avisos(self) -> tuple[str, ...]:
        """Every warning the metrics produced, each one saying which variable it is about.

        Gathered here so the report has one place to print them, instead of the reader
        having to look for them item by item.
        """
        return tuple(
            f"{item.variavel}: {aviso}" for item in self.criterios for aviso in item.avisos
        )

    @property
    def porcentagem(self) -> float:
        """Percentage of items that passed."""
        if not self.criterios:
            return 0.0
        passaram = sum(1 for item in self.criterios if item.passou)
        return 100.0 * passaram / len(self.criterios)

    @property
    def obrigatorios(self) -> Contagem:
        """How many mandatory items passed, out of how many there were."""
        return self._contar(obrigatorio=True)

    @property
    def desejaveis(self) -> Contagem:
        """How many desirable items passed, out of how many there were."""
        return self._contar(obrigatorio=False)

    def _contar(self, obrigatorio: bool) -> Contagem:
        do_tipo = [item for item in self.criterios if item.obrigatorio is obrigatorio]
        return Contagem(sum(1 for item in do_tipo if item.passou), len(do_tipo))


def avaliar(
    criterios: Sequence[Criterio],
    series: Mapping[str, SerieComparada],
    core: Sequence[str] = (),
    niveis: int = 3,
) -> Veredito:
    """Apply every criterion to its variables and decide the verdict.

    A value exactly on the threshold passes: the threshold is the largest accepted error.
    ``core`` is the list a criterion written as ``variaveis: core`` expands to; expanding it
    here, and not when the file is read, is what keeps the configuration a faithful record
    of what the user wrote. ``niveis`` comes from ``relatorio.niveis``.
    """
    if niveis not in NIVEIS:
        raise ValueError(f"niveis tem que ser 2 ou 3; recebido {niveis}.")
    itens: list[ItemAvaliado] = []
    for criterio in criterios:
        nomes = list(core) if criterio.variaveis == "core" else list(criterio.variaveis or [])
        for nome in nomes:
            try:
                serie = series[nome]
            except KeyError as erro:
                raise KeyError(
                    f"O critério '{criterio.metrica}' cita a variável '{nome}', "
                    "que não foi mapeada."
                ) from erro
            resultado = metrics.calcular(
                criterio.metrica,
                serie.tempo,
                serie.original,
                serie.simplificado,
                criterio.parametros,
            )
            itens.append(
                ItemAvaliado(
                    metrica=criterio.metrica,
                    variavel=nome,
                    valor=resultado.valor,
                    limite=criterio.limite,
                    passou=resultado.valor <= criterio.limite,
                    obrigatorio=criterio.obrigatorio,
                    descricao=resultado.descricao,
                    avisos=tuple(resultado.avisos),
                    detalhes=dict(resultado.detalhes),
                )
            )
    return Veredito(nivel=_decidir(itens, niveis), criterios=tuple(itens))


def _decidir(itens: Sequence[ItemAvaliado], niveis: int) -> str:
    """Return the level the items imply, by the rule of ``docs/produto.md``.

    The order matters: a mandatory failure is looked at first, so a high percentage never
    rescues it.
    """
    if any(not item.passou and item.obrigatorio for item in itens):
        return REPROVADO
    if any(not item.passou for item in itens):
        return COM_RESSALVAS if niveis == 3 else APROVADO
    return APROVADO
