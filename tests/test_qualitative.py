"""Equilibrium and local stability on the toy models, whose equilibria are known by hand.

The numbers asserted here are solved analytically in the comments, so a failure means the
library is wrong, not that the expectation drifted:

* ``aggregation_original``: two independent pools with constant input and first-order
  decay, so X1* = s1/d1 = 1.0/0.20 = 5 and X2* = s2/d2 = 0.5/0.22 = 2.272727...; the
  Jacobian is diagonal, with eigenvalues -d1 = -0.20 and -d2 = -0.22 (stable).
* ``aggregation_simplified``: X* = s/d = 1.5/0.207 = 7.246376..., eigenvalue -0.207
  (stable). The sum of the original equilibria is 7.272727..., so the aggregation misses
  the equilibrium by 0.36% -- which is the number the ``equilibrio`` criterion reports.
* ``qssa_ok``/``qssa_fail``: a decay chain with no outflow from C, so the total is
  conserved and the Jacobian has an exact zero eigenvalue. Equilibrium A* = B* = 0,
  C* = A(0) = 10; both models are marginal, and marginal in both is a *pass* for the
  ``estabilidade_local`` criterion, because the criterion compares classifications.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from reducheck import qualitative
from reducheck.config import Simulacao

FIXTURES = Path(__file__).parent / "fixtures"


def condicoes(t_fim: float = 50.0, pontos: int = 501) -> Simulacao:
    return Simulacao(t_inicio=0.0, t_fim=t_fim, pontos=pontos)


def analisar(nome: str, t_fim: float = 50.0) -> qualitative.Analise:
    return qualitative.analisar(FIXTURES / f"{nome}.xml", condicoes(t_fim))


# --- equilibrium -------------------------------------------------------------


def test_equilibrio_do_par_aggregation_bate_com_a_conta_analitica():
    analise = analisar("aggregation_original")
    assert analise.equilibrio.convergiu
    assert analise.equilibrio.ponto["X1"] == pytest.approx(5.0, rel=1e-8)
    assert analise.equilibrio.ponto["X2"] == pytest.approx(0.5 / 0.22, rel=1e-8)


def test_equilibrio_do_simplificado_de_aggregation():
    analise = analisar("aggregation_simplified")
    assert analise.equilibrio.ponto["X"] == pytest.approx(1.5 / 0.207, rel=1e-8)


def test_a_agregacao_erra_o_equilibrio_em_0_36_por_cento():
    """The number the ``equilibrio`` criterion measures on the pair, computed by hand."""
    original = analisar("aggregation_original").equilibrio.ponto
    simplificado = analisar("aggregation_simplified").equilibrio.ponto
    soma = original["X1"] + original["X2"]
    erro = abs(simplificado["X"] - soma) / soma
    assert erro == pytest.approx(0.00362, abs=1e-5)


def test_equilibrio_da_cadeia_qssa_esvazia_e_conserva_o_total():
    analise = analisar("qssa_ok_original", t_fim=40.0)
    ponto = analise.equilibrio.ponto
    assert analise.equilibrio.convergiu
    assert ponto["A"] == pytest.approx(0.0, abs=1e-6)
    assert ponto["B"] == pytest.approx(0.0, abs=1e-6)
    assert ponto["C"] == pytest.approx(10.0, rel=1e-6)


def test_o_residuo_e_relativo_a_velocidade_inicial_do_sistema():
    """A dimensionless residual: how much slower the system moves than it did at t0."""
    equilibrio = analisar("aggregation_original").equilibrio
    assert equilibrio.residuo <= qualitative.TOLERANCIA_DO_EQUILIBRIO
    assert equilibrio.escala_de_taxa == pytest.approx(0.6, rel=1e-6)  # max|f| em t=0
    assert equilibrio.residuo == pytest.approx(
        equilibrio.residuo_absoluto / equilibrio.escala_de_taxa, rel=1e-9
    )


def test_o_metodo_usado_fica_registrado():
    equilibrio = analisar("aggregation_original").equilibrio
    assert "steadyState" in equilibrio.metodo


def test_o_estado_e_lido_das_taxas_de_variacao():
    modelo = qualitative.preparar_modelo(
        FIXTURES / "aggregation_original.xml", condicoes()
    )
    assert qualitative.estado(modelo) == ("X1", "X2")


# --- local stability ---------------------------------------------------------


def test_autovalores_do_par_aggregation_sao_as_taxas_de_decaimento():
    analise = analisar("aggregation_original")
    reais = sorted(valor.real for valor in analise.estabilidade.autovalores)
    assert reais == pytest.approx([-0.22, -0.20], rel=1e-6)
    assert analise.estabilidade.classificacao == qualitative.ESTAVEL


def test_o_simplificado_de_aggregation_tambem_e_estavel():
    analise = analisar("aggregation_simplified")
    assert analise.estabilidade.autovalores[0].real == pytest.approx(-0.207, rel=1e-6)
    assert analise.estabilidade.classificacao == qualitative.ESTAVEL


def test_a_cadeia_conservativa_e_marginal_nos_dois_modelos():
    """C has no outflow, so the total is conserved and one eigenvalue is exactly zero."""
    original = analisar("qssa_ok_original", t_fim=40.0).estabilidade
    simplificado = analisar("qssa_ok_simplified", t_fim=40.0).estabilidade
    assert original.classificacao == qualitative.MARGINAL
    assert simplificado.classificacao == qualitative.MARGINAL
    assert original.autovalores[0].real == pytest.approx(0.0, abs=1e-9)


def test_os_autovalores_vem_ordenados_por_parte_real_decrescente():
    estabilidade = analisar("qssa_ok_original", t_fim=40.0).estabilidade
    reais = [valor.real for valor in estabilidade.autovalores]
    assert reais == sorted(reais, reverse=True)
    assert estabilidade.dominantes(3) == estabilidade.autovalores[:3]


def test_a_jacobiana_do_brinquedo_vem_do_libroadrunner():
    """A model whose state is all floating species does not need finite differences."""
    analise = analisar("aggregation_original")
    assert "libRoadRunner" in analise.estabilidade.metodo


def test_classificar_instavel_quando_ha_autovalor_com_parte_real_positiva():
    estabilidade = qualitative.classificar(np.array([0.5, -2.0]))
    assert estabilidade.classificacao == qualitative.INSTAVEL


def test_classificar_usa_tolerancia_relativa_ao_espectro():
    """The threshold scales with the model's own fastest mode.

    The same system written in another time unit is the same system, so the label may not
    depend on the unit. Multiplying every eigenvalue by 86400 (days to seconds) must not
    change the answer, which an absolute tolerance would not survive.
    """
    autovalores = np.array([-2.05e-10, -3.3])
    assert qualitative.classificar(autovalores).classificacao == qualitative.MARGINAL
    assert (
        qualitative.classificar(autovalores * 86400.0).classificacao
        == qualitative.MARGINAL
    )
    # Com tolerância muito menor, o mesmo espectro é lido como estável.
    assert (
        qualitative.classificar(autovalores, tolerancia=1e-12).classificacao
        == qualitative.ESTAVEL
    )


def test_classificar_um_espectro_todo_nulo_e_marginal():
    assert qualitative.classificar(np.zeros(2)).classificacao == qualitative.MARGINAL


# --- what the analysis refuses to claim --------------------------------------


def test_equilibrio_nao_alcancado_nao_vira_equilibrio_silencioso():
    """``divergente`` blows up at t = 1: there is no equilibrium to report."""
    with pytest.raises(qualitative.ErroDeQualitativo) as erro:
        qualitative.analisar(FIXTURES / "divergente.xml", condicoes(t_fim=0.5))
    assert "divergente" in str(erro.value)


def test_o_aviso_do_equilibrio_unico_esta_no_modulo():
    assert "um único equilíbrio" in qualitative.AVISO_DO_EQUILIBRIO_UNICO
    assert "outros equilíbrios não foram buscados" in qualitative.AVISO_DO_EQUILIBRIO_UNICO
