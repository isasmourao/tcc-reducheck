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
    "AGREGACOES",
    "ErroDeMetrica",
    "Metrica",
    "ResultadoDeMetrica",
    "agregar",
    "calcular",
    "disponiveis",
    "erro_estacionario",
    "erro_integral",
    "erro_l2_rel",
    "erro_max_abs",
    "erro_max_rel",
    "erro_simetrico",
    "mape",
    "nrmse",
    "obter",
    "parametros_de",
    "registrar",
    "rmse",
]

#: Default threshold under which a point is considered too close to zero to be divided by,
#: as a fraction of the largest absolute value of the original series. Relative, and not an
#: absolute number, so that the protection does not depend on the unit of the variable: a
#: concentration in mol/L and the same concentration in µmol/L exclude the same points.
EPSILON_RELATIVO = 1e-6

#: A point is "close to zero", for the warning about MAPE, when the original is below this
#: fraction of its own peak. Much larger than :data:`EPSILON_RELATIVO` on purpose: the points
#: under the epsilon are already left out, and what misleads the MAPE are the ones just above
#: it, divided by a number small enough to blow the relative error up. Relative for the same
#: reason as the epsilon. Arbitrary, and registered as such in ``docs/questoes-em-aberto.md``.
PERTO_DE_ZERO = 0.01

#: MAPE warns when more than this fraction of the points is close to zero (issue #19).
FRACAO_PERTO_DE_ZERO = 0.05

#: NRMSE warns when a single point holds more than this share of the squared error: the
#: number then describes one spike, not the trajectory (issue #19).
FRACAO_DO_PICO = 0.5

#: How the pointwise error of a metric adds up to its value: the mean, the square root of
#: the mean, or the maximum. What lets the verdict compute the same metric on a window of
#: time without knowing its formula.
AGREGACOES = frozenset({"media", "raiz_da_media", "maximo"})


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
    #: Whether the value is a fraction (0,05 = 5%), so the reasons print it as a
    #: percentage, or a number in the unit of the variable.
    fracao: bool = False
    #: One non-negative number per time point, ``NaN`` where the point was left out, such
    #: that :func:`agregar` over every point gives back :attr:`valor`. Optional: a metric
    #: that is not a sum over points (``erro_estacionario``) leaves it out, and its failure
    #: then has no window of time in the reason.
    erro_pontual: np.ndarray | None = field(default=None, compare=False, repr=False)
    #: One of :data:`AGREGACOES`; required when :attr:`erro_pontual` is given.
    agregacao: str | None = None

    def __post_init__(self) -> None:
        """Refuse a pointwise error that the verdict would not know how to add up."""
        if self.erro_pontual is not None and self.agregacao not in AGREGACOES:
            raise ErroDeMetrica(
                "Uma métrica com erro ponto a ponto precisa dizer como ele se agrega "
                f"({', '.join(sorted(AGREGACOES))}); recebido {self.agregacao!r}."
            )


def agregar(
    erro_pontual: np.ndarray, agregacao: str | None, mascara: np.ndarray
) -> float | None:
    """Return the metric computed on the points of ``mascara`` alone.

    The normalization stays the one of the whole series -- the range of the original in
    NRMSE, each point's own value in MAPE -- so the number on a window can be read against
    the number on the whole run. ``None`` when no valid point falls in the mask.
    """
    erro = np.asarray(erro_pontual, dtype=float)[mascara]
    erro = erro[~np.isnan(erro)]
    if erro.size == 0:
        return None
    if agregacao == "media":
        return float(np.mean(erro))
    if agregacao == "raiz_da_media":
        return float(np.sqrt(np.mean(erro)))
    if agregacao == "maximo":
        return float(np.max(erro))
    raise ErroDeMetrica(f"Agregação desconhecida: {agregacao!r}.")


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

    Limite base da literatura: sem limite na literatura; o valor usado no estudo de caso é
    convenção do TCC.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    amplitude = float(original.max() - original.min())
    if amplitude == 0.0:
        raise ErroDeMetrica(
            "nrmse: a série do original é constante, então a amplitude usada para normalizar "
            "é zero. Use outra métrica para esta variável."
        )
    quadrado = ((original - simplificado) / amplitude) ** 2
    total = float(np.sum(quadrado))
    indice = int(np.argmax(quadrado))
    fracao_do_pico = float(quadrado[indice]) / total if total > 0.0 else 0.0
    avisos: tuple[str, ...] = ()
    if fracao_do_pico > FRACAO_DO_PICO:
        instante = float(np.asarray(tempo, dtype=float)[indice])
        avisos = (
            f"nrmse: um único ponto (t = {instante:g}) responde por "
            f"{100 * fracao_do_pico:.0f}% do erro quadrático, então o valor descreve esse "
            "pico e não a trajetória. 'erro_max_abs' mede o pico diretamente.",
        )
    return ResultadoDeMetrica(
        valor=float(np.sqrt(np.mean(quadrado))),
        descricao="RMSE normalizado pela amplitude do original (fração: 0,05 = 5%)",
        avisos=avisos,
        detalhes={"fracao_do_maior_ponto": fracao_do_pico},
        fracao=True,
        erro_pontual=quadrado,
        agregacao="raiz_da_media",
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

    Fonte: Hyndman & Koehler (2006), "Another look at measures of forecast accuracy",
    International Journal of Forecasting 22(4), apontam que o erro percentual é indefinido
    ou explode quando o valor observado é zero ou perto de zero; é o motivo da exclusão.

    Limite base da literatura: sem limite na literatura.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    relativo, validos, limiar = _erros_relativos(original, simplificado, epsilon, "mape")
    excluidos = int(original.size - relativo.size)
    pico = float(np.max(np.abs(original)))
    # Only the points that are divided by: the ones under the epsilon are already out.
    perto = int(np.count_nonzero(validos & (np.abs(original) < PERTO_DE_ZERO * pico)))
    return ResultadoDeMetrica(
        valor=float(np.mean(relativo)),
        descricao="erro relativo médio (fração: 0,05 = 5%)",
        avisos=(
            *_aviso_de_exclusao("mape", excluidos, original.size, limiar),
            *_aviso_perto_de_zero("mape", perto, original.size, pico, rotulo="o MAPE"),
        ),
        detalhes={
            "pontos_excluidos": excluidos,
            "pontos_usados": int(relativo.size),
            "epsilon": limiar,
            "pontos_perto_de_zero": perto,
        },
        fracao=True,
        erro_pontual=_espalhar(relativo, validos),
        agregacao="media",
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
        erro_pontual=diferenca,
        agregacao="maximo",
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

    Fonte: Snowden, van der Graaf & Tindall (2017a), BMC Systems Biology 11:17, usam o erro
    relativo máximo nas saídas com tolerância de 5%, escolhida pelos autores como critério
    de parada do algoritmo, não como padrão. Avaliar cada variável ≤ 5% equivale a exigir o
    máximo sobre as saídas ≤ 5%. [VERIFICAR: se Snowden normaliza ponto a ponto ou pela
    norma da saída]

    Limite base da literatura: 0,05 (Snowden et al., 2017a).
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
        fracao=True,
        erro_pontual=_espalhar(relativo, validos),
        agregacao="maximo",
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

    Limite base da literatura: sem limite na literatura; o valor usado no estudo de caso é
    convenção do TCC.
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
        fracao=True,
    )


# --- metrics from the model-reduction literature -----------------------------


@registrar("rmse")
def rmse(
    tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray
) -> ResultadoDeMetrica:
    r"""Return the root mean squared error, in the unit of the variable.

    .. math:: \mathrm{RMSE} = \sqrt{\frac1n \sum_i (o_i - s_i)^2}

    A plain mean over the points, like :func:`nrmse`, of which it is the numerator:
    ``rmse == nrmse * (max(o) - min(o))``. Because it keeps the unit of the variable, it
    must not be compared or added across variables. Chai & Draxler (2014), Geoscientific
    Model Development 7, conclude that no single metric is enough on its own; this one is
    here as the unnormalized companion of the others, not as a criterion in itself.

    Limite base da literatura: sem limite na literatura (depende da escala da variável).
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    quadrado = (original - simplificado) ** 2
    return ResultadoDeMetrica(
        valor=float(np.sqrt(np.mean(quadrado))),
        descricao="raiz do erro quadrático médio (na unidade da variável)",
        fracao=False,
        erro_pontual=quadrado,
        agregacao="raiz_da_media",
    )


@registrar("erro_integral")
def erro_integral(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    epsilon: float | None = None,
) -> ResultadoDeMetrica:
    r"""Return the relative error integrated in time (Rao et al., 2014, eq. 14).

    .. math:: I = \frac1T \int_0^T \left| 1 - \frac{s(t)}{o(t)} \right| dt
              \approx \frac{\sum_{i \in I} w_i\, e_i}{\sum_{i \in I} w_i}, \quad
              e_i = \frac{|o_i - s_i|}{|o_i|}

    with :math:`w_i` the trapezoid weights of the time grid (:func:`_pesos_trapezio`) and
    :math:`I` the points where :math:`|o_i| \ge \varepsilon`, with the same ``epsilon`` as
    :func:`mape`. Without excluded points the denominator is :math:`T`. Unlike the MAPE,
    each point counts by the time it covers, so the value does not depend on how the grid
    is spaced.

    Fonte: Rao et al. (2014), BMC Systems Biology 8:52, eq. 14. Em Rao a mesma integral
    também é tirada a média sobre as espécies importantes; aqui cada variável vira um item
    do veredito, o que é mais rígido: cada uma tem de passar sozinha. Rao parou a redução
    em I = 0,1 e observou diferenças visuais claras com 0,2. Rao exige uma rede
    assintoticamente estável, e o resultado depende da janela [0, T] simulada.

    Limite base da literatura: 0,10 (Rao et al., 2014).
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    pesos = _pesos_trapezio(tempo)
    relativo, validos, limiar = _erros_relativos(
        original, simplificado, epsilon, "erro_integral"
    )
    excluidos = int(original.size - relativo.size)
    pico = float(np.max(np.abs(original)))
    perto = int(np.count_nonzero(validos & (np.abs(original) < PERTO_DE_ZERO * pico)))
    valor, pontual = _media_ponderada(relativo, pesos[validos])
    return ResultadoDeMetrica(
        valor=valor,
        descricao=(
            "erro relativo médio integrado no tempo (Rao et al., 2014; fração: 0,1 = 10%)"
        ),
        avisos=(
            *_aviso_de_exclusao("erro_integral", excluidos, original.size, limiar),
            *_aviso_perto_de_zero("erro_integral", perto, original.size, pico),
        ),
        detalhes={
            "pontos_excluidos": excluidos,
            "pontos_usados": int(relativo.size),
            "epsilon": limiar,
            "pontos_perto_de_zero": perto,
        },
        fracao=True,
        erro_pontual=_espalhar(pontual, validos),
        agregacao="media",
    )


@registrar("erro_simetrico")
def erro_simetrico(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    epsilon: float | None = None,
) -> ResultadoDeMetrica:
    r"""Return the symmetric integrated relative error (Frøysa et al., 2018, eqs. 3-4).

    .. math:: E = \tfrac12 \left[ I(s, o) + I(o, s) \right], \quad
              I(x_r, x_f) = \frac1T \int_0^T \left| 1 - \frac{x_r(t)}{x_f(t)} \right| dt

    :math:`I(s, o)` is :func:`erro_integral`, which divides by the original, and
    :math:`I(o, s)` divides by the simplified. Both terms use the same points and the same
    trapezoid weights: a point is valid when :math:`|o_i| \ge \varepsilon_o` and
    :math:`|s_i| \ge \varepsilon_s`, with each epsilon ``EPSILON_RELATIVO`` times the peak
    of its own series, or the absolute ``epsilon`` for both when one is given. The value
    is therefore unchanged when the two series swap places.

    Fonte: Frøysa, Fallahi & Blaser (2018), BMC Systems Biology 12:79, eqs. 3-4. O artigo
    usa esta medida para agrupar e ranquear reduções sob incerteza de parâmetros (teste KS
    com limiar 0,2), e não como critério de aceitação; não dá limite absoluto. Avisos do
    próprio artigo: um T curto não cobre a dinâmica, e um T longo demais reduz a integral à
    diferença entre os estados estacionários.

    Limite base da literatura: o artigo não tem. 0,10 é um limite DERIVADO de Rao et al.
    (2014), porque E é a média de duas integrais de Rao; não é de Frøysa et al. (2018).
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    pesos = _pesos_trapezio(tempo)
    limiar_original = _limiar(original, epsilon, "erro_simetrico")
    if epsilon is None and float(np.max(np.abs(simplificado))) == 0.0:
        raise ErroDeMetrica(
            "erro_simetrico: a série do simplificado é identicamente zero, então o termo "
            "que divide pelo simplificado não existe. Use 'erro_integral' ou 'erro_max_abs' "
            "para esta variável."
        )
    limiar_simplificado = (
        limiar_original if epsilon is not None else EPSILON_RELATIVO * float(
            np.max(np.abs(simplificado))
        )
    )
    validos = (np.abs(original) >= limiar_original) & (
        np.abs(simplificado) >= limiar_simplificado
    )
    if not validos.any():
        raise ErroDeMetrica(
            f"erro_simetrico: em todos os {original.size} pontos o original ou o "
            "simplificado está perto de zero, então não sobra nada para dividir. Use "
            "'erro_max_abs' para esta variável."
        )
    diferenca = np.abs(original[validos] - simplificado[validos])
    pelo_original = diferenca / np.abs(original[validos])
    pelo_simplificado = diferenca / np.abs(simplificado[validos])
    pesos_validos = pesos[validos]
    termo_original, _ = _media_ponderada(pelo_original, pesos_validos)
    termo_simplificado, _ = _media_ponderada(pelo_simplificado, pesos_validos)
    valor, pontual = _media_ponderada(
        0.5 * (pelo_original + pelo_simplificado), pesos_validos
    )
    excluidos = int(original.size - np.count_nonzero(validos))
    return ResultadoDeMetrica(
        valor=valor,
        descricao="erro relativo simétrico integrado (Frøysa et al., 2018)",
        avisos=_aviso_de_exclusao_simetrico(
            excluidos, original.size, limiar_original, limiar_simplificado
        ),
        detalhes={
            "I_original": termo_original,
            "I_simplificado": termo_simplificado,
            "pontos_excluidos": excluidos,
            "epsilon_original": limiar_original,
            "epsilon_simplificado": limiar_simplificado,
        },
        fracao=True,
        erro_pontual=_espalhar(pontual, validos),
        agregacao="media",
    )


@registrar("erro_l2_rel")
def erro_l2_rel(
    tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray
) -> ResultadoDeMetrica:
    r"""Return the relative error in the L² norm over the simulated window.

    .. math:: E = \frac{\lVert o - s \rVert_{L^2(0,T)}}{\lVert o \rVert_{L^2(0,T)}}
              = \sqrt{\frac{\int_0^T (o - s)^2\, dt}{\int_0^T o^2\, dt}}
              \approx \sqrt{\frac{\sum_i w_i (o_i - s_i)^2}{\sum_i w_i o_i^2}}

    with the trapezoid weights :math:`w_i`. No point is left out: the norm is of the whole
    series, so a point near zero does not blow the value up, which is what makes it usable
    on variables that start at zero (``M1`` in the Verly model).

    Fonte: Vejchodský (2014), Mathematica Bohemica 139(4), Tabela 1. Vejchodský alinha o
    período e a fase antes de calcular, porque o modelo dele oscila; aqui NÃO há
    alinhamento (modelos oscilantes estão fora do escopo), então um atraso entra como erro.
    Números do artigo, como referência e não como limite: QSSA padrão 92,7%, QSSA com
    atraso 19%.

    Limite base da literatura: sem limite na literatura.
    """
    original, simplificado = _conferir_formato(tempo, original, simplificado)
    pesos = _pesos_trapezio(tempo)
    norma_original = float(np.sum(pesos * original**2))
    if norma_original == 0.0:
        raise ErroDeMetrica(
            "erro_l2_rel: a norma L² do original é zero (a série é identicamente zero), "
            "então não há erro relativo a calcular. Use 'erro_max_abs' para esta variável."
        )
    pontual = original.size * pesos * (original - simplificado) ** 2 / norma_original
    return ResultadoDeMetrica(
        valor=float(np.sqrt(np.sum(pesos * (original - simplificado) ** 2) / norma_original)),
        descricao="erro relativo na norma L² (fração: 0,2 = 20%)",
        fracao=True,
        erro_pontual=pontual,
        agregacao="raiz_da_media",
    )


# --- helpers -----------------------------------------------------------------


def _pesos_trapezio(tempo: np.ndarray) -> np.ndarray:
    r"""Return the trapezoid weights of a (possibly non-uniform) time grid.

    :math:`w_0 = (t_1 - t_0)/2`, :math:`w_i = (t_{i+1} - t_{i-1})/2` inside and
    :math:`w_N = (t_N - t_{N-1})/2`, so :math:`\sum_i w_i = t_N - t_0` and
    :math:`\sum_i w_i f_i` is the trapezoid rule for :math:`\int f\,dt`. Written by hand,
    and not with ``np.trapz``, because that name changed between numpy versions.
    """
    tempo = np.asarray(tempo, dtype=float)
    if tempo.size < 2:
        raise ErroDeMetrica(
            "As métricas integrais precisam de pelo menos dois instantes de tempo."
        )
    passos = np.diff(tempo)
    pesos = np.zeros_like(tempo)
    pesos[:-1] += passos / 2.0
    pesos[1:] += passos / 2.0
    return pesos


def _media_ponderada(
    erro: np.ndarray, pesos: np.ndarray
) -> tuple[float, np.ndarray]:
    """Return the weighted mean of ``erro`` and the pointwise terms whose plain mean it is.

    The pointwise term is ``erro_i * w_i / mean(w)``, so averaging it over the same points
    gives back exactly ``sum(w * erro) / sum(w)``: that is what lets the verdict compute an
    integral metric on a window with :func:`agregar` and ``"media"``.
    """
    total = float(np.sum(pesos))
    if total <= 0.0:
        raise ErroDeMetrica(
            "Os pontos válidos não cobrem nenhum intervalo de tempo, então a integral não "
            "pode ser calculada."
        )
    return float(np.sum(pesos * erro) / total), erro * pesos / float(np.mean(pesos))


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


def _aviso_de_exclusao_simetrico(
    excluidos: int, total: int, limiar_original: float, limiar_simplificado: float
) -> tuple[str, ...]:
    """Return the exclusion warning of :func:`erro_simetrico`, which divides by both."""
    if excluidos == 0:
        return ()
    return (
        f"erro_simetrico: {excluidos} de {total} pontos foram excluídos por terem "
        f"|original| < {limiar_original:g} ou |simplificado| < {limiar_simplificado:g} "
        "(divisão por valor perto de zero). O valor foi calculado com os "
        f"{total - excluidos} pontos restantes, os mesmos nos dois termos.",
    )


def _aviso_perto_de_zero(
    nome: str, perto: int, total: int, pico: float, rotulo: str | None = None
) -> tuple[str, ...]:
    """Return the warning that a relative metric divides by too many small numbers.

    ``nome`` opens the message, as in every warning of a metric; ``rotulo`` is how the
    metric is called inside the sentence (``"o MAPE"``), and defaults to its quoted name.
    """
    if perto <= FRACAO_PERTO_DE_ZERO * total:
        return ()
    rotulo = rotulo if rotulo is not None else f"'{nome}'"
    return (
        f"{nome}: {perto} de {total} pontos ({100 * perto / total:.0f}%) entram no cálculo "
        f"perto de zero (|original| < {100 * PERTO_DE_ZERO:g}% do máximo, "
        f"{PERTO_DE_ZERO * pico:.3g}); "
        f"nesses pontos uma diferença pequena vira um erro relativo grande, e {rotulo} pode "
        "reprovar uma trajetória boa. 'nrmse' ou 'erro_max_abs' não dividem pelo valor.",
    )


def _espalhar(relativo: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """Put the errors of the valid points back on the full grid, ``NaN`` elsewhere."""
    erro = np.full(validos.shape, np.nan)
    erro[validos] = relativo
    return erro
