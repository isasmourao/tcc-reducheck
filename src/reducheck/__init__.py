"""ReduCheck: verify whether a simplified ODE model is faithful to the original one.

The whole library is used through :func:`verificar`, which runs the pipeline described in
``docs/produto.md``: read the configuration, simulate both models under identical conditions,
map the variables, measure the metrics, decide the verdict and write the report.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from reducheck import config as _config
from reducheck import mapping, report, simulation, verdict
from reducheck.verdict import ItemAvaliado, Veredito

__all__ = ["Resultado", "__version__", "verificar"]

__version__ = "0.1.0.dev0"


@dataclass(frozen=True)
class Resultado:
    """What a verification produced: the verdict plus where it was written."""

    configuracao: _config.Configuracao
    veredito: Veredito
    caminho_json: Path

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


def _sem_repetir(nomes: Iterable[str]) -> list[str]:
    """Return ``nomes`` without repetitions, in order.

    Two declared variables may read the same variable of a model; it is simulated once.
    """
    return list(dict.fromkeys(nomes))


def verificar(caminho_config: Path | str) -> Resultado:
    """Run the whole verification described by the YAML at ``caminho_config``."""
    configuracao = _config.carregar(caminho_config)

    trajetorias_originais = simulation.simular(
        configuracao.modelos.original,
        configuracao.simulacao,
        _sem_repetir(variavel.original for variavel in configuracao.variaveis),
    )
    trajetorias_simplificadas = simulation.simular(
        configuracao.modelos.simplificado,
        configuracao.simulacao,
        _sem_repetir(variavel.simplificado for variavel in configuracao.variaveis),
    )

    series = mapping.mapear(
        configuracao.variaveis, trajetorias_originais, trajetorias_simplificadas
    )
    veredito = verdict.avaliar(configuracao.criterios, series)
    caminho_json = report.salvar_json(veredito, configuracao.relatorio.pasta)

    return Resultado(
        configuracao=configuracao, veredito=veredito, caminho_json=caminho_json
    )
