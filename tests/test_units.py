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


# --- metrics -----------------------------------------------------------------


def test_nrmse_is_zero_for_identical_series() -> None:
    serie = np.array([1.0, 2.0, 3.0])
    assert metrics.nrmse(serie, serie) == 0.0


def test_nrmse_is_the_rmse_over_the_range_of_the_original() -> None:
    original = np.array([0.0, 2.0, 4.0])  # range of 4
    simplificado = original + 1.0  # constant error of 1 -> rmse of 1
    assert metrics.nrmse(original, simplificado) == pytest.approx(0.25)


def test_nrmse_normalizes_by_the_original_not_the_simplified() -> None:
    original = np.array([0.0, 1.0, 2.0])  # range of 2
    simplificado = np.array([0.0, 10.0, 20.0])
    esperado = float(np.sqrt(np.mean((original - simplificado) ** 2)) / 2.0)
    assert metrics.nrmse(original, simplificado) == pytest.approx(esperado)


def test_nrmse_refuses_a_constant_original() -> None:
    constante = np.array([2.0, 2.0, 2.0])
    with pytest.raises(metrics.ErroDeMetrica):
        metrics.nrmse(constante, np.array([2.0, 2.1, 2.0]))


def test_the_registry_exposes_nrmse() -> None:
    assert metrics.obter("nrmse") is metrics.nrmse
    with pytest.raises(metrics.ErroDeMetrica, match="mape"):
        metrics.obter("mape")


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
    valor = metrics.nrmse(series["A"].original, series["A"].simplificado)
    criterios = [config_mod.Criterio(metrica="nrmse", limite=valor, variaveis=["A"])]

    resultado = verdict.avaliar(criterios, series)

    assert resultado.criterios[0].valor == valor
    assert resultado.criterios[0].passou is True


def test_verdict_rejects_a_value_just_above_the_limit() -> None:
    series = series_com({"A": 0.1})
    valor = metrics.nrmse(series["A"].original, series["A"].simplificado)
    criterios = [config_mod.Criterio(metrica="nrmse", limite=valor * 0.999, variaveis=["A"])]

    assert verdict.avaliar(criterios, series).criterios[0].passou is False


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
        }
    ]
