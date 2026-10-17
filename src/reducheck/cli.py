"""Command line entry point for the library.

One command, ``reducheck verificar config.yaml``, so that whoever does not write Python can
still run a verification. The exit code is part of the interface, because the point of a
command line here is being usable from a script:

=====  ==========================================
  0    APROVADO
  1    APROVADO COM RESSALVAS
  2    REPROVADO
  3    error: configuration, mapping, metric or simulation
=====  ==========================================

An error is never a verdict (``docs/produto.md``: "nenhum desses casos gera veredito"), so
code 3 is reported with the message on stderr and nothing on stdout. Argparse's own usage
errors also exit with 3, and not with its default of 2, which would read as REPROVADO.

The texts are in Portuguese, like the report and the error messages; the identifiers are in
English, as in the rest of the library.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import reducheck
from reducheck import report
from reducheck.config import ErroDeConfiguracao
from reducheck.mapping import ErroDeMapeamento
from reducheck.metrics import ErroDeMetrica
from reducheck.simulation import ErroDeSimulacao
from reducheck.verdict import APROVADO, COM_RESSALVAS, REPROVADO

__all__ = ["CODIGOS", "CODIGO_DE_ERRO", "main"]

#: Exit code of each verdict level.
CODIGOS = {APROVADO: 0, COM_RESSALVAS: 1, REPROVADO: 2}

#: Exit code of anything that stopped the run before a verdict existed.
CODIGO_DE_ERRO = 3

#: The errors the library raises on purpose, all of them meaning "no verdict".
_ERROS = (ErroDeConfiguracao, ErroDeMapeamento, ErroDeMetrica, ErroDeSimulacao)

#: How many failed mandatory items the summary lists before it stops, to keep the summary
#: short; the report has all of them.
_MAXIMO_DE_RAZOES = 3


class _Analisador(argparse.ArgumentParser):
    """An argparse parser that speaks Portuguese and fails with :data:`CODIGO_DE_ERRO`."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.exit(CODIGO_DE_ERRO, f"{self.prog}: erro: {message}\n")


class _Ajuda(argparse.HelpFormatter):
    """Help formatter with the usage prefix in Portuguese."""

    def add_usage(
        self,
        usage: str | None,
        actions: object,
        groups: object,
        prefix: str | None = None,
    ) -> None:
        super().add_usage(usage, actions, groups, prefix="uso: ")  # type: ignore[arg-type]


def construir_analisador() -> argparse.ArgumentParser:
    """Return the parser of the command line, with every text in Portuguese."""
    analisador = _Analisador(
        prog="reducheck",
        description=(
            "Verifica se um modelo de EDOs simplificado é fiel ao original, "
            "a partir de um arquivo de configuração em YAML."
        ),
        formatter_class=_Ajuda,
        add_help=False,
    )
    analisador.add_argument(
        "-h", "--help", action="help", help="mostra esta ajuda e sai."
    )
    analisador.add_argument(
        "-V",
        "--versao",
        action="version",
        version=f"reducheck {reducheck.__version__}",
        help="mostra a versão e sai.",
    )
    analisador._positionals.title = "comandos"
    analisador._optionals.title = "opções"

    subcomandos = analisador.add_subparsers(dest="comando", metavar="comando")
    verificar = subcomandos.add_parser(
        "verificar",
        help="roda a verificação descrita por uma configuração e gera o relatório.",
        description=(
            "Simula os dois modelos nas mesmas condições, mede os critérios da "
            "configuração, decide o veredito e escreve o relatório. Código de saída: "
            "0 aprovado, 1 aprovado com ressalvas, 2 reprovado, 3 erro."
        ),
        formatter_class=_Ajuda,
        add_help=False,
    )
    verificar.add_argument(
        "-h", "--help", action="help", help="mostra esta ajuda e sai."
    )
    verificar._positionals.title = "argumentos"
    verificar._optionals.title = "opções"
    verificar.add_argument(
        "configuracao",
        type=Path,
        metavar="config.yaml",
        help="caminho do arquivo YAML de configuração.",
    )
    verificar.add_argument(
        "--saida",
        type=Path,
        metavar="pasta",
        default=None,
        help=(
            "pasta onde escrever os resultados, no lugar da pasta declarada em "
            "'relatorio.pasta' na configuração."
        ),
    )
    return analisador


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the exit code, without raising on expected errors."""
    analisador = construir_analisador()
    argumentos = analisador.parse_args(argv)

    if argumentos.comando is None:
        analisador.error("falta o comando. O único comando hoje é 'verificar'.")
        return CODIGO_DE_ERRO  # pragma: no cover - error() already exited.

    try:
        resultado = reducheck.verificar(argumentos.configuracao, pasta_de_saida=argumentos.saida)
    except _ERROS as erro:
        print(f"reducheck: erro: {erro}", file=sys.stderr)
        return CODIGO_DE_ERRO

    print("\n".join(resumo(resultado)))
    return CODIGOS[resultado.nivel]


def resumo(resultado: reducheck.Resultado) -> list[str]:
    """Return the three to five lines printed in the terminal.

    Enough to decide without opening the report: the verdict, how much passed, which
    mandatory items failed and where the report went.
    """
    obrigatorios = resultado.veredito.obrigatorios
    desejaveis = resultado.veredito.desejaveis
    passados = sum(1 for item in resultado.criterios if item.passou)
    porcentagem = f"{resultado.porcentagem:.1f}".replace(".", ",")

    linhas = [
        f"Veredito: {resultado.nivel}",
        (
            f"Critérios atendidos: {passados} de {len(resultado.criterios)} ({porcentagem}%) "
            f"— obrigatórios {obrigatorios.passados}/{obrigatorios.total}, "
            f"desejáveis {desejaveis.passados}/{desejaveis.total}"
        ),
        _linha_das_falhas(resultado),
    ]
    caminho = resultado.caminho_relatorio or resultado.caminho_json
    if caminho is not None:
        linhas.append(f"Relatório: {caminho}")
    if len(resultado.avisos) > 0:
        linhas.append(f"Avisos: {len(resultado.avisos)} (no relatório)")
    return linhas


def _linha_das_falhas(resultado: reducheck.Resultado) -> str:
    """Return the line about the mandatory failures, which are what rejects the model."""
    falhas = [
        item for item in resultado.criterios if not item.passou and item.obrigatorio
    ]
    if not falhas:
        desejaveis = [
            item for item in resultado.criterios if not item.passou and not item.obrigatorio
        ]
        if desejaveis:
            nomes = ", ".join(f"{item.metrica} em {item.variavel}" for item in desejaveis)
            return f"Falhas obrigatórias: nenhuma. Desejáveis que falharam: {nomes}."
        return "Falhas obrigatórias: nenhuma."

    das_obrigatorias = [razao for item in falhas if (razao := report.razao(item))]
    mostradas = das_obrigatorias[:_MAXIMO_DE_RAZOES]
    restantes = len(das_obrigatorias) - len(mostradas)
    texto = " ".join(mostradas)
    if restantes > 0:
        texto += f" (e mais {restantes} no relatório)"
    total = resultado.veredito.obrigatorios.total
    return f"Falhas obrigatórias ({len(falhas)} de {total}): {texto}"


if __name__ == "__main__":  # pragma: no cover - exercised by tests through subprocess.
    raise SystemExit(main())
