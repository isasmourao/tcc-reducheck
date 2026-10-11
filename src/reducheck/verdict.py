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

import numpy as np

from reducheck import metrics, qualitative
from reducheck.config import ANALISES_QUALITATIVAS, Criterio
from reducheck.mapping import SerieComparada

__all__ = [
    "APROVADO",
    "COM_RESSALVAS",
    "NIVEIS",
    "REPROVADO",
    "SEM_VARIAVEL",
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

#: Printed in the "Variável" column of an item that is about the whole model, and not about
#: one variable: ``estabilidade_local`` is one item, whatever the number of variables.
SEM_VARIAVEL = "—"


class Contagem(NamedTuple):
    """How many items of one kind passed, out of how many there were."""

    passados: int
    total: int


@dataclass(frozen=True)
class ItemAvaliado:
    """One (criterion, variable) pair, with the measured value against its threshold."""

    metrica: str
    variavel: str
    #: The measured number, or ``None`` for an item that is not a number -- the
    #: ``estabilidade_local`` criterion compares two labels, not two values.
    valor: float | None
    #: The threshold, or ``None`` when the criterion has none.
    limite: float | None
    passou: bool
    #: Whether the criterion this item came from is mandatory. A mandatory item that fails
    #: rejects the model on its own; a desirable one only adds a reservation.
    obrigatorio: bool = True
    #: What the metric says the number means; printed next to the value in the report.
    descricao: str = ""
    #: What the report prints in the "Valor" column when there is no number to print, such
    #: as ``"marginal / marginal"`` for the comparison of two stability classifications.
    valor_texto: str = ""
    #: The same, for the "Limite" column: a qualitative criterion is met when the two
    #: labels are equal, and ``"igual"`` is what that reads as in the table.
    limite_texto: str = ""
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
    comparacao: qualitative.Comparacao | None = None,
) -> Veredito:
    """Apply every criterion to its variables and decide the verdict.

    A value exactly on the threshold passes: the threshold is the largest accepted error.
    ``core`` is the list a criterion written as ``variaveis: core`` expands to; expanding it
    here, and not when the file is read, is what keeps the configuration a faithful record
    of what the user wrote. ``niveis`` comes from ``relatorio.niveis``.

    ``comparacao`` is the qualitative analysis of both models, required when and only when
    some criterion is one of :data:`~reducheck.config.ANALISES_QUALITATIVAS`. A qualitative
    item counts in the percentage like any other, which is the sense in which it is "a
    criterion like the others"; what it is not is a pluggable metric (question 41 of
    ``docs/questoes-em-aberto.md``).
    """
    if niveis not in NIVEIS:
        raise ValueError(f"niveis tem que ser 2 ou 3; recebido {niveis}.")
    itens: list[ItemAvaliado] = []
    for criterio in criterios:
        nomes = list(core) if criterio.variaveis == "core" else list(criterio.variaveis or [])
        if criterio.metrica in ANALISES_QUALITATIVAS:
            if comparacao is None:
                raise ValueError(
                    f"O critério '{criterio.metrica}' precisa da análise qualitativa dos "
                    "dois modelos, que não foi informada."
                )
            itens.extend(_itens_qualitativos(criterio, nomes, series, comparacao))
            continue
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


# --- qualitative criteria (capability L3) ------------------------------------


def _itens_qualitativos(
    criterio: Criterio,
    nomes: Sequence[str],
    series: Mapping[str, SerieComparada],
    comparacao: qualitative.Comparacao,
) -> list[ItemAvaliado]:
    if criterio.metrica == "estabilidade_local":
        return [_item_de_estabilidade(criterio, comparacao)]
    return [_item_de_equilibrio(criterio, nome, series, comparacao) for nome in nomes]


def _item_de_estabilidade(
    criterio: Criterio, comparacao: qualitative.Comparacao
) -> ItemAvaliado:
    """Compare the two classifications, which is the only comparison that makes sense.

    The two models have different dimensions, so their eigenvalue vectors cannot be put
    side by side; what can is the label each spectrum earns. The eigenvalues themselves go
    into the details, so the report can print them and the reader can judge the label.
    """
    original = comparacao.original.estabilidade
    simplificado = comparacao.simplificado.estabilidade
    passou = original.classificacao == simplificado.classificacao
    coincidem = "coincidem" if passou else "são diferentes"
    return ItemAvaliado(
        metrica=criterio.metrica,
        variavel=SEM_VARIAVEL,
        valor=None,
        limite=None,
        valor_texto=f"{original.classificacao} / {simplificado.classificacao}",
        limite_texto="igual",
        passou=passou,
        obrigatorio=criterio.obrigatorio,
        descricao=(
            f"a classificação do original ({original.classificacao}) e a do simplificado "
            f"({simplificado.classificacao}) {coincidem}"
        ),
        detalhes={
            "classificacao_original": original.classificacao,
            "classificacao_simplificado": simplificado.classificacao,
            "autovalores_dominantes_original": _autovalores(original),
            "autovalores_dominantes_simplificado": _autovalores(simplificado),
            "metodo_original": original.metodo,
            "metodo_simplificado": simplificado.metodo,
            "tolerancia": original.tolerancia,
            "limiar_original": original.limiar,
            "limiar_simplificado": simplificado.limiar,
        },
    )


def _autovalores(estabilidade: qualitative.Estabilidade) -> list[list[float]]:
    """Return the dominant eigenvalues as ``[real, imaginary]`` pairs, for the JSON."""
    return [[valor.real, valor.imag] for valor in estabilidade.dominantes()]


def _item_de_equilibrio(
    criterio: Criterio,
    nome: str,
    series: Mapping[str, SerieComparada],
    comparacao: qualitative.Comparacao,
) -> ItemAvaliado:
    """Compare one mapped variable at the equilibrium of each model, relatively.

    The denominator is the equilibrium value of the original, with a floor of
    ``EPSILON_RELATIVO`` times the largest value that variable reaches in the simulated
    trajectory. The floor is what keeps a variable that decays to zero from reporting a
    meaningless relative error: in the Verly model ``C2`` settles at 4e-11 against a peak of
    8e-2, so dividing by 4e-11 would turn two numbers that are both zero, as far as the
    variable's own scale goes, into a percentage. When the floor is used the item says so.
    """
    serie = _serie(criterio, nome, series)
    original = _combinar(
        comparacao.original.equilibrio.ponto, serie.pesos_original, nome, "original"
    )
    simplificado = _combinar(
        comparacao.simplificado.equilibrio.ponto,
        serie.pesos_simplificado,
        nome,
        "simplificado",
    )
    diferenca = abs(simplificado - original)
    escala = float(np.max(np.abs(serie.original))) if serie.original.size else 0.0
    piso = metrics.EPSILON_RELATIVO * escala
    denominador = max(abs(original), piso)

    avisos: tuple[str, ...] = ()
    if denominador <= 0.0:
        # The variable is identically zero in the whole trajectory and at the equilibrium:
        # there is nothing to normalise by, and nothing to disagree about either.
        valor = 0.0 if diferenca == 0.0 else float("inf")
    else:
        valor = diferenca / denominador
        if abs(original) < piso:
            avisos = (
                f"o equilíbrio do original ({original:.3g}) está abaixo de "
                f"{metrics.EPSILON_RELATIVO:g}× o máximo da trajetória ({escala:.3g}); o "
                f"erro foi normalizado por esse piso ({piso:.3g}), e não pelo valor, que "
                "nessa escala é indistinguível de zero",
            )
    return ItemAvaliado(
        metrica=criterio.metrica,
        variavel=nome,
        valor=valor,
        limite=criterio.limite,
        passou=criterio.limite is not None and valor <= criterio.limite,
        obrigatorio=criterio.obrigatorio,
        descricao="o erro relativo entre os dois equilíbrios (fração: 0,05 = 5%)",
        avisos=avisos,
        detalhes={
            "equilibrio_original": original,
            "equilibrio_simplificado": simplificado,
            "diferenca": diferenca,
            "denominador": denominador,
            "piso": piso,
        },
    )


def _serie(
    criterio: Criterio, nome: str, series: Mapping[str, SerieComparada]
) -> SerieComparada:
    try:
        return series[nome]
    except KeyError as erro:
        raise KeyError(
            f"O critério '{criterio.metrica}' cita a variável '{nome}', que não foi mapeada."
        ) from erro


def _combinar(
    ponto: Mapping[str, float], pesos: Mapping[str, float], nome: str, papel: str
) -> float:
    """Apply the declared linear combination to the equilibrium point of one model."""
    total = 0.0
    for variavel, peso in pesos.items():
        try:
            total += peso * ponto[variavel]
        except KeyError as erro:
            raise KeyError(
                f"O critério 'equilibrio' em '{nome}' precisa de '{variavel}' no "
                f"equilíbrio do modelo {papel}, que não está entre as variáveis de estado."
            ) from erro
    return total


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
