"""The reproducibility package of a run: series.csv, config_usada.yaml and ``execucao``."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import roadrunner
import scipy
from test_pipeline import FIXTURES_DIR, prepare
from test_report import com_formatos

import reducheck
from reducheck import config as config_mod
from reducheck import report


def ler_csv(caminho: Path) -> tuple[list[str], np.ndarray]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.reader(arquivo))
    return linhas[0], np.array(linhas[1:], dtype=float)


def sem_data(caminho: Path) -> dict:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    del dados["execucao"]["data"]
    return dados


# --- series.csv ---------------------------------------------------------------


def test_the_csv_has_time_and_both_series_of_every_mapped_variable(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))

    assert resultado.reproducao["series"] == tmp_path / "resultados" / "series.csv"
    cabecalho, valores = ler_csv(resultado.reproducao["series"])
    assert cabecalho == ["tempo", "A_original", "A_simplificado", "C_original", "C_simplificado"]
    assert valores.shape == (401, 5)


def test_the_csv_keeps_every_digit_of_the_series(tmp_path: Path) -> None:
    # Whoever redoes the analysis from the CSV must get the same numbers, not rounded ones.
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))
    _, valores = ler_csv(resultado.reproducao["series"])

    serie = resultado.series["C"]
    np.testing.assert_array_equal(valores[:, 0], serie.tempo)
    np.testing.assert_array_equal(valores[:, 3], serie.original)
    np.testing.assert_array_equal(valores[:, 4], serie.simplificado)


def test_a_summed_variable_goes_to_the_csv_already_summed(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_aggregation.yaml"))
    cabecalho, valores = ler_csv(resultado.reproducao["series"])

    assert cabecalho == ["tempo", "X_original", "X_simplificado"]
    np.testing.assert_array_equal(valores[:, 1], resultado.series["X"].original)


# --- config_usada.yaml --------------------------------------------------------


def test_the_used_configuration_is_written_even_when_only_json_is_asked(
    tmp_path: Path,
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))

    assert resultado.reproducao["config"] == tmp_path / "resultados" / "config_usada.yaml"
    texto = resultado.reproducao["config"].read_text(encoding="utf-8")
    # The defaults the user left out are written explicitly.
    assert "formatos:" in texto and "niveis: 3" in texto and "nao_negativas: true" in texto


def test_the_used_configuration_loads_back_into_the_same_configuration(
    tmp_path: Path,
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))

    recarregada = config_mod.carregar(resultado.reproducao["config"])
    assert recarregada == resultado.configuracao


def test_the_used_configuration_runs_from_another_folder(tmp_path: Path) -> None:
    # The model paths are absolute, so the copy works without the original YAML beside it.
    primeiro = reducheck.verificar(prepare(tmp_path / "a", "config_qssa_ok.yaml"))
    copia = tmp_path / "b" / "config_usada.yaml"
    copia.parent.mkdir()
    copia.write_bytes(primeiro.reproducao["config"].read_bytes())

    segundo = reducheck.verificar(copia, pasta_de_saida=tmp_path / "b" / "saida")
    assert [c.valor for c in segundo.criterios] == [c.valor for c in primeiro.criterios]


def test_the_used_configuration_carries_date_and_versions_as_comments(
    tmp_path: Path,
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))
    texto = resultado.reproducao["config"].read_text(encoding="utf-8")

    cabecalho = [linha for linha in texto.splitlines() if linha.startswith("#")]
    assert any(f"reducheck {reducheck.__version__}" in linha for linha in cabecalho)
    assert any("Data:" in linha for linha in cabecalho)


# --- the execucao block -------------------------------------------------------


def test_the_json_records_the_versions_of_the_libraries(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))
    execucao = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))["execucao"]

    versoes = execucao["versoes"]
    assert versoes["reducheck"] == reducheck.__version__
    assert versoes["libroadrunner"] == roadrunner.__version__
    assert versoes["numpy"] == np.__version__
    assert versoes["scipy"] == scipy.__version__
    assert versoes["python"].count(".") == 2


def test_the_json_records_the_sha256_of_both_models(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qssa_ok.yaml"))
    modelos = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))["execucao"][
        "modelos"
    ]

    for papel, arquivo in [
        ("original", "qssa_ok_original.xml"),
        ("simplificado", "qssa_ok_simplified.xml"),
    ]:
        esperado = hashlib.sha256((FIXTURES_DIR / arquivo).read_bytes()).hexdigest()
        assert modelos[papel]["sha256"] == esperado
        assert Path(modelos[papel]["arquivo"]).name == arquivo


def test_the_report_and_the_json_carry_the_same_date(tmp_path: Path) -> None:
    resultado = reducheck.verificar(
        com_formatos(prepare(tmp_path, "config_qssa_ok.yaml"), "[html, json]")
    )
    data = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))["execucao"]["data"]
    html = resultado.caminhos["html"].read_text(encoding="utf-8")

    assert report.data_legivel(data) in html


def test_a_changed_model_changes_the_hash(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    antes = reducheck.verificar(config)
    hash_antes = json.loads(antes.caminho_json.read_text(encoding="utf-8"))["execucao"]
    modelo = tmp_path / "qssa_ok_simplified.xml"
    modelo.write_text(modelo.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    depois = reducheck.verificar(config)
    hash_depois = json.loads(depois.caminho_json.read_text(encoding="utf-8"))["execucao"]

    assert hash_antes["modelos"]["original"] == hash_depois["modelos"]["original"]
    assert hash_antes["modelos"]["simplificado"] != hash_depois["modelos"]["simplificado"]


# --- determinism --------------------------------------------------------------


@pytest.mark.parametrize("config_name", ["config_qssa_ok.yaml", "config_qssa_fail.yaml"])
def test_two_runs_give_identical_json_except_for_the_date(
    tmp_path: Path, config_name: str
) -> None:
    config = prepare(tmp_path, config_name)
    primeiro = reducheck.verificar(config, pasta_de_saida=tmp_path / "um")
    segundo = reducheck.verificar(config, pasta_de_saida=tmp_path / "dois")

    um, dois = sem_data(primeiro.caminho_json), sem_data(segundo.caminho_json)
    # The output folder is not in the JSON, so pointing two runs at two folders is fair.
    assert um == dois
    assert (
        primeiro.reproducao["series"].read_bytes() == segundo.reproducao["series"].read_bytes()
    )
