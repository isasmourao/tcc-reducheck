"""Pluggable quantitative metrics comparing the mapped trajectories.

Every metric has the same shape -- ``(tempo, original, simplificado, **parametros)`` ->
:class:`ResultadoDeMetrica`, both series on the same time grid, smaller is better -- and
registers itself under a name with :func:`registrar`. Adding a metric therefore means
adding a decorated function: the configuration validates the names it reads against
:func:`disponiveis`, and the per-metric options written under ``criterios[].parametros``
against the keyword arguments of the function itself (:func:`parametros_de`), so nothing
in the pipeline has to change. ``tests/test_units.py`` registers one from outside the
package to keep that promise honest.

A metric returns three things, not just a number: the value, a short description in
Portuguese of what the number means (the report prints it next to the value) and a list of
warnings. The warnings are how a metric says that it had to leave data out -- MAPE near
zero -- without failing the run, which is what ``docs/produto.md`` asks for ("avisa, sem
parar").

Formulas, with :math:`o` the original series, :math:`s` the simplified one and :math:`n`
the number of points, are in each docstring; they go into the text of the TCC.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

__all__ = [
    "ErroDeMetrica",
    "Metrica",
    "ResultadoDeMetrica",
    "calcular",
    "disponiveis",
    "erro_estacionario",
    "erro_max_abs",
    "erro_max_rel",
    "mape",
    "nrmse",
    "obter",
    "parametros_de",
    "registrar",
]

#: Default threshold under which a point is considered too close to zero to be divided by,
#: as a fraction of the largest absolute value of the original series. Relative, and not an
#: absolute number, so that the protection does not depend on the unit of the variable: a
#: concentration in mol/L and the same concentration in µmol/L exclude the same points.
EPSILON_RELATIVO = 1e-6


class ErroDeMetrica(Exception):
    """A métrica não existe, não aceita esse parâmetro, ou não se aplica a estas séries."""


@dataclass(frozen=True)
class ResultadoDeMetrica:
    """What every metric returns: the number, what it means, and what to watch out for."""

    #: The measured error. Lower is better, 0 means identical.
    valor: float
    #: One line, in Portuguese, saying what the number is and in which unit it is read.
    descricao: str
    #: Warnings about the measurement itself (excluded points, degenerate series).
    avisos: tuple[str, ...] = ()
    #: Anything the metric wants the report to state, such as how many points it dropped.
    detalhes: Mapping[str, Any] = field(default_factory=dict)


class Metrica(Protocol):
    """Common signature of every metric: lower is better, 0 means identical."""

    def __call__(
        self,
        tempo: np.ndarray,
        original: np.ndarray,
        simplificado: np.ndarray,
        **parametros: Any,
    ) -> ResultadoDeMetrica:
        """Return the error of ``simplificado`` with respect to ``original``."""
        ...


_REGISTRO: dict[str, Metrica] = {}


def registrar(nome: str) -> Callable[[Metrica], Metrica]:
    """Return a decorator that records a metric under ``nome``.

    The decorated function takes ``(tempo, original, simplificado)`` and, after those, only
    keyword arguments with a default: those are exactly the options the YAML may set under
    ``criterios[].parametros``, so the signature is the single source of truth for what a
    metric can be configured with.
    """

    def decorador(funcao: Metrica) -> Metrica:
        if nome in _REGISTRO:
            raise ErroDeMetrica(f"A métrica '{nome}' já está registrada.")
        _conferir_assinatura(nome, funcao)
        _REGISTRO[nome] = funcao
        return funcao

    return decorador


def _conferir_assinatura(nome: str, funcao: Metrica) -> None:
    """Refuse a metric whose signature the pipeline would not know how to call."""
    parametros = list(inspect.signature(funcao).parameters.values())
    posicionais = [
        parametro.name
        for parametro in parametros
        if parametro.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if posicionais[:3] != ["tempo", "original", "simplificado"]:
        raise ErroDeMetrica(
            f"A métrica '{nome}' tem que começar com os parâmetros (tempo, original, "
            f"simplificado); recebido ({', '.join(posicionais) or 'nenhum'})."
        )
    for parametro in parametros[3:]:
        if parametro.default is inspect.Parameter.empty:
            raise ErroDeMetrica(
                f"A métrica '{nome}': o parâmetro '{parametro.name}' precisa de um valor "
                "padrão, porque a configuração pode não informá-lo."
            )


def disponiveis() -> frozenset[str]:
    """Return the names of every registered metric.

    This is what :mod:`reducheck.config` validates the configuration against, so adding a
    metric here is enough to make it usable from the YAML.
    """
    return frozenset(_REGISTRO)


def obter(nome: str) -> Metrica:
    """Return the metric registered under ``nome``."""
    try:
        return _REGISTRO[nome]
    except KeyError as erro:
        nomes = ", ".join(sorted(_REGISTRO))
        raise ErroDeMetrica(
            f"A métrica '{nome}' não existe. Disponíveis: {nomes}."
        ) from erro


def parametros_de(nome: str) -> frozenset[str]:
    """Return the names of the options ``nome`` accepts under ``criterios[].parametros``."""
    assinatura = inspect.signature(obter(nome))
    return frozenset(list(assinatura.parameters)[3:])


def calcular(
    nome: str,
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    parametros: Mapping[str, Any] | None = None,
) -> ResultadoDeMetrica:
    """Run the metric registered under ``nome`` with the options read from the YAML."""
    metrica = obter(nome)
    parametros = dict(parametros or {})
    desconhecidos = sorted(set(parametros) - parametros_de(nome))
    if desconhecidos:
        aceitos = ", ".join(sorted(parametros_de(nome))) or "nenhum"
        raise ErroDeMetrica(
            f"A métrica '{nome}' não aceita o parâmetro {', '.join(desconhecidos)}. "
            f"Aceita: {aceitos}."
        )
    return metrica(tempo, original, simplificado, **parametros)


# --- metrics -----------------------------------------------------------------


@registrar("nrmse")
def nrmse(
    tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray
) -> ResultadoDeMetrica:
    r"""Return the RMSE normalized by the range (``max - min``) of the original series.

    .. math:: \mathrm{NRMSE} = \frac{\sqrt{\frac1n \sum_i (o_i - s_i)^2}}
              {\max_i o_i - \min_i o_i}

    Normalizing by the range, and not by the mean, is what ``docs/produto.md`` and the toy
    fixtures use; the choice is still open with the supervisor (see
    ``docs/questoes-em-aberto.md``), which is why the report records it next to the number.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    amplitude = float(original.max() - original.min())
    if amplitude == 0.0:
        raise ErroDeMetrica(
            "nrmse: a série do original é constante, então a amplitude usada para normalizar "
            "é zero. Use outra métrica para esta variável."
        )
    rmse = float(np.sqrt(np.mean((original - simplificado) ** 2)))
    return ResultadoDeMetrica(
        valor=rmse / amplitude,
        descricao="RMSE normalizado pela amplitude do original (fração: 0,05 = 5%)",
    )


@registrar("mape")
def mape(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    epsilon: float | None = None,
) -> ResultadoDeMetrica:
    r"""Return the mean relative error, leaving out the points where the original is ~0.

    .. math:: \mathrm{MAPE} = \frac{1}{|I|} \sum_{i \in I}
              \frac{|o_i - s_i|}{|o_i|}, \quad
              I = \{\, i : |o_i| \ge \varepsilon \,\}

    The value is a *fraction*, not a percentage: 0,081 is an error of 8,1%, which is how
    the thresholds are written in ``docs/produto.md``.

    The quotient blows up wherever the original approaches zero -- exactly what happens in
    the model of Verly et al. (2024), whose variables start at or near zero -- so the
    points with :math:`|o_i| < \varepsilon` are excluded and their number is reported as a
    warning. By default :math:`\varepsilon` is ``EPSILON_RELATIVO`` times the largest
    absolute value of the original series, so the protection does not depend on the unit of
    the variable; ``criterios[].parametros.epsilon`` sets an absolute value instead.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    relativo, validos, limiar = _erros_relativos(original, simplificado, epsilon, "mape")
    excluidos = int(original.size - relativo.size)
    return ResultadoDeMetrica(
        valor=float(np.mean(relativo)),
        descricao="erro relativo médio (fração: 0,05 = 5%)",
        avisos=_aviso_de_exclusao("mape", excluidos, original.size, limiar),
        detalhes={
            "pontos_excluidos": excluidos,
            "pontos_usados": int(relativo.size),
            "epsilon": limiar,
        },
    )


@registrar("erro_max_abs")
def erro_max_abs(
    tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray
) -> ResultadoDeMetrica:
    r"""Return the largest absolute difference between the two series.

    .. math:: E_{\max} = \max_i |o_i - s_i|

    It is the only metric here that keeps the unit of the variable, which is what makes it
    usable where the original passes through zero and every relative metric has to give up.
    The report also records *when* the maximum happened: a large error concentrated in the
    initial transient means something different from the same error at the end.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    diferenca = np.abs(original - simplificado)
    indice = int(np.argmax(diferenca))
    return ResultadoDeMetrica(
        valor=float(diferenca[indice]),
        descricao="maior erro absoluto (na unidade da variável)",
        detalhes={"instante": float(np.asarray(tempo, dtype=float)[indice])},
    )


@registrar("erro_max_rel")
def erro_max_rel(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    epsilon: float | None = None,
) -> ResultadoDeMetrica:
    r"""Return the largest relative error, leaving out the points where the original is ~0.

    .. math:: E^{\mathrm{rel}}_{\max} = \max_{i \in I} \frac{|o_i - s_i|}{|o_i|},
              \quad I = \{\, i : |o_i| \ge \varepsilon \,\}

    Same protection, same ``epsilon``, and the same fraction convention as :func:`mape`;
    what changes is that this one answers "how wrong does it ever get", not "how wrong is
    it on average", so a short bad transient shows up here and is diluted in the MAPE.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    relativo, validos, limiar = _erros_relativos(
        original, simplificado, epsilon, "erro_max_rel"
    )
    excluidos = int(original.size - relativo.size)
    posicao = int(np.flatnonzero(validos)[int(np.argmax(relativo))])
    return ResultadoDeMetrica(
        valor=float(np.max(relativo)),
        descricao="maior erro relativo (fração: 0,05 = 5%)",
        avisos=_aviso_de_exclusao("erro_max_rel", excluidos, original.size, limiar),
        detalhes={
            "pontos_excluidos": excluidos,
            "epsilon": limiar,
            "instante": float(np.asarray(tempo, dtype=float)[posicao]),
        },
    )


@registrar("erro_estacionario")
def erro_estacionario(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    fracao_final: float = 0.0,
) -> ResultadoDeMetrica:
    r"""Return the relative error at the end of the simulation.

    .. math:: E_{\mathrm{ee}} = \frac{|\bar o - \bar s|}{|\bar o|}

    where :math:`\bar o` and :math:`\bar s` are the averages over the last
    ``fracao_final`` of the *time* span. With the default ``fracao_final = 0`` the averages
    are the final values alone, which is the comparison ``docs/produto.md`` describes ("fim
    da simulação"); averaging a final window instead is what makes the number readable when
    the trajectory is still oscillating or the solver output is noisy.

    The window is taken on the time axis, not on the number of points, so the value does
    not change when the same horizon is simulated with more points. A simplification can be
    faithful in the transient and wrong at the end, or the reverse, which is why this is a
    criterion of its own and not a summary of the others.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    tempo = np.asarray(tempo, dtype=float)
    if not 0.0 <= fracao_final < 1.0:
        raise ErroDeMetrica(
            "erro_estacionario: 'fracao_final' tem que estar em [0, 1); "
            f"recebido {fracao_final}."
        )
    janela = tempo >= tempo[-1] - fracao_final * (tempo[-1] - tempo[0])
    media_original = float(np.mean(original[janela]))
    media_simplificado = float(np.mean(simplificado[janela]))
    if media_original == 0.0:
        raise ErroDeMetrica(
            "erro_estacionario: o valor final do original é zero, então não há erro "
            "relativo a calcular. Use 'erro_max_abs' para esta variável."
        )
    avisos: tuple[str, ...] = ()
    pontos = int(np.count_nonzero(janela))
    if fracao_final > 0.0 and pontos == 1:
        avisos = (
            f"erro_estacionario: a fração final {fracao_final:g} pegou um único ponto da "
            "malha; aumente 'pontos' na simulação ou 'fracao_final' no critério.",
        )
    return ResultadoDeMetrica(
        valor=abs(media_original - media_simplificado) / abs(media_original),
        descricao="erro relativo no fim da simulação (fração: 0,05 = 5%)",
        avisos=avisos,
        detalhes={
            "pontos_na_janela": pontos,
            "original": media_original,
            "simplificado": media_simplificado,
        },
    )


# --- helpers -----------------------------------------------------------------


def _conferir_formato(
    tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    original = np.asarray(original, dtype=float)
    simplificado = np.asarray(simplificado, dtype=float)
    tempo = np.asarray(tempo, dtype=float)
    if original.shape != simplificado.shape:
        raise ErroDeMetrica(
            f"As duas séries têm tamanhos diferentes: {original.shape} e {simplificado.shape}."
        )
    if tempo.shape != original.shape:
        raise ErroDeMetrica(
            f"O vetor de tempo tem {tempo.shape} e as séries têm {original.shape}."
        )
    if original.size == 0:
        raise ErroDeMetrica("As séries comparadas estão vazias.")
    return original, simplificado


def _limiar(original: np.ndarray, epsilon: float | None, nome: str) -> float:
    """Return the threshold under which a point is too close to zero to divide by."""
    if epsilon is not None:
        if epsilon <= 0.0:
            raise ErroDeMetrica(
                f"{nome}: 'epsilon' tem que ser maior que zero; recebido {epsilon}."
            )
        return float(epsilon)
    escala = float(np.max(np.abs(original)))
    if escala == 0.0:
        raise ErroDeMetrica(
            f"{nome}: a série do original é identicamente zero, então não há erro relativo "
            "a calcular. Use 'erro_max_abs' para esta variável."
        )
    return EPSILON_RELATIVO * escala


def _erros_relativos(
    original: np.ndarray, simplificado: np.ndarray, epsilon: float | None, nome: str
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return the pointwise relative errors, the mask that survived, and the threshold.

    Shared by :func:`mape` and :func:`erro_max_rel`: both divide by the original, so both
    have to drop the same points and refuse the same degenerate series.
    """
    limiar = _limiar(original, epsilon, nome)
    validos = np.abs(original) >= limiar
    if not validos.any():
        raise ErroDeMetrica(
            f"{nome}: todos os {original.size} pontos têm |original| < {limiar:g}, então "
            "não sobra nada para dividir. Use 'erro_max_abs' para esta variável."
        )
    relativo = np.abs(original[validos] - simplificado[validos]) / np.abs(original[validos])
    return relativo, validos, limiar


def _aviso_de_exclusao(
    nome: str, excluidos: int, total: int, limiar: float
) -> tuple[str, ...]:
    """Return the warning that says how much data the protection near zero threw away."""
    if excluidos == 0:
        return ()
    return (
        f"{nome}: {excluidos} de {total} pontos foram excluídos por terem |original| < "
        f"{limiar:g} (divisão por valor perto de zero). O valor foi calculado com os "
        f"{total - excluidos} pontos restantes.",
    )
