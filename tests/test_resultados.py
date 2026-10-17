"""Checks on `estudo_de_caso/gerar_resultados.py`, the script that feeds the dissertation.

The script is not part of the library: it is the case study's way of turning a verification
into the figures and LaTeX tables of `texto/`. What is tested here is what would silently
put a wrong number in the text -- the formatting of numbers, the mean and deviation of the
timing, and which rows each table has -- not the look of the figures.
"""

from __future__ import annotations

import importlib.util
import statistics
import sys
from pathlib import Path

import pytest
import roadrunner

from reducheck import qualitative
from reducheck.config import Simulacao
from reducheck.verdict import ItemAvaliado

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "estudo_de_caso" / "gerar_resultados.py"
FIXTURES = ROOT / "tests" / "fixtures"


def _carregar_script():
    spec = importlib.util.spec_from_file_location("gerar_resultados", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gerar_resultados"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


gr = _carregar_script()


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (0.45, "0{,}450"),
        (0.68452, "0{,}685"),
        (1.0, "1{,}00"),
        (0.0, "0"),
        # o arredondamento sobe a ordem de grandeza e não pode ganhar um algarismo
        (0.999995, "1{,}00"),
        (99.96, "100"),
        (987.933, "988"),
        (7.4e-10, r"$7{,}40 \times 10^{-10}$"),
        (150504.0, r"$1{,}51 \times 10^{5}$"),
        (-2.05e-10, r"$-2{,}05 \times 10^{-10}$"),
    ],
)
def test_numero_em_latex_usa_virgula_e_tres_algarismos(valor: float, esperado: str) -> None:
    assert gr.numero_latex(valor) == esperado


def test_autovalor_complexo_mostra_parte_imaginaria() -> None:
    assert gr.autovalor_latex(complex(-0.5, 0.25)) == r"$-0{,}500 \pm 0{,}250\, i$"
    assert gr.autovalor_latex(complex(-2e-10, -3e-11)) == (
        r"$-2{,}00 \times 10^{-10} \pm 3{,}00 \times 10^{-11}\, i$"
    )


def test_autovalor_real_nao_tem_parte_imaginaria() -> None:
    assert gr.autovalor_latex(complex(-3.3, 0.0)) == "$-3{,}30$"


def _item(metrica: str, variavel: str, valor: float, limite: float, passou: bool,
          obrigatorio: bool = True) -> ItemAvaliado:
    return ItemAvaliado(
        metrica=metrica, variavel=variavel, valor=valor, limite=limite, passou=passou,
        obrigatorio=obrigatorio,
    )


def test_tabela_de_criterios_tem_uma_linha_por_item_e_escapa_o_sublinhado() -> None:
    itens = [
        _item("nrmse", "Cb", 0.45, 0.05, False),
        _item("mape", "E2", 5.1e-12, 0.05, True, obrigatorio=False),
        _item("erro_estacionario", "Mb", 0.10292, 0.01, False),
    ]
    tabela = gr.tabela_criterios(itens, legenda="L", rotulo="tab:x")

    assert "\\begin{tabular}" in tabela and "\\toprule" in tabela
    assert "erro\\_estacionario" in tabela and "erro_estacionario" not in tabela
    linhas = [linha for linha in tabela.splitlines() if linha.rstrip().endswith("\\\\")]
    # cabeçalho + três itens
    assert len(linhas) == 4
    assert "\\texttt{Cb} & 0{,}450 & 0{,}0500 & obrigatório & falhou" in tabela
    assert "desejável & passou" in tabela
    assert "\\label{tab:x}" in tabela


def test_tabela_de_tempo_calcula_media_desvio_e_razao() -> None:
    tempos = {
        "Original": gr.Tempos(carga=[2.0, 2.0, 2.0], integracao=[0.010, 0.012, 0.014]),
        "Simplificação 1": gr.Tempos(carga=[1.0, 1.0, 1.0], integracao=[0.005, 0.006, 0.007]),
    }
    tabela = gr.tabela_tempo(tempos, legenda="L", rotulo="tab:t")

    media = statistics.mean([0.010, 0.012, 0.014]) * 1000
    desvio = statistics.stdev([0.010, 0.012, 0.014]) * 1000
    assert f"{gr.numero_latex(media)} $\\pm$ {gr.numero_latex(desvio)}" in tabela
    # a razão da simplificação é a integração dela dividida pela do original
    assert "0{,}500" in tabela
    assert "Simplificação 1" in tabela


def test_medir_tempo_faz_o_numero_pedido_de_execucoes() -> None:
    condicoes = Simulacao(t_inicio=0, t_fim=10, pontos=50)
    tempos = gr.medir_tempo(
        FIXTURES / "aggregation_original.xml", condicoes, ["X1"], execucoes=3
    )
    assert len(tempos.carga) == 3 and len(tempos.integracao) == 3
    assert all(t > 0 for t in tempos.carga + tempos.integracao)
    # a recompilação forçada para a medição não vaza para o resto do processo
    assert roadrunner.Config.getValue(roadrunner.Config.LOADSBMLOPTIONS_RECOMPILE) is False


def test_item_sem_variavel_sai_com_travessao_e_valor_em_texto() -> None:
    item = ItemAvaliado(
        metrica="estabilidade_local", variavel="—", valor=None, limite=None, passou=True,
        valor_texto="marginal / marginal",
    )
    tabela = gr.tabela_criterios([item], legenda="L", rotulo="tab:q")
    assert r"\texttt{estabilidade\_local} & --- & marginal / marginal & --- &" in tabela


def _analise(papel: str, ponto: dict[str, float], autovalores: tuple[complex, ...]):
    return qualitative.Analise(
        papel=papel,
        equilibrio=qualitative.Equilibrio(
            ponto=ponto, metodo="integração", residuo=1e-9, residuo_absoluto=1e-6,
            escala_de_taxa=2500.0, instante=1e9, tolerancia=1e-6, convergiu=True,
        ),
        estabilidade=qualitative.Estabilidade(
            autovalores=autovalores, classificacao="marginal", metodo="diferenças finitas",
            tolerancia=1e-6, limiar=3.3e-6,
        ),
    )


def test_tabelas_qualitativas_tem_as_variaveis_e_os_autovalores() -> None:
    comparacao = qualitative.Comparacao(
        original=_analise("original", {"Cb": 150600.0, "Cm": 1.0}, (-2.05e-10, -0.1, -3.3)),
        simplificado=_analise("simplificado", {"Cb": 150600.0}, (-2.04e-10, -0.2, -3.0)),
    )
    item = ItemAvaliado(
        metrica="equilibrio", variavel="Cb", valor=0.0, limite=0.05, passou=True,
        detalhes={"equilibrio_original": 150600.0, "equilibrio_simplificado": 150600.0},
    )
    outro = _item("nrmse", "Cm", 0.5, 0.05, False)
    equilibrios = gr.tabela_equilibrios([item, outro], legenda="L", rotulo="tab:e")
    assert (
        r"\texttt{Cb} & $1{,}51 \times 10^{5}$ & $1{,}51 \times 10^{5}$ & 0 & " in equilibrios
    )
    assert "Cm" not in equilibrios

    autovalores = gr.tabela_autovalores(comparacao, legenda="L", rotulo="tab:a")
    assert r"$-2{,}05 \times 10^{-10}$" in autovalores
    assert r"$-2{,}04 \times 10^{-10}$" in autovalores
    assert "marginal" in autovalores


def test_figura_sai_em_pdf_vetorial(tmp_path: Path) -> None:
    import numpy as np

    from reducheck.mapping import SerieComparada

    tempo = np.linspace(0, 10, 20)
    series = {
        nome: SerieComparada(nome=nome, tempo=tempo, original=tempo**2, simplificado=tempo)
        for nome in ["A", "B", "C"]
    }
    caminho = gr.figura_trajetorias(series, ["A", "B", "C"], tmp_path / "f.pdf")
    assert caminho.read_bytes().startswith(b"%PDF")
