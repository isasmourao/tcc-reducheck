"""Command line entry point for the library.

One command, ``reducheck verificar config.yaml``, so that whoever does not write Python can
still run a verification. The exit code is part of the interface, because the point of a
command line here is being usable from a script:

=====  ==========================================
  0    APROVADO
  1    APROVADO COM RESSALVAS
  2    REPROVADO
  3    error: configuration, mapping, metric, simulation or qualitative analysis
=====  ==========================================

An error is never a verdict (``docs/produto.md``: "nenhum desses casos gera veredito"), so
code 3 is reported with the message on stderr and nothing on stdout. Argparse's own usage
errors also exit with 3, and not with its default of 2, which would read as REPROVADO.

The summary is a short block: the verdict, the counts, one line per failed item (a few of
them; the report has all), the report path and the number of warnings. It is coloured only
when stdout is a real terminal and ``NO_COLOR`` is not set, so a pipe, a file or a script
always gets plain text. ``--abrir`` opens the HTML report in the default browser after it is
written; it never changes the exit code.

The texts are in Portuguese, like the report and the error messages; the identifiers are in
English, as in the rest of the library.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

import reducheck
from reducheck import report
from reducheck.config import ErroDeConfiguracao
from reducheck.mapping import ErroDeMapeamento
from reducheck.metrics import ErroDeMetrica
from reducheck.qualitative import ErroDeQualitativo
from reducheck.simulation import ErroDeSimulacao
from reducheck.verdict import APROVADO, COM_RESSALVAS, PERGUNTAS, REPROVADO, ItemAvaliado

__all__ = ["CODIGOS", "CODIGO_DE_ERRO", "main", "resumo", "usar_cor"]

#: Exit code of each verdict level.
CODIGOS = {APROVADO: 0, COM_RESSALVAS: 1, REPROVADO: 2}

#: Exit code of anything that stopped the run before a verdict existed.
CODIGO_DE_ERRO = 3

#: The errors the library raises on purpose, all of them meaning "no verdict".
_ERROS = (
    ErroDeConfiguracao,
    ErroDeMapeamento,
    ErroDeMetrica,
    ErroDeQualitativo,
    ErroDeSimulacao,
)

#: How many failed items of each kind the summary lists before it stops, to keep the
#: summary short; the report has all of them.
_MAXIMO_DE_RAZOES = 3

#: Width of the label column of the summary ("Relatório", "Avisos", ...).
_ROTULO = 11

#: ANSI escape codes. Only the 16 basic colours, which every terminal that understands
#: escape codes at all also understands, including the Windows 10 console.
_CORES = {
    "negrito": "1",
    "cinza": "90",
    "vermelho": "1;31",
    "verde": "1;32",
    "amarelo": "1;33",
    "ciano": "36",
}

#: Colour of each verdict level.
_COR_DO_NIVEL = {APROVADO: "verde", COM_RESSALVAS: "amarelo", REPROVADO: "vermelho"}


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
    verificar.add_argument(
        "--abrir",
        action="store_true",
        help=(
            "abre o relatorio.html no navegador quando a verificação termina. Exige 'html' "
            "em 'relatorio.formatos'; não muda o código de saída."
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

    print("\n".join(resumo(resultado, cor=usar_cor(sys.stdout))))
    if argumentos.abrir:
        _abrir(resultado)
    return CODIGOS[resultado.nivel]


def _abrir(resultado: reducheck.Resultado) -> None:
    """Open the HTML report in the default browser, or say on stderr why it was not opened.

    A warning and not an error: the verification itself worked and its exit code already
    says the verdict, which a missing browser must not change.
    """
    caminho = resultado.caminhos.get("html")
    if caminho is None:
        print(
            "reducheck: aviso: --abrir não abriu nada, porque a configuração não pede o "
            "relatório HTML. Acrescente 'html' em 'relatorio.formatos'.",
            file=sys.stderr,
        )
        return
    if not webbrowser.open(Path(caminho).resolve().as_uri()):
        print(
            f"reducheck: aviso: não foi possível abrir o navegador. Abra o relatório "
            f"manualmente: {caminho}",
            file=sys.stderr,
        )


# --- the summary --------------------------------------------------------------


def usar_cor(fluxo: TextIO) -> bool:
    """Whether the summary written to ``fluxo`` should carry colours.

    Only on a real terminal, and never when ``NO_COLOR`` is set (https://no-color.org), so
    a pipe, a redirected file or a test always gets plain text. On Windows the console has
    to be switched into the mode that understands escape codes; if that fails, no colour.
    """
    if os.environ.get("NO_COLOR"):
        return False
    try:
        if not fluxo.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if os.name == "nt":
        return _ativar_cores_no_windows()
    return os.environ.get("TERM") != "dumb"


def _ativar_cores_no_windows() -> bool:  # pragma: no cover - depends on the console.
    """Turn on ``ENABLE_VIRTUAL_TERMINAL_PROCESSING`` for stdout, and say if it worked."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        saida = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        modo = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(saida, ctypes.byref(modo)):
            return False
        return bool(kernel32.SetConsoleMode(saida, modo.value | 0x0004))
    except (AttributeError, OSError):
        return False


def resumo(resultado: reducheck.Resultado, cor: bool = False) -> list[str]:
    """Return the lines printed in the terminal.

    Enough to decide without opening the report: the verdict, how much passed, which items
    failed and by how much, and where the report went. ``cor`` adds ANSI colours; the text
    is the same with or without them.
    """

    def pintar(texto: str, estilo: str) -> str:
        if not cor:
            return texto
        return f"\033[{_CORES[estilo]}m{texto}\033[0m"

    def rotulo(texto: str) -> str:
        return pintar(texto.ljust(_ROTULO), "cinza")

    obrigatorios = resultado.veredito.obrigatorios
    desejaveis = resultado.veredito.desejaveis
    passados = sum(1 for item in resultado.criterios if item.passou)
    porcentagem = f"{resultado.porcentagem:.1f}".replace(".", ",")

    linhas = [
        rotulo("Veredito") + pintar(resultado.nivel, _COR_DO_NIVEL[resultado.nivel]),
        rotulo("Critérios")
        + f"{passados} de {len(resultado.criterios)} atendidos ({porcentagem}%) · "
        f"obrigatórios {obrigatorios.passados}/{obrigatorios.total} · "
        f"desejáveis {desejaveis.passados}/{desejaveis.total}",
    ]
    # The two questions apart, so that a run is never read as one answer when it is two
    # (and so that a question nobody declared shows up as such).
    for pergunta, titulo in PERGUNTAS.items():
        parte = resultado.veredito.parte(pergunta)
        rotulo_da_parte = "  " + titulo.ljust(_ROTULO + 2)
        if not parte.criterios:
            linhas.append(pintar(rotulo_da_parte + "não verificada", "cinza"))
            continue
        passados_da_parte = sum(1 for item in parte.criterios if item.passou)
        linhas.append(
            pintar(rotulo_da_parte, "cinza")
            + pintar(parte.nivel, _COR_DO_NIVEL[parte.nivel])
            + f" · {passados_da_parte} de {len(parte.criterios)} · "
            f"obrigatórios {parte.obrigatorios.passados}/{parte.obrigatorios.total}"
        )

    grupos = [
        ("Falhas obrigatórias", True, obrigatorios.total, "vermelho"),
        ("Desejáveis que falharam", False, desejaveis.total, "amarelo"),
    ]
    houve_falha = False
    for titulo, obrigatorio, total, estilo in grupos:
        falhas = [
            item
            for item in resultado.criterios
            if not item.passou and item.obrigatorio is obrigatorio
        ]
        if not falhas:
            continue
        houve_falha = True
        linhas += ["", pintar(f"{titulo} ({len(falhas)} de {total})", "negrito")]
        linhas += _tabela_de_falhas(falhas[:_MAXIMO_DE_RAZOES], pintar, estilo)
        restantes = len(falhas) - _MAXIMO_DE_RAZOES
        if restantes > 0:
            linhas.append(pintar(f"  … e mais {restantes} no relatório", "cinza"))
    if not houve_falha:
        linhas.append(rotulo("Falhas") + "nenhuma")

    linhas.append("")
    caminho = resultado.caminho_relatorio or resultado.caminho_json
    if caminho is not None:
        linhas.append(rotulo("Relatório") + pintar(str(caminho), "ciano"))
    if len(resultado.avisos) > 0:
        linhas.append(rotulo("Avisos") + f"{len(resultado.avisos)} (no relatório)")
    return linhas


def _tabela_de_falhas(
    itens: Sequence[ItemAvaliado], pintar: Callable[[str, str], str], estilo: str
) -> list[str]:
    """Return one aligned line per failed item: metric, variable, value, limit, window."""
    colunas = [_colunas_da_falha(item) for item in itens]
    larguras = [max(len(linha[i]) for linha in colunas) for i in range(4)]
    linhas = []
    for metrica, variavel, valor, limite, janela in colunas:
        texto = "  ".join(
            celula.ljust(largura)
            for celula, largura in zip(
                (metrica, variavel, valor, limite), larguras, strict=True
            )
        )
        if janela:
            texto += "  " + pintar(janela, "cinza")
        linhas.append(("  " + pintar("×", estilo) + " " + texto).rstrip())
    return linhas


def _colunas_da_falha(item: ItemAvaliado) -> tuple[str, str, str, str, str]:
    """Return the cells of one failed item, already formatted the way the report does."""
    if item.valor is None:
        # A qualitative item compares two labels; the value cell carries both.
        return item.metrica, item.variavel, item.valor_texto, f"limite {item.limite_texto}", ""

    def formatar(valor: float | None) -> str:
        return report._porcento(valor) if item.fracao else report._numero(valor)

    janela = ""
    if item.diagnostico is not None:
        janela = (
            f"erro em t = {report._numero(item.diagnostico.inicio)} a "
            f"{report._numero(item.diagnostico.fim)} ({item.diagnostico.fase})"
        )
    return (
        item.metrica,
        item.variavel,
        formatar(item.valor),
        f"limite {formatar(item.limite)}",
        janela,
    )


if __name__ == "__main__":  # pragma: no cover - exercised by tests through subprocess.
    raise SystemExit(main())
