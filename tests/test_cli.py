"""Tests of the command line, run the way a user runs it: a separate process.

The exit code is the contract here, so every case goes through subprocess instead of
calling main() in this interpreter: that is what a shell script or a Makefile will see.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest

import reducheck
from reducheck import cli

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: (configuration file, expected level, expected exit code), from fixtures/README.md.
PAIRS = [
    ("config_qssa_ok.yaml", "APROVADO", 0),
    ("config_qssa_fail.yaml", "REPROVADO", 2),
    ("config_aggregation.yaml", "APROVADO", 0),
]


def prepare(tmp_path: Path, config_name: str, formatos: str = "[json]") -> Path:
    """Copy one configuration and every fixture model into tmp_path, return the config.

    ``formatos`` is written over the ``relatorio`` section of the copy, never of the
    versioned fixture: the pipeline tests rely on those asking for json only.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    for path in [*FIXTURES_DIR.glob("*.xml"), FIXTURES_DIR / config_name]:
        shutil.copy(path, tmp_path / path.name)
    caminho = tmp_path / config_name
    texto = caminho.read_text(encoding="utf-8")
    caminho.write_text(f"{texto}\n  formatos: {formatos}\n", encoding="utf-8")
    return caminho


def run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    """Run the command line in a separate process, as a user would.

    PYTHONIOENCODING fixes the encoding of the pipe: without it the child writes in the
    locale encoding (cp1252 on Windows), which the accented Portuguese of the summary
    makes impossible to decode here as utf-8. It says nothing about the library: in a real
    terminal Python already writes in whatever the console understands.
    """
    return subprocess.run(
        [sys.executable, "-m", "reducheck", *[str(arg) for arg in args]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_the_command_is_installed_by_the_pyproject() -> None:
    scripts = entry_points(group="console_scripts")
    assert "reducheck" in scripts.names
    assert scripts["reducheck"].value == "reducheck.cli:main"


@pytest.mark.parametrize(("config_name", "nivel", "codigo"), PAIRS)
def test_exit_code_and_summary_follow_the_verdict(
    tmp_path: Path, config_name: str, nivel: str, codigo: int
) -> None:
    config = prepare(tmp_path, config_name)

    processo = run("verificar", config)

    assert processo.returncode == codigo
    assert nivel in processo.stdout
    # The verdict on the first line, plain text through a pipe, nothing on stderr.
    assert processo.stdout.splitlines()[0] == f"Veredito   {nivel}"
    assert "\033[" not in processo.stdout
    assert processo.stderr == ""


def test_it_writes_json_and_html_when_the_configuration_asks_for_both(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml", formatos="[html, json]")

    processo = run("verificar", config)

    assert processo.returncode == 0
    pasta = tmp_path / "resultados"
    assert (pasta / "resultado.json").is_file()
    assert (pasta / "relatorio.html").is_file()
    assert str(pasta / "relatorio.html") in processo.stdout


def test_saida_overrides_the_folder_of_the_configuration(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml", formatos="[html, json]")
    pasta = tmp_path / "outra"

    processo = run("verificar", config, "--saida", pasta)

    assert processo.returncode == 0
    assert (pasta / "resultado.json").is_file()
    assert (pasta / "relatorio.html").is_file()
    assert not (tmp_path / "resultados").exists()


def test_the_summary_says_the_percentage_and_the_mandatory_failures(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_fail.yaml")

    processo = run("verificar", config)

    assert processo.returncode == 2
    # One of the two items failed: A passes, C does not (fixtures/README.md).
    assert "50,0%" in processo.stdout
    assert "1 de 2" in processo.stdout
    assert "Falhas obrigatórias (1 de 2)" in processo.stdout
    assert any(
        linha.startswith("  × nrmse  C  52%  limite 5%") for linha in processo.stdout.splitlines()
    )


def test_a_verdict_with_a_reservation_exits_with_one(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_fail.yaml")
    # The failing criterion becomes desirable, so nothing mandatory fails and the level
    # drops to "com ressalvas" instead of "reprovado".
    texto = config.read_text(encoding="utf-8").replace(
        "variaveis: [A, C]", "variaveis: [A, C]\n    obrigatorio: false"
    )
    config.write_text(texto, encoding="utf-8")

    processo = run("verificar", config)

    assert processo.returncode == 1
    assert "APROVADO COM RESSALVAS" in processo.stdout


def test_a_configuration_error_exits_with_three_and_no_traceback(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace("simplificado: C", "simplificado: Z"),
        encoding="utf-8",
    )

    processo = run("verificar", config)

    assert processo.returncode == 3
    assert "Traceback" not in processo.stderr
    assert "Z" in processo.stderr
    assert processo.stdout == ""


def test_a_missing_configuration_file_exits_with_three(tmp_path: Path) -> None:
    processo = run("verificar", tmp_path / "nao_existe.yaml")

    assert processo.returncode == 3
    assert "nao_existe.yaml" in processo.stderr


def test_a_broken_simulation_exits_with_three(tmp_path: Path) -> None:
    # negativa.xml compared with itself: every error would be zero, but the trajectory
    # goes negative, so there is no verdict to report (fixtures/README.md).
    config = prepare(tmp_path, "config_negativa.yaml")

    processo = run("verificar", config)

    assert processo.returncode == 3
    assert "Traceback" not in processo.stderr
    assert "X" in processo.stderr


#: ``divergente`` blows up at t = 1. Up to t = 0.5 the simulation is fine, so the metrics
#: run; the equilibrium search integrates past the horizon and cannot find one.
SEM_EQUILIBRIO = """versao: 1
modelos:
  original: divergente.xml
  simplificado: divergente.xml
simulacao:
  t_inicio: 0
  t_fim: 0.5
  pontos: 51
variaveis:
  - nome: X
    original: X
    simplificado: X
criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: [X]
  - metrica: equilibrio
    limite: 0.05
    variaveis: [X]
relatorio:
  formatos: [json]
  pasta: resultados/
"""


def test_a_model_without_equilibrium_exits_with_three_and_no_traceback(
    tmp_path: Path,
) -> None:
    shutil.copy(FIXTURES_DIR / "divergente.xml", tmp_path / "divergente.xml")
    config = tmp_path / "config.yaml"
    config.write_text(SEM_EQUILIBRIO, encoding="utf-8")

    processo = run("verificar", config)

    assert processo.returncode == 3
    assert "Traceback" not in processo.stderr
    # libRoadRunner writes its own CVODE lines to stderr first; ours is the one that counts.
    linhas = [linha for linha in processo.stderr.splitlines() if linha.startswith("reducheck:")]
    assert len(linhas) == 1
    assert linhas[0].startswith("reducheck: erro: Análise qualitativa do modelo original")
    # CVODE's own warnings may land on stdout too; what must not be there is a verdict.
    assert "Veredito" not in processo.stdout


def test_equilibrio_on_an_assignment_rule_exits_with_three(tmp_path: Path) -> None:
    # B is an assignment rule in qssa_ok_simplified: there is no B in its equilibrium.
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    texto = config.read_text(encoding="utf-8")
    texto = texto.replace(
        "variaveis:\n  - nome: A",
        "variaveis:\n  - nome: B\n    original: B\n    simplificado: B\n  - nome: A",
    ).replace(
        "    variaveis: [A, C]\n",
        "    variaveis: [A, C]\n  - metrica: equilibrio\n    limite: 0.05\n    variaveis: [B]\n",
    )
    config.write_text(texto, encoding="utf-8")

    processo = run("verificar", config)

    assert processo.returncode == 3
    assert "Traceback" not in processo.stderr
    assert "KeyError" not in processo.stderr
    assert "variável de estado" in processo.stderr
    assert processo.stdout == ""


def test_help_is_in_portuguese(tmp_path: Path) -> None:
    geral = run("--help")
    do_subcomando = run("verificar", "--help")

    assert geral.returncode == 0
    assert do_subcomando.returncode == 0
    for texto in (geral.stdout, do_subcomando.stdout):
        assert "usage" not in texto.lower() or "uso:" in texto.lower()
    assert "verificar" in geral.stdout
    assert "--saida" in do_subcomando.stdout
    assert "--abrir" in do_subcomando.stdout
    assert "pasta" in do_subcomando.stdout.lower()


def test_no_subcommand_exits_with_three_and_explains(tmp_path: Path) -> None:
    processo = run()

    assert processo.returncode == 3
    assert "verificar" in processo.stderr


def test_the_json_written_by_the_command_matches_the_printed_summary(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_aggregation.yaml")

    processo = run("verificar", config)

    dados = json.loads((tmp_path / "resultados" / "resultado.json").read_text(encoding="utf-8"))
    assert dados["veredito"] in processo.stdout
    assert f"{dados['porcentagem']:.1f}".replace(".", ",") in processo.stdout


# --- --abrir and colours: in this interpreter, to replace the browser and the terminal --


def test_abrir_opens_the_html_report_in_the_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml", formatos="[html, json]")
    abertos: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: abertos.append(url) or True)

    codigo = cli.main(["verificar", str(config), "--abrir"])

    assert codigo == 0
    assert abertos == [(tmp_path / "resultados" / "relatorio.html").resolve().as_uri()]
    assert capsys.readouterr().err == ""


def test_abrir_without_html_warns_and_keeps_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = prepare(tmp_path, "config_qssa_fail.yaml")
    abertos: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: abertos.append(url) or True)

    codigo = cli.main(["verificar", str(config), "--abrir"])

    assert codigo == 2
    assert abertos == []
    assert "relatorio.formatos" in capsys.readouterr().err


def test_abrir_says_where_the_report_is_when_there_is_no_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml", formatos="[html]")
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: False)

    codigo = cli.main(["verificar", str(config), "--abrir"])

    assert codigo == 0
    assert "relatorio.html" in capsys.readouterr().err


def test_colours_change_only_the_escape_codes_not_the_text(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_fail.yaml")
    resultado = reducheck.verificar(config)

    simples = cli.resumo(resultado)
    colorido = cli.resumo(resultado, cor=True)

    assert not any("\033[" in linha for linha in simples)
    assert "\033[1;31mREPROVADO\033[0m" in colorido[0]
    assert [re.sub(r"\033\[[0-9;]*m", "", linha) for linha in colorido] == simples


def test_a_desirable_failure_gets_its_own_group(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_fail.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "variaveis: [A, C]", "variaveis: [A, C]\n    obrigatorio: false"
        ),
        encoding="utf-8",
    )

    linhas = cli.resumo(reducheck.verificar(config))

    assert "Desejáveis que falharam (1 de 2)" in linhas
    assert "Falhas obrigatórias" not in "\n".join(linhas)


class _Fluxo:
    def __init__(self, terminal: bool) -> None:
        self.terminal = terminal

    def isatty(self) -> bool:
        return self.terminal


def test_no_colour_outside_a_terminal_or_with_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli.usar_cor(_Fluxo(terminal=False)) is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.usar_cor(_Fluxo(terminal=True)) is False
