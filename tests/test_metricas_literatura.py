"""Metrics taken from the model-reduction literature: rmse, erro_integral, erro_simetrico
and erro_l2_rel, plus the qualitative comparison of the long-run behaviour.

The expected values are exact (tolerance 1e-12) and were computed by hand: the toy pair
differs only at t = 2, where the original is 4 and the simplified 3.
"""

from __future__ import annotations

import numpy as np
import pytest

from reducheck import metrics, qualitative, verdict
from reducheck.config import ANALISES_QUALITATIVAS, QUALITATIVAS_POR_VARIAVEL, Criterio

TOL = 1e-12

T = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
ORIG = np.array([1.0, 2.0, 4.0, 2.0, 1.0])
SIMP = np.array([1.0, 2.0, 3.0, 2.0, 1.0])

NOVAS = ["rmse", "erro_integral", "erro_simetrico", "erro_l2_rel"]


def _confere_agregacao(resultado: metrics.ResultadoDeMetrica, n: int) -> None:
    """The pointwise error, added up over every point, gives back the value."""
    assert resultado.erro_pontual is not None
    todos = np.ones(n, dtype=bool)
    agregado = metrics.agregar(resultado.erro_pontual, resultado.agregacao, todos)
    assert agregado == pytest.approx(resultado.valor, abs=TOL)


# --- registry ----------------------------------------------------------------


def test_the_literature_metrics_are_registered() -> None:
    assert set(NOVAS) <= metrics.disponiveis()


@pytest.mark.parametrize("nome", NOVAS)
def test_every_new_metric_is_zero_for_identical_series(nome: str) -> None:
    resultado = metrics.calcular(nome, T, ORIG, ORIG)
    assert resultado.valor == 0.0
    assert resultado.descricao
    assert resultado.avisos == ()


@pytest.mark.parametrize("nome", NOVAS)
def test_every_new_metric_aggregates_back_to_its_value(nome: str) -> None:
    _confere_agregacao(metrics.calcular(nome, T, ORIG, SIMP), T.size)


def test_the_trapezoid_weights_follow_a_non_uniform_grid() -> None:
    pesos = metrics._pesos_trapezio(np.array([0.0, 1.0, 3.0]))
    np.testing.assert_allclose(pesos, [0.5, 1.5, 1.0], atol=TOL)
    assert float(np.sum(metrics._pesos_trapezio(T))) == pytest.approx(4.0, abs=TOL)


# --- A1. rmse ----------------------------------------------------------------


def test_rmse_is_the_root_of_the_mean_squared_error() -> None:
    resultado = metrics.rmse(T, ORIG, SIMP)
    assert resultado.valor == pytest.approx(0.4472135954999579, abs=TOL)
    assert resultado.fracao is False
    assert resultado.agregacao == "raiz_da_media"
    assert resultado.descricao == "raiz do erro quadrático médio (na unidade da variável)"


def test_rmse_is_nrmse_times_the_range() -> None:
    nrmse = metrics.nrmse(T, ORIG, SIMP).valor
    assert nrmse == pytest.approx(0.14907119849998599, abs=TOL)
    amplitude = ORIG.max() - ORIG.min()
    assert metrics.rmse(T, ORIG, SIMP).valor == pytest.approx(nrmse * amplitude, abs=TOL)


# --- A2. erro_integral (Rao et al., 2014) -------------------------------------


def test_erro_integral_uses_the_trapezoid_rule_and_not_the_plain_mean() -> None:
    resultado = metrics.erro_integral(T, ORIG, SIMP)
    # 0,25 x 1 / 4; the plain mean would be 0,05.
    assert resultado.valor == pytest.approx(0.0625, abs=TOL)
    assert resultado.fracao is True
    assert resultado.agregacao == "media"
    assert resultado.detalhes["pontos_excluidos"] == 0


def test_erro_integral_excludes_a_point_near_zero_and_says_so() -> None:
    original = np.array([0.0, 2.0, 4.0, 2.0, 1.0])
    simplificado = np.array([0.5, 2.0, 3.0, 2.0, 1.0])
    resultado = metrics.erro_integral(T, original, simplificado)
    assert resultado.valor == pytest.approx(0.07142857142857142, abs=TOL)  # 0,25 / 3,5
    assert resultado.detalhes["pontos_excluidos"] == 1
    exclusao = [aviso for aviso in resultado.avisos if "excluídos" in aviso]
    assert len(exclusao) == 1
    assert exclusao[0].startswith("erro_integral:")
    assert np.isnan(resultado.erro_pontual[0])
    _confere_agregacao(resultado, T.size)


def test_erro_integral_on_a_non_uniform_grid() -> None:
    tempo = np.array([0.0, 1.0, 3.0])
    resultado = metrics.erro_integral(
        tempo, np.array([1.0, 1.0, 1.0]), np.array([1.0, 1.0, 0.5])
    )
    assert resultado.valor == pytest.approx(0.16666666666666666, abs=TOL)
    _confere_agregacao(resultado, tempo.size)


def test_erro_integral_honours_an_explicit_epsilon() -> None:
    original = np.array([0.0, 2.0, 4.0, 2.0, 1.0])
    simplificado = np.array([0.5, 2.0, 3.0, 2.0, 1.0])
    resultado = metrics.calcular(
        "erro_integral", T, original, simplificado, {"epsilon": 1.5}
    )
    assert resultado.detalhes["pontos_excluidos"] == 2  # 0 and 1 are below 1,5
    assert resultado.detalhes["epsilon"] == 1.5


def test_erro_integral_warns_about_points_close_to_zero_with_its_own_name() -> None:
    # Most points sit at 0,1% of the peak: above the epsilon, below 1% of the maximum.
    original = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1.0])
    resultado = metrics.erro_integral(T, original, original * 1.01)
    perto = [aviso for aviso in resultado.avisos if "perto de zero" in aviso]
    assert len(perto) == 1
    assert perto[0].startswith("erro_integral:")


def test_the_mape_warning_near_zero_did_not_change() -> None:
    original = np.array([1e-3, 1e-3, 1e-3, 1e-3, 1.0])
    (aviso,) = metrics.mape(T, original, original * 1.01).avisos
    assert aviso == (
        "mape: 4 de 5 pontos (80%) entram no cálculo perto de zero (|original| < 1% do "
        "máximo, 0.01); nesses pontos uma diferença pequena vira um erro relativo grande, e "
        "o MAPE pode reprovar uma trajetória boa. 'nrmse' ou 'erro_max_abs' não dividem pelo "
        "valor."
    )


def test_erro_integral_refuses_an_original_that_is_all_zero() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="erro_integral"):
        metrics.erro_integral(T, np.zeros(5), SIMP)


# --- A3. erro_simetrico (Frøysa et al., 2018) ---------------------------------


def test_erro_simetrico_is_the_mean_of_the_two_integrals() -> None:
    resultado = metrics.erro_simetrico(T, ORIG, SIMP)
    assert resultado.valor == pytest.approx(0.07291666666666666, abs=TOL)
    assert resultado.detalhes["I_original"] == pytest.approx(0.0625, abs=TOL)
    assert resultado.detalhes["I_simplificado"] == pytest.approx(0.08333333333333333, abs=TOL)
    assert resultado.detalhes["pontos_excluidos"] == 0
    assert resultado.fracao is True
    assert resultado.agregacao == "media"


def test_erro_simetrico_is_symmetric() -> None:
    ida = metrics.erro_simetrico(T, ORIG, SIMP)
    volta = metrics.erro_simetrico(T, SIMP, ORIG)
    assert ida.valor == volta.valor
    assert ida.detalhes["I_original"] == volta.detalhes["I_simplificado"]


def test_erro_simetrico_uses_the_same_points_in_both_terms() -> None:
    # The simplified is zero at t = 1: that point leaves both integrals, not only one.
    original = np.array([1.0, 2.0, 4.0, 2.0, 1.0])
    simplificado = np.array([1.0, 0.0, 4.0, 2.0, 1.0])
    resultado = metrics.erro_simetrico(T, original, simplificado)
    assert resultado.detalhes["pontos_excluidos"] == 1
    assert resultado.valor == 0.0
    assert any("excluídos" in aviso for aviso in resultado.avisos)
    _confere_agregacao(resultado, T.size)


def test_erro_simetrico_refuses_a_simplified_that_is_all_zero() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="simplificado"):
        metrics.erro_simetrico(T, ORIG, np.zeros(5))


# --- A4. erro_l2_rel (Vejchodský, 2014) ---------------------------------------


def test_erro_l2_rel_is_the_relative_l2_norm() -> None:
    resultado = metrics.erro_l2_rel(T, ORIG, SIMP)
    assert resultado.valor == pytest.approx(0.2, abs=TOL)  # sqrt(1/25)
    assert resultado.fracao is True
    assert resultado.agregacao == "raiz_da_media"


def test_erro_l2_rel_accepts_an_original_that_is_mostly_zero() -> None:
    pulso = np.array([0.0, 0.0, 1.0, 0.0, 0.0])
    assert metrics.erro_l2_rel(T, pulso, pulso).valor == 0.0


def test_erro_l2_rel_refuses_an_original_with_zero_norm() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="erro_max_abs"):
        metrics.erro_l2_rel(T, np.zeros(5), SIMP)


# --- C. comportamento_longo_prazo --------------------------------------------


def _analise(papel: str, convergiu: bool) -> qualitative.Analise:
    return qualitative.Analise(
        papel=papel,
        equilibrio=qualitative.Equilibrio(
            ponto={"X": 1.0}, metodo="integração", residuo=1e-9, residuo_absoluto=1e-9,
            escala_de_taxa=1.0, instante=10.0, tolerancia=1e-6, convergiu=convergiu,
        ),
        estabilidade=qualitative.Estabilidade(
            autovalores=(-1.0 + 0j,), classificacao="estável", metodo="diferenças finitas",
            tolerancia=1e-6, limiar=1e-6,
        ),
    )


def _avaliar_longo_prazo(original: bool, simplificado: bool) -> verdict.Veredito:
    comparacao = qualitative.Comparacao(
        original=_analise("original", original),
        simplificado=_analise("simplificado", simplificado),
    )
    return verdict.avaliar(
        [Criterio(metrica="comportamento_longo_prazo")], {}, comparacao=comparacao
    )


def test_comportamento_longo_prazo_is_a_whole_model_analysis() -> None:
    assert "comportamento_longo_prazo" in ANALISES_QUALITATIVAS
    assert "comportamento_longo_prazo" not in QUALITATIVAS_POR_VARIAVEL


def test_comportamento_longo_prazo_passes_when_both_reach_an_equilibrium() -> None:
    resultado = _avaliar_longo_prazo(True, True)
    (item,) = resultado.criterios
    assert item.passou
    assert item.variavel == verdict.SEM_VARIAVEL
    assert item.valor is None and item.limite is None
    assert verdict.pergunta_de(item) == verdict.LONGO_PRAZO
    assert resultado.nivel == verdict.APROVADO


def test_comportamento_longo_prazo_fails_when_only_one_reaches_an_equilibrium() -> None:
    resultado = _avaliar_longo_prazo(True, False)
    (item,) = resultado.criterios
    assert not item.passou
    assert "original" in item.descricao and "simplificado" in item.descricao
    assert "não" in item.descricao
    assert resultado.nivel == verdict.REPROVADO


def test_comportamento_longo_prazo_passes_on_the_real_toy_pair() -> None:
    from pathlib import Path

    from reducheck.config import Simulacao

    fixtures = Path(__file__).parent / "fixtures"
    condicoes = Simulacao(t_inicio=0.0, t_fim=10.0, pontos=11)
    comparacao = qualitative.Comparacao(
        original=qualitative.analisar(fixtures / "qssa_ok_original.xml", condicoes),
        simplificado=qualitative.analisar(
            fixtures / "qssa_ok_simplified.xml", condicoes, papel="simplificado"
        ),
    )
    resultado = verdict.avaliar(
        [Criterio(metrica="comportamento_longo_prazo")], {}, comparacao=comparacao
    )
    assert resultado.criterios[0].passou
