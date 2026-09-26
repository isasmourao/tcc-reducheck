"""Unit tests of the individual pipeline steps."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reducheck import config as config_mod
from reducheck import mapping, metrics, report, simulation, verdict

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --- config ------------------------------------------------------------------


def test_config_reads_every_supported_field() -> None:
    cfg = config_mod.carregar(FIXTURES_DIR / "config_qssa_ok.yaml")

    assert cfg.versao == 1
    assert cfg.modelos.original == FIXTURES_DIR / "qssa_ok_original.xml"
    assert cfg.modelos.simplificado == FIXTURES_DIR / "qssa_ok_simplified.xml"
    assert (cfg.simulacao.t_inicio, cfg.simulacao.t_fim, cfg.simulacao.pontos) == (0.0, 40.0, 401)
    assert (cfg.simulacao.tol_relativa, cfg.simulacao.tol_absoluta) == (1e-8, 1e-10)
    assert [(v.nome, v.original, v.simplificado) for v in cfg.variaveis] == [
        ("A", "A", "A"),
        ("C", "C", "C"),
    ]
    assert [(c.metrica, c.limite, c.variaveis) for c in cfg.criterios] == [
        ("nrmse", 0.05, ["A", "C"])
    ]
    assert cfg.relatorio.pasta == FIXTURES_DIR / "resultados"


BASE = """
versao: 1
modelos:
  original: qssa_ok_original.xml
  simplificado: qssa_ok_simplified.xml
simulacao:
  t_fim: 40
  pontos: 401
variaveis:
  - nome: A
    original: A
    simplificado: A
criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: [A]
"""


def escrever(tmp_path: Path, texto: str) -> Path:
    """Write one configuration into tmp_path, next to copies of the fixture models."""
    for modelo in FIXTURES_DIR.glob("qssa_ok_*.xml"):
        (tmp_path / modelo.name).write_bytes(modelo.read_bytes())
    caminho = tmp_path / "config.yaml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_config_defaults_match_the_product_document(tmp_path: Path) -> None:
    cfg = config_mod.carregar(escrever(tmp_path, BASE))

    assert cfg.simulacao.t_inicio == 0.0
    assert cfg.simulacao.solver == "cvode"
    assert cfg.simulacao.tol_relativa == 1e-8
    assert cfg.simulacao.tol_absoluta == 1e-10
    assert cfg.relatorio.pasta == tmp_path / "resultados"


@pytest.mark.parametrize(
    ("de", "para"),
    [
        # Not supported by this version of the pipeline.
        ("metrica: nrmse", "metrica: mape"),
        # Criterion pointing at a variable that was never declared.
        ("variaveis: [A]", "variaveis: [Z]"),
        # Sum mapping: a later task.
        ("original: A\n    simplificado: A", "original: [A, B]\n    simplificado: A"),
        ("pontos: 401", "pontos: 1"),
    ],
)
def test_config_rejects_what_is_not_supported_yet(tmp_path: Path, de: str, para: str) -> None:
    with pytest.raises(config_mod.ErroDeConfiguracao):
        config_mod.carregar(escrever(tmp_path, BASE.replace(de, para)))


def test_config_reports_a_missing_model_file(tmp_path: Path) -> None:
    texto = BASE.replace("qssa_ok_original.xml", "nao_existe.xml")
    with pytest.raises(config_mod.ErroDeConfiguracao, match="nao_existe.xml"):
        config_mod.carregar(escrever(tmp_path, texto))


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
