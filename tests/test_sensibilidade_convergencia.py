"""Checks on `estudo_de_caso/sensibilidade_convergencia.py`.

Like `gerar_resultados.py`, the script is the case study's, not the library's. What is tested
is what would put a wrong statement in the text: the range of tolerances reported as giving
the default verdict, and the "Parou em" column, which has to show when the two models
stopped at different instants. The sweeps themselves call the library unchanged and are
covered by its own tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "estudo_de_caso" / "sensibilidade_convergencia.py"


def _carregar_script():
    spec = importlib.util.spec_from_file_location("sensibilidade_convergencia", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["sensibilidade_convergencia"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


sc = _carregar_script()


def _ponto(tolerancia, nivel="REPROVADO", passados=5, instante=(7.2e8, 7.2e8), falha=""):
    return sc.Ponto(
        tolerancia=tolerancia,
        horizonte=None,
        instante={"original": instante[0], "simplificado": instante[1]},
        nivel=nivel,
        passados=passados,
        total=6,
        falha=falha,
    )


def test_faixa_vai_ate_onde_o_veredito_e_o_ponto_de_parada_mudam():
    pontos = [
        _ponto(1e-5, passados=3, instante=(7.2e7, 7.2e7)),
        _ponto(1e-6),
        _ponto(1e-7),
        _ponto(1e-8),
        _ponto(1e-9, nivel="APROVADO", passados=6, instante=(7.2e9, 7.2e9)),
    ]
    assert sc.faixa_estavel(pontos, 1e-6) == (1e-6, 1e-8)


def test_mesma_contagem_em_outro_ponto_de_parada_nao_conta_como_mesmo_veredito():
    # O caso de 10⁻¹¹ na Verly: 5/6 como o padrão, mas cada modelo parou num instante.
    pontos = [_ponto(1e-6), _ponto(1e-7, instante=(7.2e8, 7.2e9))]
    assert sc.faixa_estavel(pontos, 1e-6) == (1e-6, 1e-6)


def test_faixa_e_none_quando_a_referencia_falhou():
    assert sc.faixa_estavel([_ponto(1e-6, falha="não convergiu")], 1e-6) is None


def test_faixa_nao_atravessa_um_ponto_que_falhou():
    pontos = [_ponto(1e-6), _ponto(1e-7, falha="não convergiu"), _ponto(1e-8)]
    assert sc.faixa_estavel(pontos, 1e-6) == (1e-6, 1e-6)


def test_parou_em_mostra_os_dois_instantes_so_quando_diferem():
    assert sc._instante(_ponto(1e-6)) == "$7{,}20 \\times 10^{8}$"
    assert sc._instante(_ponto(1e-6, instante=(720.0, None))) == "720 / SS"


def test_tabela_marca_a_tolerancia_padrao_e_o_erro_acima_do_limite():
    ponto = _ponto(1e-6)
    ponto = sc.Ponto(**{**ponto.__dict__, "erro": {"C1": 0.0933, "Cb": 4.17e-6}})
    latex = sc.tabela_tolerancia([ponto], ["Cb", "C1"], 0.05)
    assert "$10^{-6}$ (padrão)" in latex
    assert "\\textbf{0{,}0933}" in latex
    assert "\\textbf{$4" not in latex
    assert latex.startswith("% Gerado por estudo_de_caso/sensibilidade_convergencia.py")
