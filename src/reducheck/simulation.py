"""Simulate both models under identical time grid, solver and tolerances.

Every simulation goes through :func:`simular`, which takes the same
:class:`~reducheck.config.Simulacao` for both models. That is what makes the two
trajectories comparable point by point: the caller cannot accidentally give one model a
different horizon, solver or tolerance.

Two things this module does besides simulating, both of them about not reporting a number
that means less than it looks like:

* :func:`ruido_numerico` runs the original a second time with tolerances
  :data:`FATOR_DE_RUIDO` times looser and measures the NRMSE between the two runs. That is
  the *floor* of the comparison -- error the solver alone produces -- and a limit close to
  it is not measuring the reduction (capability S3).
* a simulation that fails, that produces NaN/infinity, or that drives a variable negative
  when the variables are declared non-negative stops with :class:`ErroDeSimulacao`, naming
  the variable and the instant. A broken integration must not reach the metrics, because
  there it would turn into a verdict.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import roadrunner

from reducheck import metrics
from reducheck.config import (
    SOLVERS_SUPORTADOS,
    Configuracao,
    Simulacao,
    Valores,
    Variavel,
    normalizar_alvo,
)

__all__ = [
    "FATOR_DE_RUIDO",
    "MARGEM_SOBRE_O_RUIDO",
    "ErroDeSimulacao",
    "RuidoNumerico",
    "Trajetorias",
    "avisos_de_ruido",
    "preparar",
    "ruido_numerico",
    "simular",
    "tipos_disponiveis",
    "unidade_de_tempo",
    "variaveis_de_estado",
]

#: How much looser the tolerances of the second run of the original are. Two orders of
#: magnitude is enough to make the solver take a visibly different internal step sequence
#: while still integrating the same problem.
FATOR_DE_RUIDO = 100.0

#: How many times the numerical noise a threshold has to be above it to be worth measuring.
#: Below that, what the criterion reports is mostly the solver, not the reduction.
MARGEM_SOBRE_O_RUIDO = 10.0


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


@dataclass(frozen=True)
class RuidoNumerico:
    """The floor of the comparison: how much the original differs from itself.

    Measured on the report variables, not on the raw columns of the model, so that the
    number can be read against the thresholds of the criteria.
    """

    #: How much looser the tolerances of the second run were.
    fator: float
    #: NRMSE between the two runs, per report variable.
    por_variavel: Mapping[str, float] = field(default_factory=dict)
    #: Variables whose noise could not be measured, and why (a constant series has no
    #: range to normalize by). They are named instead of silently left out.
    sem_medida: Mapping[str, str] = field(default_factory=dict)

    @property
    def maximo(self) -> float:
        """The largest noise over the variables, or 0.0 when none could be measured."""
        return max(self.por_variavel.values(), default=0.0)

    def resumo(self) -> str:
        """One line for the report, in the form ``docs/produto.md`` shows."""
        if not self.por_variavel:
            return (
                f"Ruído numérico de referência: não foi possível medir em nenhuma variável "
                f"(tolerâncias {self.fator:g}× mais frouxas)."
            )
        pior = max(self.por_variavel, key=lambda nome: self.por_variavel[nome])
        return (
            f"Ruído numérico de referência: {self.maximo:.3g} (NRMSE máximo, em '{pior}', "
            f"entre o original e ele mesmo com tolerâncias {self.fator:g}× mais frouxas)."
        )


def preparar(
    caminho_sbml: Path | str,
    condicoes: Simulacao,
    variaveis: Sequence[str] = (),
    sobrescrever: Valores | None = None,
) -> roadrunner.RoadRunner:
    """Load the model, apply the overrides and set the solver and its tolerances.

    Everything that makes two runs comparable happens here, in one place: both models of a
    comparison go through this function with the same :class:`~reducheck.config.Simulacao`.
    Public because the qualitative analysis (:mod:`reducheck.qualitative`) needs the loaded
    model itself, and not a table of trajectories -- it asks it for rates of change and for
    the Jacobian -- and it has to ask under exactly the same conditions the metrics saw.

    ``variaveis``, when given, are required to exist in the model before anything else
    happens, so a typo is a configuration error and not an empty column.
    """
    if condicoes.solver not in SOLVERS_SUPORTADOS:
        suportados = ", ".join(sorted(SOLVERS_SUPORTADOS))
        raise ErroDeSimulacao(
            f"O solver '{condicoes.solver}' não é suportado. Disponíveis: {suportados}."
        )
    modelo = _carregar(caminho_sbml)
    if variaveis:
        _exigir_variaveis_existentes(modelo, variaveis, caminho_sbml)
    _aplicar(modelo, sobrescrever, caminho_sbml)

    modelo.setIntegrator(condicoes.solver)
    modelo.integrator.relative_tolerance = condicoes.tol_relativa
    modelo.integrator.absolute_tolerance = condicoes.tol_absoluta
    return modelo


def simular(
    caminho_sbml: Path | str,
    condicoes: Simulacao,
    variaveis: Sequence[str],
    sobrescrever: Valores | None = None,
) -> Trajetorias:
    """Simulate the SBML model at ``caminho_sbml`` and return ``variaveis`` over time.

    ``sobrescrever`` replaces parameters and initial conditions of the file before
    integrating; it is what :meth:`reducheck.config.Sobrescrita.para` produced for this
    model, so the caller cannot mix up the two models' overrides.
    """
    if not variaveis:
        raise ErroDeSimulacao(f"Nenhuma variável pedida para '{caminho_sbml}'.")

    modelo = preparar(caminho_sbml, condicoes, variaveis, sobrescrever)
    modelo.selections = ["time", *variaveis]

    try:
        saida = np.asarray(
            modelo.simulate(condicoes.t_inicio, condicoes.t_fim, condicoes.pontos), dtype=float
        )
    except RuntimeError as erro:
        raise ErroDeSimulacao(
            f"A simulação de '{caminho_sbml}' falhou: {' '.join(str(erro).split())}"
        ) from erro

    trajetorias = Trajetorias(
        tempo=saida[:, 0], nomes=tuple(variaveis), estados=saida[:, 1:]
    )
    _conferir_finitos(trajetorias, caminho_sbml)
    if condicoes.nao_negativas:
        _conferir_nao_negativas(trajetorias, condicoes, caminho_sbml)
    return trajetorias


def ruido_numerico(
    caminho_sbml: Path | str,
    condicoes: Simulacao,
    variaveis: Sequence[Variavel],
    referencia: Trajetorias,
    sobrescrever: Valores | None = None,
    fator: float = FATOR_DE_RUIDO,
) -> RuidoNumerico:
    """Measure how much the original differs from itself when the tolerances are loosened.

    ``referencia`` is the run of the original the comparison already used, so the original
    is simulated once more, not twice. ``variaveis`` are the declared correspondences: the
    noise of a report variable is measured on the same combination the metrics see, and a
    variable the reduction dropped is skipped, because nothing is compared on it.
    """
    from reducheck import mapping  # deferred: mapping imports this module

    frouxas = condicoes.model_copy(
        update={
            "tol_relativa": condicoes.tol_relativa * fator,
            "tol_absoluta": condicoes.tol_absoluta * fator,
        }
    )
    outra = simular(caminho_sbml, frouxas, referencia.nomes, sobrescrever)

    por_variavel: dict[str, float] = {}
    sem_medida: dict[str, str] = {}
    for variavel in variaveis:
        if variavel.simplificado is None:
            continue
        pesos = normalizar_alvo(variavel.original)
        estrita = mapping.combinar(referencia, pesos, variavel.nome, "original")
        frouxa = mapping.combinar(outra, pesos, variavel.nome, "original")
        try:
            por_variavel[variavel.nome] = metrics.nrmse(
                referencia.tempo, estrita, frouxa
            ).valor
        except metrics.ErroDeMetrica as erro:
            sem_medida[variavel.nome] = str(erro)
    return RuidoNumerico(fator=fator, por_variavel=por_variavel, sem_medida=sem_medida)


def avisos_de_ruido(ruido: RuidoNumerico, configuracao: Configuracao) -> tuple[str, ...]:
    """Warn about every threshold that is not at least :data:`MARGEM_SOBRE_O_RUIDO` × the noise.

    A warning, never a failure: the threshold is the user's decision, and ``docs/produto.md``
    asks the library to flag a risky choice without stopping. The noise is an NRMSE, so for a
    criterion measured in another scale (``erro_max_abs``, in the unit of the variable) the
    comparison is only indicative -- the message says which metric it is about so the reader
    can tell (see ``docs/questoes-em-aberto.md``).
    """
    avisos: list[str] = []
    for indice, criterio in enumerate(configuracao.criterios):
        if criterio.limite is None:
            continue
        for nome in configuracao.variaveis_de(criterio):
            medido = ruido.por_variavel.get(nome)
            if medido is None or criterio.limite >= MARGEM_SOBRE_O_RUIDO * medido:
                continue
            avisos.append(
                f"criterios[{indice}] ({criterio.metrica} em '{nome}'): o limite "
                f"{criterio.limite:g} é menor que {MARGEM_SOBRE_O_RUIDO:g}× o ruído numérico "
                f"da variável ({medido:.3g}), então o critério mede mais o solver que a "
                "simplificação. Afrouxe o limite ou aperte as tolerâncias."
            )
    return tuple(avisos)


def tipos_disponiveis(caminho_sbml: Path | str) -> dict[str, str]:
    """Return every name the model at ``caminho_sbml`` can be asked for, and what it is.

    Used by :mod:`reducheck.config` to reject a mapping that cites a name the model does
    not have, and an override that puts a parameter where an initial condition belongs,
    *before* anything is simulated. Variables eliminated by QSSA appear here as
    ``parametro``, because that is how libRoadRunner exposes an assignment rule.
    """
    return _tipos(_carregar(caminho_sbml))


def variaveis_de_estado(caminho_sbml: Path | str) -> frozenset[str]:
    """Return the names of the state variables of the model at ``caminho_sbml``.

    These are the only names an equilibrium point has (see
    :func:`reducheck.qualitative.estado`, which reads the same listing): the floating
    species and the parameters with a rate rule. A variable defined by an assignment rule
    -- one eliminated by QSSA -- is not among them, nor is a constant, even though
    :func:`tipos_disponiveis` lists both as ``parametro``.
    """
    taxas = _carregar(caminho_sbml).getRatesOfChangeNamedArray()
    return frozenset(str(nome).removesuffix("'") for nome in taxas.colnames)


def unidade_de_tempo(caminho_sbml: Path | str) -> str | None:
    """Return the time unit the SBML model declares, or ``None`` when it declares none.

    Only used to label the time axis of the plots. libRoadRunner does not expose the
    attribute, so it is read from the file; a model that leaves ``timeUnits`` out (the
    usual case, including the toy models here) gets a generic label instead of a guess.
    """
    try:
        raiz = ElementTree.parse(str(caminho_sbml)).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    modelo = next(
        (no for no in raiz.iter() if no.tag.endswith("}model") or no.tag == "model"), None
    )
    if modelo is None:
        return None
    unidade = modelo.get("timeUnits")
    return unidade or None


def _tipos(modelo: roadrunner.RoadRunner) -> dict[str, str]:
    tipos = {nome: "parametro" for nome in modelo.model.getGlobalParameterIds()}
    for nome in (
        *modelo.model.getFloatingSpeciesIds(),
        *modelo.model.getBoundarySpeciesIds(),
    ):
        tipos[nome] = "especie"
    return tipos


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
    conhecidas = frozenset(_tipos(modelo))
    ausentes = [nome for nome in variaveis if nome not in conhecidas]
    if ausentes:
        disponiveis = ", ".join(sorted(conhecidas))
        raise ErroDeSimulacao(
            f"O modelo '{caminho_sbml}' não tem a variável {', '.join(ausentes)}. "
            f"Disponíveis: {disponiveis}."
        )


def _aplicar(
    modelo: roadrunner.RoadRunner, sobrescrever: Valores | None, caminho_sbml: Path | str
) -> None:
    """Replace parameters and initial conditions before integrating.

    An initial condition is written through ``init(X)``: assigning ``X`` directly would set
    the *current* value, which the first step of the integration overwrites.
    """
    if sobrescrever is None or sobrescrever.vazio():
        return
    alvos = {nome: nome for nome in sobrescrever.parametros}
    alvos.update({nome: f"init({nome})" for nome in sobrescrever.condicoes_iniciais})
    valores = {**sobrescrever.parametros, **sobrescrever.condicoes_iniciais}
    for nome, valor in valores.items():
        try:
            modelo[alvos[nome]] = valor
        except (RuntimeError, ValueError) as erro:
            campo = (
                "condicoes_iniciais" if nome in sobrescrever.condicoes_iniciais else "parametros"
            )
            raise ErroDeSimulacao(
                f"simulacao.sobrescrever.{campo}: não foi possível atribuir "
                f"{valor} a '{nome}' no modelo '{caminho_sbml}': "
                f"{' '.join(str(erro).split())}"
            ) from erro


def _conferir_finitos(trajetorias: Trajetorias, caminho_sbml: Path | str) -> None:
    """Refuse a run with NaN or infinity, naming where it first appeared."""
    ruins = np.argwhere(~np.isfinite(trajetorias.estados))
    if ruins.size == 0:
        return
    linha, coluna = (int(indice) for indice in ruins[0])
    raise ErroDeSimulacao(
        f"A simulação de '{caminho_sbml}' produziu um valor não finito (NaN ou infinito) "
        f"em '{trajetorias.nomes[coluna]}', em t = {trajetorias.tempo[linha]:.6g}. "
        "A integração divergiu; não há métrica a calcular."
    )


def _conferir_nao_negativas(
    trajetorias: Trajetorias, condicoes: Simulacao, caminho_sbml: Path | str
) -> None:
    """Refuse a run where a variable went negative, naming the variable and the instant.

    "Negative" means below the accuracy the solver itself claims for that variable:
    ``tol_absoluta + tol_relativa · max|x|``, which is the weight CVODE controls its local
    error with, taken over the whole series. A stricter threshold -- ``tol_absoluta`` alone --
    was tried first and flags healthy runs: a variable that decays towards zero undershoots
    it by accumulation (in the toy pair ``qssa_ok``, A reaches -1.0e-10 with
    ``tol_absoluta = 1e-10``), because local error control is not a global bound. Below the
    threshold the value is indistinguishable from zero for the integration that produced it;
    above it, the sign change is real.
    """
    escala = np.max(np.abs(trajetorias.estados), axis=0)
    limiar = -(condicoes.tol_absoluta + condicoes.tol_relativa * escala)
    ruins = np.argwhere(trajetorias.estados < limiar)
    if ruins.size == 0:
        return
    linha, coluna = (int(indice) for indice in ruins[0])
    raise ErroDeSimulacao(
        f"A simulação de '{caminho_sbml}' produziu um valor negativo em "
        f"'{trajetorias.nomes[coluna]}': {trajetorias.estados[linha, coluna]:.6g} em "
        f"t = {trajetorias.tempo[linha]:.6g}, abaixo da precisão que o solver garante para "
        f"essa variável ({-limiar[coluna]:.3g}). Se a variável pode ser negativa neste "
        "modelo, declare 'simulacao.nao_negativas: false'."
    )
