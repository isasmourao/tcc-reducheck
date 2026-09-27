"""Unit tests of the individual pipeline steps (the configuration is in test_config.py)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reducheck import config as config_mod
from reducheck import mapping, metrics, report, simulation, verdict

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --- simulation --------------------------------------------------------------


CONDICOES = config_mod.Simulacao(t_fim=40.0, pontos=401)


def test_simulation_returns_the_requested_columns() -> None:
    trajetorias = simulation.simular(FIXTURES_DIR / "qssa_ok_original.xml", CONDICOES, ["A", "C"])

    assert trajetorias.nomes == ("A", "C")
    assert trajetorias.estados.shape == (401, 2)
    assert trajetorias.tempo.shape == (401,)
    assert trajetorias.tempo[0] == 0.0
    assert trajetorias.tempo[-1] == pytest.approx(40.0)
    assert np.isfinite(trajetorias.estados).all()
    np.testing.assert_allclose(trajetorias.serie("A"), trajetorias.estados[:, 0])


def test_both_models_share_the_time_grid() -> None:
    original = simulation.simular(FIXTURES_DIR / "qssa_ok_original.xml", CONDICOES, ["A"])
    simplificado = simulation.simular(FIXTURES_DIR / "qssa_ok_simplified.xml", CONDICOES, ["A"])
    np.testing.assert_array_equal(original.tempo, simplificado.tempo)


def test_simulation_reports_an_unknown_variable() -> None:
    with pytest.raises(simulation.ErroDeSimulacao, match="Z"):
        simulation.simular(FIXTURES_DIR / "qssa_ok_original.xml", CONDICOES, ["Z"])


def test_simulation_rejects_an_unsupported_solver() -> None:
    condicoes = config_mod.Simulacao(t_fim=40.0, pontos=401, solver="euler")
    with pytest.raises(simulation.ErroDeSimulacao, match="euler"):
        simulation.simular(FIXTURES_DIR / "qssa_ok_original.xml", condicoes, ["A"])


# --- mapping -----------------------------------------------------------------


def trajetorias(nomes: tuple[str, ...], colunas: list[list[float]]) -> simulation.Trajetorias:
    return simulation.Trajetorias(
        tempo=np.array([0.0, 1.0]), nomes=nomes, estados=np.array(colunas, dtype=float).T
    )


def test_mapping_pairs_the_declared_variables() -> None:
    original = trajetorias(("A", "C"), [[1.0, 2.0], [3.0, 4.0]])
    simplificado = trajetorias(("a", "c"), [[1.5, 2.5], [3.5, 4.5]])
    variaveis = [
        config_mod.Variavel(nome="entrada", original="A", simplificado="a"),
        config_mod.Variavel(nome="saida", original="C", simplificado="c"),
    ]

    series = mapping.mapear(variaveis, original, simplificado)

    assert list(series) == ["entrada", "saida"]
    np.testing.assert_allclose(series["entrada"].original, [1.0, 2.0])
    np.testing.assert_allclose(series["entrada"].simplificado, [1.5, 2.5])
    np.testing.assert_allclose(series["saida"].original, [3.0, 4.0])
    np.testing.assert_allclose(series["saida"].tempo, [0.0, 1.0])


def test_mapping_sums_the_variables_of_a_list() -> None:
    original = trajetorias(("Mo", "M1", "M2"), [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    simplificado = trajetorias(("M",), [[9.0, 12.0]])
    variaveis = [config_mod.Variavel(nome="M", original=["Mo", "M1", "M2"], simplificado="M")]

    series = mapping.mapear(variaveis, original, simplificado)

    np.testing.assert_allclose(series["M"].original, [9.0, 12.0])
    np.testing.assert_allclose(series["M"].simplificado, [9.0, 12.0])


def test_mapping_applies_the_weights_of_a_dictionary() -> None:
    original = trajetorias(("C1", "C2"), [[2.0, 4.0], [10.0, 20.0]])
    simplificado = trajetorias(("C",), [[7.0, 14.0]])
    variaveis = [config_mod.Variavel(nome="C", original={"C1": 1.0, "C2": 0.5}, simplificado="C")]

    series = mapping.mapear(variaveis, original, simplificado)

    np.testing.assert_allclose(series["C"].original, [7.0, 14.0])


def test_a_sum_may_also_be_on_the_simplified_side() -> None:
    original = trajetorias(("A",), [[6.0, 8.0]])
    simplificado = trajetorias(("a1", "a2"), [[2.0, 3.0], [4.0, 5.0]])
    variaveis = [config_mod.Variavel(nome="A", original="A", simplificado=["a1", "a2"])]

    series = mapping.mapear(variaveis, original, simplificado)

    np.testing.assert_allclose(series["A"].simplificado, [6.0, 8.0])


def test_mapping_records_what_each_side_was_built_from() -> None:
    original = trajetorias(("Mo", "M1"), [[1.0, 2.0], [3.0, 4.0]])
    simplificado = trajetorias(("M",), [[4.0, 6.0]])
    variaveis = [config_mod.Variavel(nome="M", original=["Mo", "M1"], simplificado="M")]

    serie = mapping.mapear(variaveis, original, simplificado)["M"]

    assert serie.pesos_original == {"Mo": 1.0, "M1": 1.0}
    assert serie.pesos_simplificado == {"M": 1.0}


def test_a_dropped_variable_produces_no_series() -> None:
    original = trajetorias(("A", "B"), [[1.0, 2.0], [3.0, 4.0]])
    simplificado = trajetorias(("A",), [[1.0, 2.0]])
    variaveis = [
        config_mod.Variavel(nome="A", original="A", simplificado="A"),
        config_mod.Variavel(nome="B", original="B", simplificado=None, core=False),
    ]

    series = mapping.mapear(variaveis, original, simplificado)

    assert list(series) == ["A"]


def test_mapping_asks_the_simulation_for_every_name_once() -> None:
    variaveis = [
        config_mod.Variavel(nome="M", original=["Mo", "M1"], simplificado="M"),
        config_mod.Variavel(nome="soma", original={"M1": 0.5, "D": 1.0}, simplificado="D"),
        config_mod.Variavel(nome="B", original="B", simplificado=None, core=False),
    ]

    assert mapping.nomes_simulados(variaveis, "original") == ["Mo", "M1", "D", "B"]
    # The dropped variable asks for nothing on the simplified side.
    assert mapping.nomes_simulados(variaveis, "simplificado") == ["M", "D"]


def test_mapping_names_the_model_when_a_summed_variable_is_missing() -> None:
    original = trajetorias(("Mo",), [[1.0, 2.0]])
    simplificado = trajetorias(("M",), [[1.0, 2.0]])
    variaveis = [config_mod.Variavel(nome="M", original=["Mo", "M1"], simplificado="M")]

    with pytest.raises(mapping.ErroDeMapeamento, match="M1"):
        mapping.mapear(variaveis, original, simplificado)



# --- metrics -----------------------------------------------------------------

#: One fixture for several metrics: five points, a relative error of exactly 10% at every
#: point, so the expected value of mape, erro_max_rel and erro_estacionario is 0,1 and the
#: expected erro_max_abs is 0,8 (the last point, where the series is largest).
TEMPO = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
ORIGINAL = np.array([1.0, 2.0, 4.0, 5.0, 8.0])
COM_10_PORCENTO = ORIGINAL * 1.1

TODAS = ["nrmse", "mape", "erro_max_abs", "erro_max_rel", "erro_estacionario"]


def test_nrmse_is_zero_for_identical_series() -> None:
    serie = np.array([1.0, 2.0, 3.0])
    assert metrics.nrmse(serie, serie, serie).valor == 0.0


def test_nrmse_is_the_rmse_over_the_range_of_the_original() -> None:
    original = np.array([0.0, 2.0, 4.0])  # range of 4
    simplificado = original + 1.0  # constant error of 1 -> rmse of 1
    assert metrics.nrmse(original, original, simplificado).valor == pytest.approx(0.25)


def test_nrmse_normalizes_by_the_original_not_the_simplified() -> None:
    original = np.array([0.0, 1.0, 2.0])  # range of 2
    simplificado = np.array([0.0, 10.0, 20.0])
    esperado = float(np.sqrt(np.mean((original - simplificado) ** 2)) / 2.0)
    assert metrics.nrmse(original, original, simplificado).valor == pytest.approx(esperado)


def test_nrmse_refuses_a_constant_original() -> None:
    constante = np.array([2.0, 2.0, 2.0])
    with pytest.raises(metrics.ErroDeMetrica):
        metrics.nrmse(constante, constante, np.array([2.0, 2.1, 2.0]))


def test_every_metric_of_the_mvp_is_registered() -> None:
    assert set(TODAS) <= metrics.disponiveis()
    assert metrics.obter("nrmse") is metrics.nrmse
    with pytest.raises(metrics.ErroDeMetrica, match="inexistente"):
        metrics.obter("inexistente")


def test_every_metric_is_zero_for_identical_series() -> None:
    for nome in TODAS:
        resultado = metrics.calcular(nome, TEMPO, ORIGINAL, ORIGINAL)
        assert resultado.valor == 0.0, nome
        assert resultado.descricao, nome
        assert resultado.avisos == (), nome


def test_mape_is_the_mean_relative_error() -> None:
    # errors of 0,1 / 0,2 / 0,4 / 0,5 / 0,8 over 1 / 2 / 4 / 5 / 8: 10% at every point.
    resultado = metrics.calcular("mape", TEMPO, ORIGINAL, COM_10_PORCENTO)

    assert resultado.valor == pytest.approx(0.1)
    assert resultado.detalhes["pontos_usados"] == 5
    assert resultado.detalhes["pontos_excluidos"] == 0


def test_mape_averages_and_is_not_the_maximum() -> None:
    # 100% wrong at one point out of four, exact elsewhere: mean 0,25, maximum 1,0.
    original = np.array([1.0, 1.0, 1.0, 1.0])
    simplificado = np.array([2.0, 1.0, 1.0, 1.0])
    tempo = np.arange(4.0)

    assert metrics.calcular("mape", tempo, original, simplificado).valor == pytest.approx(0.25)
    maximo = metrics.calcular("erro_max_rel", tempo, original, simplificado)
    assert maximo.valor == pytest.approx(1.0)


def test_mape_excludes_the_points_where_the_original_is_zero_and_says_how_many() -> None:
    original = np.array([0.0, 2.0, 4.0, 5.0, 8.0])
    simplificado = np.array([0.5, 2.2, 4.4, 5.5, 8.8])

    resultado = metrics.calcular("mape", TEMPO, original, simplificado)

    # Without the protection the first point alone would be an infinite relative error.
    assert resultado.valor == pytest.approx(0.1)
    assert resultado.detalhes["pontos_excluidos"] == 1
    assert len(resultado.avisos) == 1
    assert "1 de 5" in resultado.avisos[0]


def test_mape_honours_an_explicit_epsilon() -> None:
    # With epsilon = 3, the points at 1 and 2 are dropped: 2 of the 5 excluded.
    resultado = metrics.calcular("mape", TEMPO, ORIGINAL, COM_10_PORCENTO, {"epsilon": 3.0})

    assert resultado.valor == pytest.approx(0.1)
    assert resultado.detalhes["pontos_excluidos"] == 2
    assert resultado.detalhes["epsilon"] == 3.0


def test_the_default_epsilon_follows_the_scale_of_the_variable() -> None:
    # The same series in another unit must exclude the same points, so the default
    # threshold is relative to the largest value of the original.
    original = np.array([0.0, 2.0, 4.0, 5.0, 8.0])
    for escala in (1.0, 1e-9, 1e9):
        resultado = metrics.calcular("mape", TEMPO, original * escala, original * escala * 1.1)
        assert resultado.detalhes["pontos_excluidos"] == 1
        assert resultado.valor == pytest.approx(0.1)


def test_mape_refuses_a_series_that_is_all_near_zero() -> None:
    quase_zero = np.array([0.0, 0.0, 0.0])
    with pytest.raises(metrics.ErroDeMetrica, match="erro_max_abs"):
        metrics.calcular("mape", np.arange(3.0), quase_zero, np.array([1.0, 2.0, 3.0]))
    with pytest.raises(metrics.ErroDeMetrica, match="erro_max_abs"):
        metrics.calcular("mape", TEMPO, ORIGINAL, COM_10_PORCENTO, {"epsilon": 100.0})


def test_erro_max_abs_is_the_largest_difference_and_records_when_it_happened() -> None:
    resultado = metrics.calcular("erro_max_abs", TEMPO, ORIGINAL, COM_10_PORCENTO)

    assert resultado.valor == pytest.approx(0.8)  # 10% of 8, the last point
    assert resultado.detalhes["instante"] == 4.0


def test_erro_max_abs_and_erro_max_rel_can_point_at_different_instants() -> None:
    # An absolute error of 0,5 over 1 is worse, in relative terms, than 1,0 over 10.
    tempo = np.array([0.0, 1.0])
    original = np.array([1.0, 10.0])
    simplificado = np.array([1.5, 11.0])

    absoluto = metrics.calcular("erro_max_abs", tempo, original, simplificado)
    relativo = metrics.calcular("erro_max_rel", tempo, original, simplificado)

    assert (absoluto.valor, absoluto.detalhes["instante"]) == (1.0, 1.0)
    assert (relativo.valor, relativo.detalhes["instante"]) == (0.5, 0.0)


def test_erro_max_rel_excludes_the_points_near_zero() -> None:
    original = np.array([0.0, 2.0, 4.0, 5.0, 8.0])
    simplificado = np.array([0.5, 2.2, 4.4, 5.5, 8.8])

    resultado = metrics.calcular("erro_max_rel", TEMPO, original, simplificado)

    assert resultado.valor == pytest.approx(0.1)
    assert resultado.detalhes["pontos_excluidos"] == 1
    assert len(resultado.avisos) == 1


def test_erro_estacionario_compares_the_final_values_by_default() -> None:
    resultado = metrics.calcular("erro_estacionario", TEMPO, ORIGINAL, COM_10_PORCENTO)

    assert resultado.valor == pytest.approx(0.1)  # |8 - 8,8| / 8
    assert resultado.detalhes["pontos_na_janela"] == 1


def test_erro_estacionario_averages_the_configured_final_window() -> None:
    # Half of the span of [0, 4] is t >= 2: the three last points, 4 + 5 + 8 = 17 against
    # 4,4 + 5,5 + 8,8 = 18,7, so |17 - 18,7| / 17 = 0,1.
    resultado = metrics.calcular(
        "erro_estacionario", TEMPO, ORIGINAL, COM_10_PORCENTO, {"fracao_final": 0.5}
    )

    assert resultado.valor == pytest.approx(0.1)
    assert resultado.detalhes["pontos_na_janela"] == 3
    assert resultado.detalhes["original"] == pytest.approx(17.0 / 3.0)


def test_erro_estacionario_ignores_a_transient_that_the_other_metrics_see() -> None:
    # Wrong by 100% at the start, exact at the end: this is the criterion that says so.
    original = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
    simplificado = np.array([2.0, 1.5, 1.0, 1.0, 1.0])

    estacionario = metrics.calcular("erro_estacionario", TEMPO, original, simplificado)
    assert estacionario.valor == pytest.approx(0.0)
    assert metrics.calcular("mape", TEMPO, original, simplificado).valor == pytest.approx(0.3)


def test_the_final_window_is_taken_on_time_not_on_the_number_of_points() -> None:
    # The same horizon simulated with more points must average the same time window.
    for pontos, esperado in ((5, 3), (9, 5)):
        tempo = np.linspace(0.0, 4.0, pontos)
        resultado = metrics.calcular(
            "erro_estacionario", tempo, tempo + 1.0, tempo + 1.1, {"fracao_final": 0.5}
        )
        assert resultado.detalhes["pontos_na_janela"] == esperado


def test_erro_estacionario_warns_when_the_window_holds_a_single_point() -> None:
    resultado = metrics.calcular(
        "erro_estacionario", TEMPO, ORIGINAL, COM_10_PORCENTO, {"fracao_final": 0.01}
    )

    assert resultado.detalhes["pontos_na_janela"] == 1
    assert "um único ponto" in resultado.avisos[0]


def test_erro_estacionario_refuses_a_fraction_outside_the_range() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="fracao_final"):
        metrics.calcular(
            "erro_estacionario", TEMPO, ORIGINAL, COM_10_PORCENTO, {"fracao_final": 1.0}
        )


def test_every_metric_refuses_series_of_different_sizes() -> None:
    for nome in TODAS:
        with pytest.raises(metrics.ErroDeMetrica):
            metrics.calcular(nome, TEMPO, ORIGINAL, COM_10_PORCENTO[:-1])


def test_the_registry_rejects_a_parameter_the_metric_does_not_have() -> None:
    assert metrics.parametros_de("mape") == frozenset({"epsilon"})
    assert metrics.parametros_de("nrmse") == frozenset()
    with pytest.raises(metrics.ErroDeMetrica, match="epsilon"):
        metrics.calcular("nrmse", TEMPO, ORIGINAL, COM_10_PORCENTO, {"epsilon": 1.0})


def test_the_registry_rejects_a_metric_with_the_wrong_signature() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="tempo"):

        @metrics.registrar("assinatura_errada")
        def errada(original: np.ndarray, simplificado: np.ndarray) -> float:
            return 0.0

    with pytest.raises(metrics.ErroDeMetrica, match="padrão"):

        @metrics.registrar("sem_padrao")
        def sem_padrao(
            tempo: np.ndarray, original: np.ndarray, simplificado: np.ndarray, peso: float
        ) -> float:
            return 0.0

    assert "assinatura_errada" not in metrics.disponiveis()
    assert "sem_padrao" not in metrics.disponiveis()


def test_the_registry_rejects_a_repeated_name() -> None:
    with pytest.raises(metrics.ErroDeMetrica, match="já está registrada"):
        metrics.registrar("nrmse")(metrics.nrmse)


# --- verdict -----------------------------------------------------------------


def series_com(erro_por_variavel: dict[str, float]) -> dict[str, mapping.SerieComparada]:
    """Build comparable series whose original has a range of 2 and a constant error."""
    original = np.array([0.0, 1.0, 2.0])
    return {
        nome: mapping.SerieComparada(
            nome=nome,
            tempo=np.array([0.0, 1.0, 2.0]),
            original=original,
            simplificado=original + erro,
        )
        for nome, erro in erro_por_variavel.items()
    }


def test_verdict_approves_when_every_criterion_passes() -> None:
    criterios = [config_mod.Criterio(metrica="nrmse", limite=0.05, variaveis=["A", "C"])]
    resultado = verdict.avaliar(criterios, series_com({"A": 0.0, "C": 0.02}))

    assert resultado.aprovado is True
    assert [(c.variavel, c.passou) for c in resultado.criterios] == [("A", True), ("C", True)]
    assert resultado.porcentagem == 100.0


def test_verdict_fails_when_a_single_criterion_fails() -> None:
    criterios = [config_mod.Criterio(metrica="nrmse", limite=0.05, variaveis=["A", "C"])]
    resultado = verdict.avaliar(criterios, series_com({"A": 0.0, "C": 0.4}))

    assert resultado.aprovado is False
    assert [c.passou for c in resultado.criterios] == [True, False]
    assert resultado.porcentagem == 50.0


def test_verdict_accepts_a_value_exactly_on_the_limit() -> None:
    # The threshold is the largest accepted error, so value == limit must pass. The limit
    # is taken from the measurement itself: no float arithmetic lands exactly on 0.05.
    series = series_com({"A": 0.1})
    valor = metrics.nrmse(
        series["A"].tempo, series["A"].original, series["A"].simplificado
    ).valor
    criterios = [config_mod.Criterio(metrica="nrmse", limite=valor, variaveis=["A"])]

    resultado = verdict.avaliar(criterios, series)

    assert resultado.criterios[0].valor == valor
    assert resultado.criterios[0].passou is True


def test_verdict_rejects_a_value_just_above_the_limit() -> None:
    series = series_com({"A": 0.1})
    valor = metrics.nrmse(
        series["A"].tempo, series["A"].original, series["A"].simplificado
    ).valor
    criterios = [config_mod.Criterio(metrica="nrmse", limite=valor * 0.999, variaveis=["A"])]

    assert verdict.avaliar(criterios, series).criterios[0].passou is False


def test_the_core_selector_evaluates_every_core_variable() -> None:
    criterios = [config_mod.Criterio(metrica="nrmse", limite=0.05, variaveis="core")]

    resultado = verdict.avaliar(
        criterios, series_com({"A": 0.0, "C": 0.02, "D": 0.4}), core=["A", "C"]
    )

    # D is not core, so it is not evaluated and does not drag the verdict down.
    assert [c.variavel for c in resultado.criterios] == ["A", "C"]
    assert resultado.aprovado is True



# --- report ------------------------------------------------------------------


def test_report_writes_the_json(tmp_path: Path) -> None:
    criterios = [config_mod.Criterio(metrica="nrmse", limite=0.05, variaveis=["A"])]
    veredito = verdict.avaliar(criterios, series_com({"A": 0.0}))

    caminho = report.salvar_json(veredito, tmp_path / "saida")

    assert caminho == tmp_path / "saida" / "resultado.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["aprovado"] is True
    assert dados["porcentagem"] == 100.0
    assert dados["criterios"] == [
        {
            "metrica": "nrmse",
            "variavel": "A",
            "valor": 0.0,
            "limite": 0.05,
            "resultado": "passou",
            "descricao": "RMSE normalizado pela amplitude do original (fração: 0,05 = 5%)",
            "avisos": [],
            "detalhes": {},
        }
    ]
    assert dados["avisos"] == []


def test_the_json_carries_the_warnings_of_the_metrics(tmp_path: Path) -> None:
    # The original starts at zero, so mape has to drop that point and say so; the warning
    # has to reach the JSON, named after the variable it is about.
    series = series_com({"A": 0.1})
    criterios = [config_mod.Criterio(metrica="mape", limite=1.0, variaveis=["A"])]
    veredito = verdict.avaliar(criterios, series)

    caminho = report.salvar_json(veredito, tmp_path / "saida")
    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["criterios"][0]["detalhes"]["pontos_excluidos"] == 1
    assert len(dados["criterios"][0]["avisos"]) == 1
    assert dados["avisos"][0].startswith("A: mape:")
