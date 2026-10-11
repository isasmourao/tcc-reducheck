"""Equilibrium point and local stability analysis of each model.

This is the long-term half of the comparison: the metrics ask whether the two models walk
the same path, and this module asks whether they arrive at the same place and whether that
place holds. Two analyses, both per model (capabilities L1 and L2), compared by
:mod:`reducheck.verdict` (L3).

**One equilibrium, not all of them.** :func:`encontrar_equilibrio` returns the equilibrium
the system reaches from the initial conditions of the configuration. Finding every
equilibrium of a nonlinear system is out of scope (``docs/produto.md``), so every report
carries :data:`AVISO_DO_EQUILIBRIO_UNICO` next to the numbers.

**Why the fallback is the main path.** The plan was libRoadRunner's ``steadyState``, with
integration as a plan B. In the case-study model it is the other way round: Verly et al.
write the eleven state variables as parameters with a *rate rule* and no floating species
at all, and both ``steadyState`` and ``getFullJacobian`` only know about floating species.
``steadyState`` then returns a residual of 1e-18 -- "converged" -- without having solved
anything, with the rates still at 2500, and ``getFullJacobian`` refuses outright
(*fewer floating species (0) than rate rules (11)*). So:

* convergence is judged by this module, from the rates of change at the point, and never
  by the solver's own claim (:attr:`Equilibrio.residuo`);
* the Jacobian falls back to central finite differences;
* when ``steadyState`` does not produce a point, the model is integrated over growing
  horizons until it stops moving, and only then refined with :func:`scipy.optimize.root`.

**Beyond the declared horizon.** The equilibrium may lie far outside the simulated window:
in the Verly model it arrives at t ~ 1e9 days, 1.4 million times the 720 days of the
configuration. The decision of 11/10 (question 39 of ``docs/questoes-em-aberto.md``) is to
measure it anyway and to say so: :attr:`Equilibrio.instante` and
:meth:`Equilibrio.vezes_o_horizonte` exist so the report can state in which instant the
point was reached, instead of letting a criterion about t = 1e9 pass for a statement about
the window the user asked about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import roadrunner
from scipy.optimize import root

from reducheck.config import Simulacao, Valores
from reducheck.simulation import ErroDeSimulacao, preparar

__all__ = [
    "AVISO_DO_EQUILIBRIO_UNICO",
    "ESTAVEL",
    "EXTENSOES_MAXIMAS",
    "FATOR_DO_HORIZONTE",
    "INSTAVEL",
    "MARGINAL",
    "TOLERANCIA_DO_EQUILIBRIO",
    "TOLERANCIA_MARGINAL",
    "Analise",
    "Comparacao",
    "Equilibrio",
    "ErroDeQualitativo",
    "Estabilidade",
    "analisar",
    "avisos",
    "classificar",
    "encontrar_equilibrio",
    "estabilidade_local",
    "estado",
    "jacobiana",
    "preparar_modelo",
    "taxas",
    "valores",
]

#: The three classifications. Portuguese, because they are printed in the report.
ESTAVEL = "estável"
INSTAVEL = "instável"
MARGINAL = "marginal"

#: How much slower than its own initial pace the system has to be moving for the point to
#: count as an equilibrium. Dimensionless on purpose: see :attr:`Equilibrio.residuo`.
TOLERANCIA_DO_EQUILIBRIO = 1e-6

#: How close to zero the real part of an eigenvalue has to be for the equilibrium to be
#: called marginal, as a fraction of the largest real part in absolute value of the same
#: model. Relative to the spectrum, and not an absolute number, so that the label does not
#: depend on the time unit of the model: the same system written in days and in seconds has
#: eigenvalues 86400 times apart and must be classified the same way (decision of 11/10,
#: question 40 of ``docs/questoes-em-aberto.md``).
TOLERANCIA_MARGINAL = 1e-6

#: Factor by which the horizon grows at each attempt of the integration fallback.
FATOR_DO_HORIZONTE = 10.0

#: How many times the horizon may grow before the analysis gives up. ``t_fim`` times
#: :data:`FATOR_DO_HORIZONTE` to this power is the furthest the model is integrated; the
#: cap is arbitrary and is itself an open question (39 of ``docs/questoes-em-aberto.md``).
EXTENSOES_MAXIMAS = 12

#: Relative step of the central finite differences of the Jacobian.
PASSO_RELATIVO = 1e-7

#: Printed in every report that contains a qualitative analysis, as issue #18 requires.
AVISO_DO_EQUILIBRIO_UNICO = (
    "Análise de um único equilíbrio, alcançado a partir das condições iniciais da "
    "configuração; outros equilíbrios não foram buscados."
)


class ErroDeQualitativo(Exception):
    """Não foi possível achar o equilíbrio ou classificar a estabilidade do modelo."""


@dataclass(frozen=True)
class Equilibrio:
    """The equilibrium point of one model, and how it was obtained."""

    #: Every state variable of the model at the point, in the model's own order.
    ponto: Mapping[str, float]
    #: In words, what produced the point: which solver, up to which instant.
    metodo: str
    #: ``max|dx/dt|`` at the point, divided by the same quantity at the initial condition.
    #: Dimensionless and scale-free, which an absolute norm is not: it reads as "the system
    #: is moving this many times slower than it was when the simulation started". A norm in
    #: the unit of the model would need a different threshold per model -- in the Verly
    #: model the initial pace is 2500 and in the toy pairs it is 0.6.
    residuo: float
    #: ``max|dx/dt|`` at the point, in the unit of the model, for whoever wants the raw
    #: number.
    residuo_absoluto: float
    #: ``max|dx/dt|`` at the initial condition: the pace :attr:`residuo` is relative to.
    escala_de_taxa: float
    #: Up to which instant the model had to be integrated, or ``None`` when the point came
    #: from the algebraic steady-state solver and no horizon was involved.
    instante: float | None
    #: Threshold :attr:`residuo` was compared against.
    tolerancia: float
    #: Whether the point is an equilibrium by this module's own measurement.
    convergiu: bool

    def vezes_o_horizonte(self, t_fim: float) -> float | None:
        """How many times the simulated horizon the equilibrium instant is.

        ``None`` when there is no instant to compare. This is the number that keeps a
        criterion about t = 1e9 from being read as a statement about t = 720.
        """
        if self.instante is None or t_fim <= 0:
            return None
        return self.instante / t_fim


@dataclass(frozen=True)
class Estabilidade:
    """The local stability of one model at one point: eigenvalues and classification."""

    #: Eigenvalues of the Jacobian, sorted by decreasing real part, so the first one is
    #: the dominant mode.
    autovalores: tuple[complex, ...]
    #: :data:`ESTAVEL`, :data:`INSTAVEL` or :data:`MARGINAL`.
    classificacao: str
    #: How the Jacobian was obtained: libRoadRunner or finite differences.
    metodo: str
    #: Relative tolerance used for "real part ~ 0".
    tolerancia: float
    #: The absolute threshold that tolerance became for this spectrum.
    limiar: float

    def dominantes(self, quantos: int = 3) -> tuple[complex, ...]:
        """Return the ``quantos`` eigenvalues of largest real part, the report's summary."""
        return self.autovalores[:quantos]


@dataclass(frozen=True)
class Analise:
    """What the qualitative analysis of one model produced."""

    #: ``original`` or ``simplificado``, for the messages.
    papel: str
    equilibrio: Equilibrio
    estabilidade: Estabilidade


@dataclass(frozen=True)
class Comparacao:
    """The analysis of both models, which is what a qualitative criterion is applied to.

    Deliberately not a comparison of the two spectra: the models have different dimensions,
    so there is no pairing between their eigenvalues. What is compared is the
    *classification* (one label per model) and the mapped variables at the equilibrium --
    both in :mod:`reducheck.verdict`, which is where criteria are decided.
    """

    original: Analise
    simplificado: Analise


def preparar_modelo(
    caminho_sbml: Path | str, condicoes: Simulacao, sobrescrever: Valores | None = None
) -> roadrunner.RoadRunner:
    """Load the model under the conditions of the configuration, ready to be questioned.

    A thin alias of :func:`reducheck.simulation.preparar`, kept so that this module reads
    as a unit and so that the qualitative analysis cannot accidentally be run under
    conditions other than the ones the metrics saw.
    """
    return preparar(caminho_sbml, condicoes, (), sobrescrever)


def estado(modelo: roadrunner.RoadRunner) -> tuple[str, ...]:
    """Return the names of the state variables, in the model's own order.

    Read from the names of the rates of change, which is the only listing that covers both
    ways a state variable can be written in SBML: a floating species (the toy models) and a
    parameter with a rate rule (every variable of the Verly model). Asking for floating
    species alone would report an empty state for the case-study model.
    """
    taxas_nomeadas = modelo.getRatesOfChangeNamedArray()
    nomes = tuple(str(nome).removesuffix("'") for nome in taxas_nomeadas.colnames)
    if not nomes:
        raise ErroDeQualitativo(
            "O modelo não tem nenhuma variável de estado (nem espécie flutuante, nem "
            "parâmetro com regra de taxa), então não há equilíbrio a procurar."
        )
    return nomes


def taxas(modelo: roadrunner.RoadRunner) -> np.ndarray:
    """Return ``dx/dt`` at the current state, in the order of :func:`estado`."""
    return np.asarray(modelo.getRatesOfChange(), dtype=float).ravel()


def valores(modelo: roadrunner.RoadRunner, nomes: Sequence[str]) -> np.ndarray:
    """Return the current value of each name, in the given order."""
    return np.array([float(modelo[nome]) for nome in nomes], dtype=float)


def _atribuir(
    modelo: roadrunner.RoadRunner, nomes: Sequence[str], ponto: np.ndarray
) -> None:
    for nome, valor in zip(nomes, ponto, strict=True):
        modelo[nome] = float(valor)


def _norma(modelo: roadrunner.RoadRunner) -> float:
    return float(np.max(np.abs(taxas(modelo))))


# --- equilibrium (L1) --------------------------------------------------------


def encontrar_equilibrio(
    modelo: roadrunner.RoadRunner,
    condicoes: Simulacao,
    tolerancia: float = TOLERANCIA_DO_EQUILIBRIO,
    extensoes: int = EXTENSOES_MAXIMAS,
) -> Equilibrio:
    """Return the equilibrium the model reaches from the initial conditions.

    Three attempts, in this order, and the first one whose residual passes wins:

    1. libRoadRunner's ``steadyState``, whose *own* claim of convergence is ignored: what
       decides is ``max|dx/dt|`` measured at the point it returned;
    2. integration from the initial condition over horizons growing by
       :data:`FATOR_DO_HORIZONTE`, starting at ``t_fim``, until the system stops moving;
    3. refinement of that point with :func:`scipy.optimize.root`, in variables scaled by
       their own magnitude -- without the scaling the solver does not move at all on a
       state vector that spans from 1e-2 to 1e6, as the Verly model does.

    The refinement is only accepted when it actually lowers the residual. In the case-study
    model it does not converge (the condition number of the Jacobian is around 3e11), and a
    point taken from a solver that reports failure would be worse than the integrated one.
    """
    nomes = estado(modelo)
    modelo.reset()
    inicial = valores(modelo, nomes)
    escala = _norma(modelo)
    if not np.isfinite(escala) or escala <= 0.0:
        # Already at rest at t0: there is no initial pace to be relative to, so the
        # residual falls back to the absolute norm.
        escala = 1.0

    def resultado(
        metodo: str, instante: float | None, convergiu: bool = True
    ) -> Equilibrio:
        absoluto = _norma(modelo)
        return Equilibrio(
            ponto=dict(zip(nomes, valores(modelo, nomes), strict=True)),
            metodo=metodo,
            residuo=absoluto / escala,
            residuo_absoluto=absoluto,
            escala_de_taxa=escala,
            instante=instante,
            tolerancia=tolerancia,
            convergiu=convergiu,
        )

    tentativas: list[str] = []
    try:
        modelo.steadyState()
    except RuntimeError as erro:
        tentativas.append(f"o steadyState do libRoadRunner falhou ({_uma_linha(erro)})")
    else:
        if _norma(modelo) / escala <= tolerancia:
            return resultado("steadyState do libRoadRunner", None)
        tentativas.append(
            f"o steadyState do libRoadRunner devolveu um ponto com resíduo relativo "
            f"{_norma(modelo) / escala:.3g}, acima da tolerância {tolerancia:g}"
        )

    instante = float(condicoes.t_fim)
    for _ in range(extensoes + 1):
        modelo.reset()
        _atribuir(modelo, nomes, inicial)
        try:
            modelo.simulate(condicoes.t_inicio, instante, 2)
        except RuntimeError as erro:
            tentativas.append(
                f"a integração até t = {instante:g} falhou ({_uma_linha(erro)})"
            )
            break
        if not np.all(np.isfinite(valores(modelo, nomes))):
            tentativas.append(
                f"a integração até t = {instante:g} produziu valor não finito"
            )
            break
        if _norma(modelo) / escala <= tolerancia:
            metodo = f"integração até t = {instante:g}"
            refinado, melhorou = _refinar(modelo, nomes)
            if melhorou:
                _atribuir(modelo, nomes, refinado)
                metodo += ", refinada com scipy.optimize.root"
            return resultado(metodo, instante)
        instante *= FATOR_DO_HORIZONTE

    raise ErroDeQualitativo(
        f"Não foi possível achar um ponto de equilíbrio do modelo: "
        f"{'; '.join(tentativas)}. O resíduo relativo chegou a "
        f"{_norma(modelo) / escala:.3g}, acima da tolerância {tolerancia:g}, integrando "
        f"até {instante / FATOR_DO_HORIZONTE:g} ({extensoes + 1} horizontes a partir de "
        f"t_fim = {condicoes.t_fim:g}). Se o modelo não tem equilíbrio neste horizonte, "
        "tire o critério qualitativo da configuração em vez de afrouxar a tolerância."
    )


def _refinar(
    modelo: roadrunner.RoadRunner, nomes: Sequence[str]
) -> tuple[np.ndarray, bool]:
    """Polish the point with Newton, in scaled variables, and say whether it got better."""
    ponto = valores(modelo, nomes)
    escalas = np.maximum(np.abs(ponto), 1e-12)

    def residuo(escalado: np.ndarray) -> np.ndarray:
        _atribuir(modelo, nomes, escalado * escalas)
        return taxas(modelo) / escalas

    antes = float(np.max(np.abs(residuo(ponto / escalas))))
    try:
        solucao = root(residuo, ponto / escalas, method="hybr")
    except (ArithmeticError, ValueError, RuntimeError):
        _atribuir(modelo, nomes, ponto)
        return ponto, False
    depois = float(np.max(np.abs(residuo(solucao.x))))
    _atribuir(modelo, nomes, ponto)
    if solucao.success and np.all(np.isfinite(solucao.x)) and depois < antes:
        return solucao.x * escalas, True
    return ponto, False


# --- local stability (L2) ----------------------------------------------------


def jacobiana(
    modelo: roadrunner.RoadRunner, ponto: Mapping[str, float] | None = None
) -> tuple[np.ndarray, str]:
    """Return the full Jacobian at ``ponto`` and how it was obtained.

    libRoadRunner's ``getFullJacobian`` is preferred, and is only usable when the state is
    made of floating species: it raises for a model written with rate rules, which is the
    case of the Verly model. Central finite differences then do the work, with a step
    relative to each variable, because the state spans many orders of magnitude.
    """
    nomes = estado(modelo)
    if ponto is not None:
        _atribuir(modelo, nomes, np.array([ponto[nome] for nome in nomes]))
    try:
        bruta = modelo.getFullJacobian()
    except RuntimeError:
        return _por_diferencas_finitas(modelo, nomes), "diferenças finitas (central)"

    linhas = tuple(str(nome) for nome in bruta.rownames)
    matriz = np.asarray(bruta, dtype=float)
    if linhas == nomes:
        return matriz, "libRoadRunner (getFullJacobian)"
    if sorted(linhas) == sorted(nomes):
        # Same variables in another order: permute instead of recomputing, so the matrix
        # stays the one libRoadRunner derived symbolically.
        ordem = [linhas.index(nome) for nome in nomes]
        return matriz[np.ix_(ordem, ordem)], "libRoadRunner (getFullJacobian, reordenada)"
    return _por_diferencas_finitas(modelo, nomes), "diferenças finitas (central)"


def _por_diferencas_finitas(
    modelo: roadrunner.RoadRunner, nomes: Sequence[str]
) -> np.ndarray:
    ponto = valores(modelo, nomes)
    tamanho = len(nomes)
    matriz = np.zeros((tamanho, tamanho), dtype=float)
    for coluna in range(tamanho):
        passo = PASSO_RELATIVO * max(abs(float(ponto[coluna])), 1.0)
        adiante, atras = ponto.copy(), ponto.copy()
        adiante[coluna] += passo
        atras[coluna] -= passo
        _atribuir(modelo, nomes, adiante)
        taxas_adiante = taxas(modelo)
        _atribuir(modelo, nomes, atras)
        matriz[:, coluna] = (taxas_adiante - taxas(modelo)) / (2.0 * passo)
    _atribuir(modelo, nomes, ponto)
    if not np.all(np.isfinite(matriz)):
        raise ErroDeQualitativo(
            "A Jacobiana por diferenças finitas tem valor não finito no equilíbrio; "
            "não é possível classificar a estabilidade local."
        )
    return matriz


def classificar(
    autovalores: np.ndarray,
    tolerancia: float = TOLERANCIA_MARGINAL,
    metodo: str = "",
) -> Estabilidade:
    """Classify a spectrum as stable, unstable or marginal.

    The threshold is ``tolerancia`` times the largest real part in absolute value of this
    same spectrum, so it carries the time scale of the model with it. Order matters:
    instability is looked at first, because one growing mode decides the point whatever the
    others do; marginality second, because a real part indistinguishable from zero means
    the linearisation does not answer the question.
    """
    espectro = np.atleast_1d(np.asarray(autovalores))
    if espectro.size == 0:
        raise ErroDeQualitativo("A Jacobiana não tem autovalores a classificar.")
    ordenados = tuple(complex(valor) for valor in espectro[np.argsort(-espectro.real)])
    reais = np.array([valor.real for valor in ordenados])
    limiar = float(tolerancia * np.max(np.abs(reais)))

    if np.any(reais > limiar):
        classificacao = INSTAVEL
    elif np.any(np.abs(reais) <= limiar):
        classificacao = MARGINAL
    else:
        classificacao = ESTAVEL
    return Estabilidade(
        autovalores=ordenados,
        classificacao=classificacao,
        metodo=metodo,
        tolerancia=tolerancia,
        limiar=limiar,
    )


def estabilidade_local(
    modelo: roadrunner.RoadRunner,
    ponto: Mapping[str, float] | None = None,
    tolerancia: float = TOLERANCIA_MARGINAL,
) -> Estabilidade:
    """Return the local stability of ``modelo`` at ``ponto``, by the eigenvalues there."""
    matriz, metodo = jacobiana(modelo, ponto)
    try:
        autovalores = np.linalg.eigvals(matriz)
    except np.linalg.LinAlgError as erro:
        raise ErroDeQualitativo(
            f"Não foi possível calcular os autovalores da Jacobiana no equilíbrio: {erro}"
        ) from erro
    return classificar(autovalores, tolerancia, metodo)


# --- both, for the pipeline --------------------------------------------------


def analisar(
    caminho_sbml: Path | str,
    condicoes: Simulacao,
    sobrescrever: Valores | None = None,
    papel: str = "original",
    tolerancia_do_equilibrio: float = TOLERANCIA_DO_EQUILIBRIO,
    tolerancia_marginal: float = TOLERANCIA_MARGINAL,
) -> Analise:
    """Find the equilibrium of one model and classify its local stability there."""
    try:
        modelo = preparar_modelo(caminho_sbml, condicoes, sobrescrever)
    except ErroDeSimulacao as erro:
        raise ErroDeQualitativo(str(erro)) from erro
    try:
        equilibrio = encontrar_equilibrio(modelo, condicoes, tolerancia_do_equilibrio)
        estabilidade = estabilidade_local(modelo, equilibrio.ponto, tolerancia_marginal)
    except ErroDeQualitativo as erro:
        raise ErroDeQualitativo(
            f"Análise qualitativa do modelo {papel} ('{caminho_sbml}'): {erro}"
        ) from erro
    return Analise(papel=papel, equilibrio=equilibrio, estabilidade=estabilidade)


def avisos(comparacao: Comparacao, t_fim: float) -> tuple[str, ...]:
    """Return what the report has to say next to a qualitative result, always.

    Two kinds of warning. The first is fixed: only one equilibrium was looked at. The
    second says, per model, how far outside the declared horizon the point was found --
    without it, a criterion met at t = 1e9 reads as a statement about the window the user
    asked about, which in the case-study model is 1.4 million times shorter (question 39 of
    ``docs/questoes-em-aberto.md``). Only stated when the instant is beyond ``t_fim``:
    inside the simulated window there is nothing to warn about.
    """
    linhas = [AVISO_DO_EQUILIBRIO_UNICO]
    for analise in (comparacao.original, comparacao.simplificado):
        instante = analise.equilibrio.instante
        vezes = analise.equilibrio.vezes_o_horizonte(t_fim)
        if instante is None or vezes is None or vezes <= 1.0:
            continue
        linhas.append(
            f"O equilíbrio do modelo {analise.papel} só foi alcançado em t = "
            f"{instante:.3g}, {vezes:.3g}× o horizonte simulado ({t_fim:g}): o critério "
            "qualitativo fala de um estado fora da janela declarada na configuração."
        )
    return tuple(linhas)


def _uma_linha(erro: object) -> str:
    return " ".join(str(erro).split())
