"""The two questions of a verification: trajectory and long run.

A run answers "does the simplified model take the same path inside the simulated window?"
and, when qualitative criteria are declared, "do the two models stop at the same place, in
the same way?". The report counts the two apart, in tabs, and reads them together, because
a single percentage would hide that Verly's simplification 1 misses the path and reaches the same
equilibrium (`C2` failed every trajectory metric and passed the equilibrium).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_pipeline import prepare
from test_report import rodar

import reducheck
from reducheck import cli, report
from reducheck.verdict import (
    APROVADO,
    LONGO_PRAZO,
    REPROVADO,
    SEM_VARIAVEL,
    TRAJETORIA,
    ItemAvaliado,
    Veredito,
    pergunta_de,
)


def item(metrica: str, variavel: str, passou: bool, obrigatorio: bool = True) -> ItemAvaliado:
    return ItemAvaliado(
        metrica=metrica,
        variavel=variavel,
        valor=0.0 if passou else 1.0,
        limite=0.5,
        passou=passou,
        obrigatorio=obrigatorio,
    )


def veredito(*itens: ItemAvaliado) -> Veredito:
    obrigatoria = any(not i.passou and i.obrigatorio for i in itens)
    return Veredito(nivel=REPROVADO if obrigatoria else APROVADO, criterios=itens)


def comparacao(instante: float) -> SimpleNamespace:
    """A stand-in for :class:`qualitative.Comparacao` with only the equilibrium instant."""
    analise = SimpleNamespace(equilibrio=SimpleNamespace(instante=instante))
    return SimpleNamespace(original=analise, simplificado=analise)


# --- splitting the verdict ----------------------------------------------------


def test_each_criterion_answers_exactly_one_question() -> None:
    assert pergunta_de(item("nrmse", "A", True)) == TRAJETORIA
    assert pergunta_de(item("erro_estacionario", "A", True)) == TRAJETORIA
    assert pergunta_de(item("equilibrio", "A", True)) == LONGO_PRAZO
    assert pergunta_de(item("estabilidade_local", SEM_VARIAVEL, True)) == LONGO_PRAZO


def test_each_part_is_judged_by_the_same_rule_as_the_whole() -> None:
    todos = veredito(
        item("nrmse", "A", False),
        item("mape", "A", False, obrigatorio=False),
        item("equilibrio", "A", True),
        item("estabilidade_local", SEM_VARIAVEL, True),
    )
    caminho, destino = todos.parte(TRAJETORIA), todos.parte(LONGO_PRAZO)

    assert caminho.nivel == REPROVADO and len(caminho.criterios) == 2
    assert destino.nivel == APROVADO and len(destino.criterios) == 2
    # The parts add up to the whole: nothing is counted twice or lost.
    assert len(caminho.criterios) + len(destino.criterios) == len(todos.criterios)


def test_a_part_with_no_criterion_comes_back_empty() -> None:
    assert veredito(item("nrmse", "A", True)).parte(LONGO_PRAZO).criterios == ()


def test_an_unknown_question_is_refused() -> None:
    with pytest.raises(ValueError, match="pergunta desconhecida"):
        veredito(item("nrmse", "A", True)).parte("trajetória")


# --- reading the two together -------------------------------------------------


@pytest.mark.parametrize(
    ("caminho", "destino", "trecho"),
    [
        (True, True, "Fiel: faz o mesmo caminho e chega ao mesmo lugar."),
        (False, True, "Erra o caminho, mas acerta o destino."),
        (True, False, "Acerta o caminho no período simulado"),
        (False, False, "Não é fiel nem no caminho nem no destino."),
    ],
)
def test_the_first_sentence_says_what_the_combination_means(
    caminho: bool, destino: bool, trecho: str
) -> None:
    frases = report.leitura_conjunta(
        veredito(item("nrmse", "A", caminho), item("equilibrio", "A", destino))
    )
    assert trecho in frases[0]


def test_the_variables_that_miss_the_path_and_hit_the_destination_are_named() -> None:
    """The case of Verly's C2: wrong in every plot, right in the equilibrium table."""
    frases = report.leitura_conjunta(
        veredito(
            item("nrmse", "C2", False),
            item("nrmse", "Cb", False),
            item("nrmse", "E2", True),
            item("equilibrio", "C2", True),
            item("equilibrio", "Cb", True),
            item("equilibrio", "E2", True),
        )
    )
    esperado = "C2 e Cb: a trajetória falhou, mas o equilíbrio passou"
    assert any(frase.startswith(esperado) for frase in frases)
    assert not any("E2" in frase for frase in frases)


def test_the_opposite_disagreement_is_named_too() -> None:
    frases = report.leitura_conjunta(
        veredito(item("nrmse", "A", True), item("equilibrio", "A", False))
    )
    assert any(f.startswith("A: a trajetória passou, mas o equilíbrio falhou") for f in frases)


def test_an_equilibrium_beyond_the_window_is_flagged() -> None:
    itens = veredito(item("nrmse", "A", False), item("equilibrio", "A", True))

    longe = report.leitura_conjunta(itens, comparacao(7.2e8), t_fim=720.0)
    perto = report.leitura_conjunta(itens, comparacao(500.0), t_fim=720.0)

    assert any("1e+06× o tempo simulado" in frase for frase in longe)
    assert not any(frase.startswith("Atenção") for frase in perto)


@pytest.mark.parametrize(
    ("itens", "falta", "como_ligar"),
    [
        ((item("nrmse", "A", True),), "Só a trajetória", "'equilibrio'"),
        ((item("equilibrio", "A", True),), "Só o longo prazo", "'nrmse'"),
    ],
)
def test_a_single_question_says_which_one_is_missing_and_how_to_add_it(
    itens: tuple[ItemAvaliado, ...], falta: str, como_ligar: str
) -> None:
    (frase,) = report.leitura_conjunta(veredito(*itens))
    assert frase.startswith(falta)
    assert como_ligar in frase


# --- the files ----------------------------------------------------------------


def test_the_html_has_one_tab_per_question_plus_summary_and_explanation(
    tmp_path: Path,
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    for aba in ("resumo", "trajetoria", "longo_prazo", "explicacao"):
        assert f'id="aba-{aba}"' in html
        assert f'data-aba="{aba}"' in html
    # Without JavaScript the tab bar stays hidden and every section is shown in sequence.
    assert 'id="abas" role="tablist" aria-label="Partes do relatório" hidden' in html
    # Both questions are spelled out, in plain words, where they are answered and explained.
    for pergunta in report.EXPLICACOES_DAS_PERGUNTAS.values():
        assert html.count(pergunta["pergunta"]) >= 3
        assert pergunta["nao_responde"] in html
    for frase in report.leitura_conjunta(
        resultado.veredito, resultado.comparacao, resultado.configuracao.simulacao.t_fim
    ):
        assert frase in html


def test_a_question_not_declared_is_shown_as_not_verified(tmp_path: Path) -> None:
    resultado = rodar(tmp_path, "config_qssa_ok.yaml")
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert "NÃO VERIFICADA" in html
    assert "acrescente ao YAML os critérios 'equilibrio' e 'estabilidade_local'" in html


def test_the_markdown_has_the_same_sections_in_order(tmp_path: Path) -> None:
    reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    markdown = (tmp_path / "resultados" / "relatorio.md").read_text(encoding="utf-8")

    titulos = ["## Resumo", "## Trajetória", "## Longo prazo", "## O que cada um mede"]
    posicoes = [markdown.index(titulo) for titulo in titulos]
    assert posicoes == sorted(posicoes)
    assert "| Trajetória | Longo prazo | O que quer dizer |" in markdown


def test_the_json_counts_each_question_apart(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))

    caminho = dados["por_pergunta"]["trajetoria"]
    destino = dados["por_pergunta"]["longo_prazo"]
    assert caminho["total"] + destino["total"] == len(dados["criterios"])
    # One 'equilibrio' item per core variable, plus the single 'estabilidade_local'.
    assert destino["total"] == len(resultado.configuracao.nomes_core()) + 1
    assert dados["leitura_conjunta"] == report.leitura_conjunta(
        resultado.veredito, resultado.comparacao, resultado.configuracao.simulacao.t_fim
    )


def test_the_json_marks_a_question_not_declared_as_null(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))
    assert dados["por_pergunta"]["longo_prazo"] is None


def test_the_terminal_shows_one_line_per_question(tmp_path: Path) -> None:
    linhas = cli.resumo(reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml")))
    assert any(linha.startswith("  Trajetória   ") for linha in linhas)
    assert any(linha.startswith("  Longo prazo  ") for linha in linhas)

    linhas = cli.resumo(reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml")))
    assert "  Longo prazo  não verificada" in linhas
