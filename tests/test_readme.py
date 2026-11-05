"""The README is executable documentation: these tests run what it tells people to run.

Issue #21: whoever reads only the README has to be able to verify a simplification, so the
five-minute example, the configuration reference and the "add a metric" recipe are checked
here against the code, and a change in either side breaks the build instead of the README.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter

import reducheck
from reducheck import cli, config, metrics

RAIZ = Path(__file__).resolve().parents[1]
README = RAIZ / "README.md"

#: NRMSE of X in the aggregation pair, as recorded in tests/fixtures/README.md.
NRMSE_DO_EXEMPLO = 0.00523


def texto() -> str:
    return README.read_text(encoding="utf-8")


def secao(titulo: str) -> str:
    """Return the body of the ``##`` section called ``titulo``, up to the next one."""
    partes = re.split(r"^## ", texto(), flags=re.MULTILINE)
    for parte in partes:
        if parte.startswith(titulo + "\n"):
            return parte
    raise AssertionError(f"O README não tem a seção '## {titulo}'.")


def blocos(trecho: str, linguagem: str) -> list[str]:
    return re.findall(rf"^```{linguagem}\n(.*?)^```", trecho, flags=re.MULTILINE | re.DOTALL)


# --- the five-minute example -------------------------------------------------


def test_the_yaml_in_the_quickstart_is_the_example_file() -> None:
    yaml_no_readme = blocos(secao("Exemplo de 5 minutos"), "yaml")[0]
    assert yaml_no_readme == (RAIZ / "exemplos" / "minimo.yaml").read_text(encoding="utf-8")


def test_the_quickstart_runs_and_prints_what_the_readme_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same command, from the root of the repository, with the output sent to tmp_path so the
    # test does not write into exemplos/. Every line the README shows has to be printed,
    # except the path of the report, which depends on the machine.
    codigo = roda_e_compara(
        secao("Exemplo de 5 minutos"),
        "reducheck verificar exemplos/minimo.yaml",
        ["verificar", "exemplos/minimo.yaml"],
        tmp_path,
        capsys,
        monkeypatch,
    )
    assert codigo == 0

    for arquivo in (
        "relatorio.html",
        "resultado.json",
        "series.csv",
        "config_usada.yaml",
        "graficos/X.png",
    ):
        assert (tmp_path / arquivo).is_file(), arquivo

    resultado = json.loads((tmp_path / "resultado.json").read_text(encoding="utf-8"))
    assert resultado["veredito"] == "APROVADO"
    assert resultado["criterios"][0]["valor"] == pytest.approx(NRMSE_DO_EXEMPLO, abs=1e-5)


def test_the_value_quoted_in_the_readme_is_the_measured_one() -> None:
    assert "0,00523" in secao("Exemplo de 5 minutos")


def test_the_python_usage_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (codigo,) = blocos(secao("Exemplo de 5 minutos"), "python")
    monkeypatch.setattr(
        reducheck,
        "verificar",
        functools.partial(reducheck.verificar, pasta_de_saida=tmp_path),
    )
    monkeypatch.chdir(RAIZ)
    espaco: dict[str, object] = {}
    exec(compile(codigo, "README.md", "exec"), espaco)

    resultado = espaco["resultado"]
    assert isinstance(resultado, reducheck.Resultado)
    assert resultado.nivel == "APROVADO"
    assert resultado.porcentagem == 100.0
    assert "X" in resultado.series


# --- reading the report ------------------------------------------------------


def roda_e_compara(
    trecho: str,
    comando: str,
    argv: list[str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    """Run ``argv`` like the README says and check every line it shows is printed."""
    assert comando in trecho
    monkeypatch.chdir(RAIZ)
    codigo = cli.main([*argv, "--saida", str(tmp_path)])
    impresso = capsys.readouterr().out.splitlines()
    (mostrado,) = [bloco for bloco in blocos(trecho, "text") if bloco.startswith("Veredito")]
    for linha in filter(None, mostrado.splitlines()):
        if linha.startswith("Relatório "):
            assert any(saida.startswith("Relatório ") for saida in impresso)
        else:
            assert linha in impresso
    return codigo


def test_the_rejected_example_prints_what_the_readme_shows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    codigo = roda_e_compara(
        secao("Como ler o relatório"),
        "reducheck verificar tests/fixtures/config_qssa_fail.yaml",
        ["verificar", "tests/fixtures/config_qssa_fail.yaml"],
        tmp_path,
        capsys,
        monkeypatch,
    )
    assert codigo == 2


def test_the_exit_codes_in_the_readme_are_the_ones_of_the_cli() -> None:
    trecho = secao("Como ler o relatório")
    for nivel, codigo in cli.CODIGOS.items():
        assert f"| {codigo} | {nivel} |" in trecho
    assert f"| {cli.CODIGO_DE_ERRO} | erro" in trecho


# --- configuration reference -------------------------------------------------


MARCA_INICIO = "<!-- referencia:inicio -->"
MARCA_FIM = "<!-- referencia:fim -->"


def test_the_configuration_reference_is_generated_from_the_schema() -> None:
    conteudo = texto()
    inicio = conteudo.index(MARCA_INICIO) + len(MARCA_INICIO)
    fim = conteudo.index(MARCA_FIM)
    no_readme = conteudo[inicio:fim].strip()
    assert no_readme == config.referencia_dos_campos().strip(), (
        "A tabela de referência do README está desatualizada. Rode "
        "'python docs/atualizar_referencia.py' e confira o diff."
    )


def test_every_field_of_the_schema_is_in_the_reference() -> None:
    tabela = config.referencia_dos_campos()
    for campo in (
        "versao",
        "modelos.original",
        "simulacao.t_fim",
        "simulacao.sobrescrever.original.condicoes_iniciais",
        "variaveis[].original",
        "criterios[].parametros",
        "relatorio.niveis",
    ):
        assert f"| `{campo}` |" in tabela, campo


def test_every_example_in_the_reference_is_accepted_by_its_field() -> None:
    for caminho, campo in config.campos_do_esquema():
        for exemplo in campo.examples or []:
            valor = yaml.safe_load(exemplo)
            TypeAdapter(campo.annotation).validate_python(valor)  # raises if not accepted
        assert campo.description, f"{caminho} não tem descrição."


# --- metrics and criteria ----------------------------------------------------


def test_every_metric_and_qualitative_analysis_is_documented() -> None:
    trecho = secao("Métricas e critérios")
    # Only the ones the library ships: other test files register metrics of their own.
    da_biblioteca = {
        nome
        for nome in metrics.disponiveis()
        if metrics.obter(nome).__module__ == metrics.__name__
    }
    assert len(da_biblioteca) == 9
    for nome in da_biblioteca | config.ANALISES_QUALITATIVAS:
        assert f"### `{nome}`" in trecho, nome


# --- adding a metric ---------------------------------------------------------


def test_the_add_a_metric_example_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trecho = secao("Como adicionar uma métrica")
    (codigo,) = blocos(trecho, "python")
    yaml_no_readme = blocos(trecho, "yaml")[0]
    arquivo = RAIZ / "exemplos" / "metrica_propria.yaml"
    assert yaml_no_readme.strip() in arquivo.read_text(encoding="utf-8")

    # A copy of the registry, so the metric registered by the README does not leak into
    # the other tests, and the run sent to tmp_path instead of exemplos/resultados.
    monkeypatch.setattr(metrics, "_REGISTRO", dict(metrics._REGISTRO))
    monkeypatch.setattr(
        reducheck,
        "verificar",
        functools.partial(reducheck.verificar, pasta_de_saida=tmp_path),
    )
    monkeypatch.chdir(RAIZ)
    espaco: dict[str, object] = {}
    exec(compile(codigo, "README.md", "exec"), espaco)

    resultado = espaco["resultado"]
    assert isinstance(resultado, reducheck.Resultado)
    assert "erro_medio_abs" in metrics.disponiveis()
    item = next(c for c in resultado.criterios if c.metrica == "erro_medio_abs")
    assert item.passou is True
    assert item.valor == pytest.approx(0.0241, abs=1e-4)  # quoted in the README
    assert "0,0241" in trecho
    assert resultado.nivel == "APROVADO"


def test_the_command_line_does_not_load_a_metric_of_your_own(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The limitation stated in the README: without the Python code that registers it, the
    # YAML cites a name the registry does not have.
    assert "erro_medio_abs" not in metrics.disponiveis()
    monkeypatch.chdir(RAIZ)
    assert cli.main(["verificar", "exemplos/metrica_propria.yaml"]) == cli.CODIGO_DE_ERRO
    assert "a métrica 'erro_medio_abs' não está no registro" in capsys.readouterr().err
