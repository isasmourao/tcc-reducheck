"""Reasons of the failures and warnings about misleading metrics (issue #19, T15).

Every series here is built by hand, so where the error is -- only at the start, only at the
end, spread out, in a single point -- is known before anything is computed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reducheck import config as config_mod
from reducheck import mapping, metrics, report, verdict

#: 100 points, t = 0, 1, ..., 99: the first 20% of the time is t <= 19.8, the last t >= 79.2.
TEMPO = np.arange(100.0)
UM = np.ones(100)


def com_erro_em(mascara: np.ndarray, tamanho: float = 0.1) -> np.ndarray:
    """Return a simplified series equal to 1 except where ``mascara`` holds, 1 + tamanho."""
    return np.where(mascara, 1.0 + tamanho, 1.0)


def serie(simplificado: np.ndarray, original: np.ndarray = UM) -> mapping.SerieComparada:
    return mapping.SerieComparada(
        nome="M", tempo=TEMPO, original=original, simplificado=simplificado
    )


def avaliar(metrica: str, limite: float, simplificado: np.ndarray) -> verdict.Veredito:
    criterio = config_mod.Criterio(metrica=metrica, limite=limite, variaveis=["M"])
    return verdict.avaliar([criterio], {"M": serie(simplificado)})


# --- pointwise error of each metric -------------------------------------------


@pytest.mark.parametrize("nome", ["nrmse", "mape", "erro_max_abs", "erro_max_rel"])
def test_the_pointwise_error_aggregates_back_to_the_value(nome: str) -> None:
    # A ramp as the original, so nrmse has a range to normalize by.
    original = np.linspace(1.0, 3.0, 100)
    simplificado = original + np.sin(TEMPO) * 0.1
    resultado = metrics.calcular(nome, TEMPO, original, simplificado)

    assert resultado.erro_pontual is not None
    todos = np.ones(100, dtype=bool)
    agregado = metrics.agregar(resultado.erro_pontual, resultado.agregacao, todos)
    assert agregado == pytest.approx(resultado.valor, rel=1e-12)


def test_the_excluded_points_have_no_pointwise_error() -> None:
    original = np.r_[0.0, np.ones(99)]
    resultado = metrics.mape(TEMPO, original, original * 1.1)

    assert np.isnan(resultado.erro_pontual[0])
    assert not np.isnan(resultado.erro_pontual[1:]).any()


def test_erro_estacionario_has_no_pointwise_error() -> None:
    # It compares two averages, which is not a sum over points: there is no window to find.
    resultado = metrics.erro_estacionario(TEMPO, UM, UM * 1.1)
    assert resultado.erro_pontual is None


# --- where the error is ------------------------------------------------------


def test_an_error_only_at_the_start_is_classified_as_transient() -> None:
    diagnostico = avaliar("mape", 0.005, com_erro_em(TEMPO < 10)).criterios[0].diagnostico

    assert diagnostico is not None
    assert diagnostico.fase == verdict.TRANSIENTE
    # 80% of ten equal points is eight points, the first eight.
    assert (diagnostico.inicio, diagnostico.fim) == (0.0, 7.0)
    assert diagnostico.fracao_do_erro == pytest.approx(0.8)
    assert diagnostico.valor_estacionario == 0.0
    assert diagnostico.valor_transiente == pytest.approx(0.1 * 10 / 20)


def test_an_error_only_at_the_end_is_classified_as_steady_state() -> None:
    diagnostico = avaliar("mape", 0.005, com_erro_em(TEMPO >= 90)).criterios[0].diagnostico

    assert diagnostico is not None
    assert diagnostico.fase == verdict.ESTACIONARIO
    assert 90.0 <= diagnostico.inicio <= diagnostico.fim <= 99.0
    assert diagnostico.valor_transiente == 0.0
    assert diagnostico.valor_estacionario == pytest.approx(0.1 * 10 / 20)


def test_an_error_spread_over_the_run_is_classified_as_such() -> None:
    diagnostico = avaliar("mape", 0.05, UM * 1.1).criterios[0].diagnostico

    assert diagnostico is not None
    assert diagnostico.fase == verdict.AO_LONGO
    assert diagnostico.valor_transiente == pytest.approx(0.1)
    assert diagnostico.valor_estacionario == pytest.approx(0.1)


def test_the_window_is_the_shortest_one_holding_the_share() -> None:
    # A small error everywhere and a large one in t in [40, 49]: the large one holds well
    # over 80% of the total, so the window is inside it, not the whole run.
    simplificado = np.where((TEMPO >= 40) & (TEMPO < 50), 2.0, 1.001)
    diagnostico = avaliar("erro_max_abs", 0.1, simplificado).criterios[0].diagnostico

    assert diagnostico is not None
    assert 40.0 <= diagnostico.inicio <= diagnostico.fim <= 49.0
    assert diagnostico.fase == verdict.AO_LONGO


def test_the_window_of_nrmse_is_taken_on_the_squared_error() -> None:
    original = np.linspace(0.0, 1.0, 100)
    simplificado = original + np.where(TEMPO < 5, 0.3, 0.0)
    diagnostico = avaliar_nrmse(original, simplificado)

    assert diagnostico is not None
    assert diagnostico.fase == verdict.TRANSIENTE
    assert diagnostico.valor_estacionario == 0.0


def avaliar_nrmse(
    original: np.ndarray, simplificado: np.ndarray
) -> verdict.Diagnostico | None:
    criterio = config_mod.Criterio(metrica="nrmse", limite=0.01, variaveis=["M"])
    veredito = verdict.avaliar([criterio], {"M": serie(simplificado, original)})
    return veredito.criterios[0].diagnostico


def test_an_item_that_passed_has_no_diagnosis() -> None:
    assert avaliar("mape", 0.5, UM * 1.1).criterios[0].diagnostico is None


def test_a_metric_without_pointwise_error_has_no_diagnosis() -> None:
    item = avaliar("erro_estacionario", 0.01, UM * 1.1).criterios[0]
    assert not item.passou
    assert item.diagnostico is None


def test_the_diagnosis_comes_from_the_function_the_verdict_uses() -> None:
    erro = np.where(TEMPO >= 90, 1.0, 0.0)
    diagnostico = verdict.diagnosticar(TEMPO, erro, "media")

    assert diagnostico is not None
    assert diagnostico.fase == verdict.ESTACIONARIO


def test_a_zero_error_has_no_window_to_find() -> None:
    assert verdict.diagnosticar(TEMPO, np.zeros(100), "media") is None


# --- warnings about misleading metrics ----------------------------------------


def test_mape_warns_when_many_points_are_close_to_zero() -> None:
    # 10 of 100 points at 0.5% of the peak: above the exclusion threshold (1e-6 of the
    # peak), so they are divided by, and below 1% of the peak, so they are "close to zero".
    original = np.r_[np.full(10, 0.005), np.ones(90)]
    resultado = metrics.mape(TEMPO, original, original + 0.001)

    avisos = [aviso for aviso in resultado.avisos if "perto de zero" in aviso]
    assert len(avisos) == 1
    assert "10 de 100 pontos (10%)" in avisos[0]


def test_mape_does_not_warn_when_few_points_are_close_to_zero() -> None:
    # 5 of 100 is exactly 5%, and the warning is for more than 5%.
    original = np.r_[np.full(5, 0.005), np.ones(95)]
    resultado = metrics.mape(TEMPO, original, original + 0.001)

    assert not [aviso for aviso in resultado.avisos if "perto de zero" in aviso]


def test_mape_does_not_count_the_excluded_points_as_close_to_zero() -> None:
    # Ten exact zeros are left out of the mean, so they cannot mislead it: the warning about
    # exclusion is the one that applies, not the one about points close to zero.
    original = np.r_[np.zeros(10), np.ones(90)]
    resultado = metrics.mape(TEMPO, original, original + 0.001)

    assert resultado.detalhes["pontos_perto_de_zero"] == 0
    assert len(resultado.avisos) == 1
    assert "foram excluídos" in resultado.avisos[0]


def test_nrmse_warns_when_a_single_point_dominates_the_squared_error() -> None:
    original = np.linspace(0.0, 1.0, 100)
    simplificado = original.copy()
    simplificado[30] += 0.5
    simplificado[60:] += 0.01
    resultado = metrics.nrmse(TEMPO, original, simplificado)

    assert len(resultado.avisos) == 1
    assert "t = 30" in resultado.avisos[0]
    assert resultado.detalhes["fracao_do_maior_ponto"] > 0.5


def test_nrmse_does_not_warn_when_the_error_is_spread_out() -> None:
    original = np.linspace(0.0, 1.0, 100)
    resultado = metrics.nrmse(TEMPO, original, original + 0.01)

    assert resultado.avisos == ()


# --- the sentence -------------------------------------------------------------


def test_the_reason_of_a_transient_error_reads_as_in_the_issue() -> None:
    veredito = avaliar("mape", 0.005, com_erro_em(TEMPO < 10))

    assert report.razoes(veredito) == [
        "mape em M falhou: 1% (limite 0,5%, 100% acima do limite), erro concentrado "
        "entre t = 0 e t = 7 (transiente); no estado estacionário o erro é 0%."
    ]


def test_the_reason_of_a_steady_state_error_gives_the_transient_value() -> None:
    (razao,) = report.razoes(avaliar("mape", 0.005, com_erro_em(TEMPO >= 90)))

    assert "(estado estacionário); no transiente o erro é 0%." in razao


def test_the_reason_of_a_spread_error_gives_both_values() -> None:
    (razao,) = report.razoes(avaliar("mape", 0.05, UM * 1.2))

    assert "(ao longo da simulação)" in razao
    assert "no transiente o erro é 20% e no estado estacionário, 20%." in razao


def test_the_reason_of_an_absolute_metric_keeps_the_unit_of_the_variable() -> None:
    (razao,) = report.razoes(avaliar("erro_max_abs", 0.05, com_erro_em(TEMPO < 10)))

    assert razao.startswith("erro_max_abs em M falhou: 0,1 (limite 0,05, 100% acima do limite)")
    assert razao.endswith(" O pior ponto está em t = 0.")


def test_a_metric_without_a_window_still_has_a_reason() -> None:
    (razao,) = report.razoes(avaliar("erro_estacionario", 0.01, UM * 1.1))

    assert razao.startswith("erro_estacionario em M falhou: 10% (limite 1%")
    assert "concentrado" not in razao


def test_the_reasons_are_in_the_json(tmp_path: Path) -> None:
    veredito = avaliar("mape", 0.005, com_erro_em(TEMPO < 10))
    dados = json.loads(report.salvar_json(veredito, tmp_path).read_text(encoding="utf-8"))

    assert dados["razoes"] == report.razoes(veredito)
    (item,) = dados["criterios"]
    assert item["razao"] == dados["razoes"][0]
    assert item["diagnostico"]["fase"] == "transiente"
    assert item["diagnostico"]["inicio"] == 0.0
    assert item["diagnostico"]["fim"] == 7.0


def test_a_passed_item_has_no_reason_in_the_json(tmp_path: Path) -> None:
    veredito = avaliar("mape", 0.5, UM * 1.1)
    dados = json.loads(report.salvar_json(veredito, tmp_path).read_text(encoding="utf-8"))

    assert dados["razoes"] == []
    assert dados["criterios"][0]["razao"] is None
    assert dados["criterios"][0]["diagnostico"] is None
