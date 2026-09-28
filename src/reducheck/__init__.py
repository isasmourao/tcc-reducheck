"""ReduCheck: verify whether a simplified ODE model is faithful to the original one.

The whole library is used through :func:`verificar`, which runs the pipeline described in
``docs/produto.md``: read the configuration, simulate both models under identical conditions,
map the variables, measure the metrics, decide the verdict and write the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reducheck import config as _config
from reducheck import mapping, report, simulation, verdict
from reducheck.simulation import RuidoNumerico
from reducheck.verdict import ItemAvaliado, Veredito

__all__ = ["Resultado", "RuidoNumerico", "__version__", "verificar"]

__version__ = "0.1.0.dev0"


@dataclass(frozen=True)
class Resultado:
    """What a verification produced: the verdict plus where it was written."""

    configuracao: _config.Configuracao
    veredito: Veredito
    caminho_json: Path
    #: The floor of the comparison, measured by simulating the original twice.
    ruido: RuidoNumerico
    #: Warnings that are not about a single metric: the noise itself and every threshold
    #: too close to it.
    avisos: tuple[str, ...] = ()

    @property
    def aprovado(self) -> bool:
        """Whether every criterion passed."""
        return self.veredito.aprovado

    @property
    def porcentagem(self) -> float:
        """Percentage of (criterion, variable) items that passed."""
        return self.veredito.porcentagem

    @property
    def criterios(self) -> tuple[ItemAvaliado, ...]:
        """Every evaluated (criterion, variable) item."""
        return self.veredito.criterios


def verificar(caminho_config: Path | str) -> Resultado:
    """Run the whole verification described by the YAML at ``caminho_config``."""
    configuracao = _config.carregar(caminho_config)

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
    veredito = verdict.avaliar(
        configuracao.criterios, series, core=configuracao.nomes_core()
    )
    avisos = (ruido.resumo(), *simulation.avisos_de_ruido(ruido, configuracao))
    caminho_json = report.salvar_json(
        veredito, configuracao.relatorio.pasta, ruido=ruido, avisos=avisos
    )

    return Resultado(
        configuracao=configuracao,
        veredito=veredito,
        caminho_json=caminho_json,
        ruido=ruido,
        avisos=avisos,
    )
