"""ReduCheck: verify whether a simplified ODE model is faithful to the original one.

The whole library is used through :func:`verificar`, which runs the pipeline described in
``docs/produto.md``: read the configuration, simulate both models under identical conditions,
map the variables, measure the metrics, decide the verdict and write the report.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from reducheck import config as _config
from reducheck import mapping, qualitative, report, simulation, verdict
from reducheck.mapping import SerieComparada
from reducheck.simulation import RuidoNumerico
from reducheck.verdict import ItemAvaliado, Veredito

__all__ = ["Resultado", "RuidoNumerico", "__version__", "verificar"]

__version__ = "0.1.0.dev0"


@dataclass(frozen=True)
class Resultado:
    """What a verification produced: the verdict plus where it was written."""

    configuracao: _config.Configuracao
    veredito: Veredito
    #: Where each requested report format was written, keyed by format name.
    caminhos: Mapping[str, Path]
    #: The floor of the comparison, measured by simulating the original twice.
    ruido: RuidoNumerico
    #: Warnings that are not about a single metric: the noise itself and every threshold
    #: too close to it.
    avisos: tuple[str, ...] = ()
    #: The two series of each mapped variable, already on the same time grid. Kept so that
    #: whoever calls from Python can plot or re-analyse without simulating again.
    series: Mapping[str, SerieComparada] = field(default_factory=dict)
    #: The equilibrium and the local stability of each model, or ``None`` when no
    #: qualitative criterion was declared and the analysis was therefore not run.
    comparacao: qualitative.Comparacao | None = None

    @property
    def caminho_json(self) -> Path | None:
        """Where ``resultado.json`` went, or ``None`` when json was not asked for."""
        return self.caminhos.get("json")

    @property
    def caminho_relatorio(self) -> Path | None:
        """Where the readable report went: the HTML if there is one, else the Markdown."""
        return self.caminhos.get("html") or self.caminhos.get("md")

    @property
    def nivel(self) -> str:
        """The verdict itself: APROVADO, APROVADO COM RESSALVAS or REPROVADO."""
        return self.veredito.nivel

    @property
    def aprovado(self) -> bool:
        """Whether the verdict is the plain approval, with no reservation."""
        return self.veredito.aprovado

    @property
    def porcentagem(self) -> float:
        """Percentage of (criterion, variable) items that passed."""
        return self.veredito.porcentagem

    @property
    def criterios(self) -> tuple[ItemAvaliado, ...]:
        """Every evaluated (criterion, variable) item."""
        return self.veredito.criterios


def verificar(
    caminho_config: Path | str, pasta_de_saida: Path | str | None = None
) -> Resultado:
    """Run the whole verification described by the YAML at ``caminho_config``.

    ``pasta_de_saida`` replaces ``relatorio.pasta`` of the configuration, for the ``--saida``
    option of the command line. Paths inside the YAML are relative to the YAML itself, but
    this one comes from a shell, so it is relative to the current directory instead.
    """
    configuracao = _config.carregar(caminho_config)
    if pasta_de_saida is not None:
        configuracao = configuracao.model_copy(
            update={
                "relatorio": configuracao.relatorio.model_copy(
                    update={"pasta": Path(pasta_de_saida).expanduser().resolve()}
                )
            }
        )

    sobrescrever = configuracao.simulacao.sobrescrever
    trajetorias_originais = simulation.simular(
        configuracao.modelos.original,
        configuracao.simulacao,
        mapping.nomes_simulados(configuracao.variaveis, "original"),
        sobrescrever.para("original"),
    )
    trajetorias_simplificadas = simulation.simular(
        configuracao.modelos.simplificado,
        configuracao.simulacao,
        mapping.nomes_simulados(configuracao.variaveis, "simplificado"),
        sobrescrever.para("simplificado"),
    )
    ruido = simulation.ruido_numerico(
        configuracao.modelos.original,
        configuracao.simulacao,
        configuracao.variaveis,
        trajetorias_originais,
        sobrescrever.para("original"),
    )

    series = mapping.mapear(
        configuracao.variaveis, trajetorias_originais, trajetorias_simplificadas
    )
    comparacao = _analisar_qualitativo(configuracao)
    veredito = verdict.avaliar(
        configuracao.criterios,
        series,
        core=configuracao.nomes_core(),
        niveis=configuracao.relatorio.niveis,
        comparacao=comparacao,
    )
    avisos = (ruido.resumo(), *simulation.avisos_de_ruido(ruido, configuracao))
    if comparacao is not None:
        avisos += qualitative.avisos(comparacao, configuracao.simulacao.t_fim)
    caminhos = report.salvar(
        veredito,
        configuracao,
        series,
        ruido=ruido,
        avisos=avisos,
        caminho_config=caminho_config,
        comparacao=comparacao,
    )

    return Resultado(
        configuracao=configuracao,
        veredito=veredito,
        caminhos=caminhos,
        ruido=ruido,
        avisos=avisos,
        series=series,
        comparacao=comparacao,
    )


def _analisar_qualitativo(
    configuracao: _config.Configuracao,
) -> qualitative.Comparacao | None:
    """Analyse both models qualitatively, and only when some criterion asks for it.

    Finding the equilibrium can mean integrating far past the declared horizon, so a
    configuration that does not declare a qualitative criterion does not pay for it. This
    is also the answer to "can I switch it off": declaring the criterion is switching it on.
    """
    pedidos = [
        criterio
        for criterio in configuracao.criterios
        if criterio.metrica in _config.ANALISES_QUALITATIVAS
    ]
    if not pedidos:
        return None
    sobrescrever = configuracao.simulacao.sobrescrever
    return qualitative.Comparacao(
        original=qualitative.analisar(
            configuracao.modelos.original,
            configuracao.simulacao,
            sobrescrever.para("original"),
            papel="original",
        ),
        simplificado=qualitative.analisar(
            configuracao.modelos.simplificado,
            configuracao.simulacao,
            sobrescrever.para("simplificado"),
            papel="simplificado",
        ),
    )
