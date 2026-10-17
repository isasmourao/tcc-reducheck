"""The readable report: HTML, Markdown and the plots (issue #14)."""

from __future__ import annotations

import base64
import re
import struct
from pathlib import Path

import pytest
from test_pipeline import prepare

import reducheck
from reducheck import plots, report


def com_formatos(config: Path, formatos: str) -> Path:
    """Rewrite the ``relatorio`` block of ``config`` to ask for ``formatos``."""
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "relatorio:\n  pasta: resultados/",
            f"relatorio:\n  pasta: resultados/\n  formatos: {formatos}",
        ),
        encoding="utf-8",
    )
    return config


def rodar(tmp_path: Path, config_name: str, formatos: str = "[html, json]"):
    """Run the whole pipeline on one fixture pair, asking for ``formatos``."""
    return reducheck.verificar(com_formatos(prepare(tmp_path, config_name), formatos))


# --- which files come out -----------------------------------------------------


def test_the_requested_formats_are_the_files_that_appear(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html, md, json]")

    pasta = tmp_path / "resultados"
    assert set(resultado.caminhos) == {"html", "md", "json"}
    assert resultado.caminhos["html"] == pasta / "relatorio.html"
    assert resultado.caminhos["md"] == pasta / "relatorio.md"
    assert resultado.caminho_json == pasta / "resultado.json"
    assert all(caminho.is_file() for caminho in resultado.caminhos.values())


def test_asking_for_markdown_alone_writes_no_html(tmp_path: Path) -> None:
    # The "opção de gerar Markdown em vez de HTML" of the issue: instead of, not besides.
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[md]")

    assert set(resultado.caminhos) == {"md"}
    assert not (tmp_path / "resultados" / "relatorio.html").exists()
    assert resultado.caminho_json is None
    assert resultado.caminho_relatorio == tmp_path / "resultados" / "relatorio.md"


def test_the_json_alone_draws_nothing(tmp_path: Path) -> None:
    # Drawing costs seconds; a run that asked only for the machine-readable result
    # must not pay for plots nobody will look at.
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))

    assert set(resultado.caminhos) == {"json"}
    assert not (tmp_path / "resultados" / plots.PASTA_DOS_GRAFICOS).exists()


def test_an_unknown_format_stops_before_simulating(tmp_path: Path) -> None:
    config = com_formatos(prepare(tmp_path, "config_qssa_ok.yaml"), "[pdf]")

    with pytest.raises(reducheck.config.ErroDeConfiguracao) as erro:
        reducheck.verificar(config)

    assert "relatorio.formatos" in str(erro.value)
    assert "html" in str(erro.value)  # the message lists what does exist


# --- the top of the report ----------------------------------------------------


def test_the_top_carries_the_verdict_and_the_counts(tmp_path: Path) -> None:
    # Same run as test_only_a_desirable_criterion_failing_gives_reservations, so the
    # numbers on the page are the ones tests/fixtures/README.md records.
    from test_pipeline import DESEJAVEL_QUE_FALHA, com_criterio_extra

    config = com_criterio_extra(prepare(tmp_path, "config_qssa_ok.yaml"), DESEJAVEL_QUE_FALHA)
    resultado = reducheck.verificar(com_formatos(config, "[html]"))
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert resultado.nivel == "APROVADO COM RESSALVAS"
    assert "APROVADO COM RESSALVAS" in html
    assert "Critérios atendidos: <strong>2 de 3 (66,7%)</strong>" in html
    assert "Obrigatórios: <strong>2 de 2</strong>" in html
    assert "Desejáveis: <strong>0 de 1</strong>" in html
    # The title says which pair was compared, by the file names of the two models.
    assert "Verificação: qssa_ok_simplified vs. qssa_ok_original" in html


def test_the_table_has_one_row_per_item_with_the_six_columns(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    for coluna in ("Critério", "Variável", "Valor", "Limite", "Tipo", "Resultado"):
        assert f"<th>{coluna}</th>" in html
    linhas = re.findall(r'<tr class="(passou|falhou)">', html)
    assert len(linhas) == len(resultado.criterios) == 2
    # The value cells carry the measured numbers, with a decimal comma and five
    # significant digits (0,00071704 for the NRMSE of C, which tests/fixtures/README.md
    # records rounded as 0,00072). Read back here instead of pinned digit by digit: the
    # last digits are solver noise, and the recorded value is what has to match.
    valores = [
        float(cela.replace(",", "."))
        for cela in re.findall(r'<td class="numero">([^<]+)</td>', html)
    ]
    assert valores[1] == valores[3] == 0.05  # the two limits
    assert valores[2] == pytest.approx(0.00072, abs=1e-5)
    assert "e-" in html  # the noise-level value of A is printed in scientific notation
    assert "<td>obrigatório</td>" in html


def test_the_failures_come_first_in_the_table(tmp_path: Path) -> None:
    # qssa_fail fails in C and passes in A, and C is declared after A: if the table kept
    # the declaration order, the failure would be the second row.
    resultado = rodar(tmp_path, "config_qssa_fail.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert [c.variavel for c in resultado.criterios] == ["A", "C"]
    assert re.findall(r'<tr class="(passou|falhou)">', html) == ["falhou", "passou"]


def test_every_failure_has_a_reason_next_to_it(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_fail.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    linhas = report.razoes(resultado.veredito)
    assert len(linhas) == 1
    # Value, threshold and relative excess first; where in time the error is after (T15).
    assert linhas[0].startswith("nrmse em C falhou: 52% (limite 5%, 940% acima do limite)")
    assert "erro concentrado entre t = " in linhas[0]
    assert linhas[0] in html


def test_an_approved_run_says_so_in_the_reasons_section(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html]")

    assert report.razoes(resultado.veredito) == []
    assert "Nenhum critério falhou." in resultado.caminhos["html"].read_text(encoding="utf-8")


def test_two_levels_explain_an_approval_with_a_percentage_below_a_hundred(
    tmp_path: Path,
) -> None:
    # Question 26 of docs/questoes-em-aberto.md asks for this sentence: with niveis: 2 the
    # report shows APROVADO next to 66,7%, which reads as a contradiction without it.
    from test_pipeline import DESEJAVEL_QUE_FALHA, com_criterio_extra

    config = com_criterio_extra(prepare(tmp_path, "config_qssa_ok.yaml"), DESEJAVEL_QUE_FALHA)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "relatorio:\n  pasta: resultados/", "relatorio:\n  pasta: resultados/\n  niveis: 2"
        ),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(com_formatos(config, "[html, md]"))

    assert resultado.nivel == "APROVADO"
    esperado = (
        "Veredito em dois níveis (relatorio.niveis: 2): 1 item desejável ficou fora do "
        "limite e não impede a aprovação, mas continua contando na porcentagem."
    )
    for caminho in resultado.caminhos.values():
        assert esperado in caminho.read_text(encoding="utf-8")


def test_three_levels_do_not_carry_the_two_level_sentence(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_fail.yaml", "[html]")

    assert "dois níveis" not in resultado.caminhos["html"].read_text(encoding="utf-8")


def test_the_warnings_of_the_run_reach_the_report(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert resultado.avisos[0].startswith("Ruído numérico de referência")
    assert resultado.avisos[0] in html


def test_the_run_data_lets_the_reader_reproduce_the_numbers(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert "qssa_ok_original.xml" in html and "qssa_ok_simplified.xml" in html
    assert "t de 0 a 40 em 401 pontos, solver cvode" in html
    assert "tolerâncias 1e-08 (relativa) e 1e-10 (absoluta)" in html
    assert f"reducheck {reducheck.__version__}" in html
    assert "config_qssa_ok.yaml" in html


# --- the plots ----------------------------------------------------------------


def dimensoes_e_dpi(png: Path) -> tuple[int, int, float]:
    """Read width, height and horizontal dpi out of the PNG header itself."""
    dados = png.read_bytes()
    largura, altura = struct.unpack(">II", dados[16:24])
    inicio = dados.index(b"pHYs")
    pixels_por_metro = struct.unpack(">I", dados[inicio + 4 : inicio + 8])[0]
    return largura, altura, pixels_por_metro * 0.0254


def test_one_png_per_mapped_variable_at_300_dpi(tmp_path: Path) -> None:
    rodar(tmp_path, "config_qssa_ok.yaml", "[html]")

    pasta = tmp_path / "resultados" / plots.PASTA_DOS_GRAFICOS
    arquivos = sorted(p.name for p in pasta.glob("*.png"))
    assert arquivos == ["A.png", "C.png"]
    for arquivo in pasta.glob("*.png"):
        largura, altura, dpi = dimensoes_e_dpi(arquivo)
        assert round(dpi) == plots.DPI
        # 7 x 5 inches at 300 dpi: big enough for a printed figure, and the labels are
        # drawn at the default font size, so they scale with it.
        assert (largura, altura) == (2100, 1500)


def test_the_html_embeds_the_plots_instead_of_linking_them(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    embutidas = re.findall(r'src="data:image/png;base64,([^"]+)"', html)
    assert len(embutidas) == 2
    # Self-contained: no src, href or url() pointing anywhere outside the file.
    assert not re.search(r'(src|href)="(?!data:)', html)
    assert "url(" not in html

    # The embedded bytes are the very PNG that was saved, not a second rendering.
    salvo = (tmp_path / "resultados" / plots.PASTA_DOS_GRAFICOS / "A.png").read_bytes()
    assert base64.b64decode(embutidas[0]) == salvo


def test_the_markdown_links_the_png_files(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml", "[md]")
    markdown = resultado.caminhos["md"].read_text(encoding="utf-8")

    assert "![A: original vs. simplificado e erro ao longo do tempo](graficos/A.png)" in markdown
    assert "base64" not in markdown
    for alvo in re.findall(r"\]\(([^)]+)\)", markdown):
        assert (resultado.caminhos["md"].parent / alvo).is_file()


def test_the_markdown_carries_the_same_verdict_and_table_as_the_html(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_fail.yaml", "[html, md]")
    markdown = resultado.caminhos["md"].read_text(encoding="utf-8")

    assert "Veredito: REPROVADO" in markdown
    assert "Critérios atendidos: 1 de 2 (50,0%)" in markdown
    assert "| nrmse | C | 0,52006 | 0,05 | obrigatório | falhou |" in markdown
    # Failures first here too.
    assert markdown.index("| nrmse | C |") < markdown.index("| nrmse | A |")
    assert report.razoes(resultado.veredito)[0] in markdown


def test_a_summed_variable_says_what_was_summed(tmp_path: Path) -> None:
    # X of the simplified model is X1 + X2 of the original: a report that only prints "X"
    # hides what is being compared.
    resultado = rodar(tmp_path, "config_aggregation.yaml", "[html]")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert "X1 + X2 (original) vs. X" in html


def test_a_weight_different_from_one_appears_in_the_label(tmp_path: Path) -> None:
    assert plots.rotulo_da_combinacao({"C1": 1.0, "C2": 0.5}) == "C1 + 0,5·C2"
    assert plots.rotulo_da_combinacao({"D": 1.0}) == "D"


# --- the time axis ------------------------------------------------------------

SBML_COM_UNIDADE = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="m" timeUnits="day"/>
</sbml>
"""


def test_the_time_unit_is_read_from_the_model_when_it_declares_one(tmp_path: Path) -> None:
    com_unidade = tmp_path / "com_unidade.xml"
    com_unidade.write_text(SBML_COM_UNIDADE, encoding="utf-8")

    assert reducheck.simulation.unidade_de_tempo(com_unidade) == "day"
    # The toy models declare none, and a guess would be worse than a generic label.
    from test_pipeline import FIXTURES_DIR

    assert reducheck.simulation.unidade_de_tempo(FIXTURES_DIR / "qssa_ok_original.xml") is None
