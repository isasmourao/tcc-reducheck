"""End-to-end tests of the minimal pipeline, on the toy pairs of tests/fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import reducheck

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: (configuration file, expected verdict, worst expected NRMSE), from fixtures/README.md.
PAIRS = [
    ("config_qssa_ok.yaml", True, 0.00072),
    ("config_qssa_fail.yaml", False, 0.52006),
]


def prepare(tmp_path: Path, config_name: str) -> Path:
    """Copy one configuration and every fixture model into tmp_path, return the config."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for path in [*FIXTURES_DIR.glob("*.xml"), FIXTURES_DIR / config_name]:
        shutil.copy(path, tmp_path / path.name)
    return tmp_path / config_name


@pytest.mark.parametrize(("config_name", "aprovado", "pior"), PAIRS)
def test_verdict_matches_the_known_one(
    tmp_path: Path, config_name: str, aprovado: bool, pior: float
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, config_name))

    assert resultado.aprovado is aprovado
    assert max(c.valor for c in resultado.criterios) == pytest.approx(pior, abs=1e-4)


@pytest.mark.parametrize(("config_name", "aprovado", "pior"), PAIRS)
def test_json_records_every_criterion(
    tmp_path: Path, config_name: str, aprovado: bool, pior: float
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, config_name))

    assert resultado.caminho_json == tmp_path / "resultados" / "resultado.json"
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))

    assert dados["aprovado"] is aprovado
    assert [c["variavel"] for c in dados["criterios"]] == ["A", "C"]
    for criterio in dados["criterios"]:
        assert criterio["metrica"] == "nrmse"
        assert criterio["limite"] == 0.05
        assert criterio["resultado"] == ("passou" if criterio["valor"] <= 0.05 else "falhou")


#: A has the same equation in both models, so its error is only integration noise.
#: It is not zero: CVODE steps differently on the two systems (measured ~3e-8 with the
#: tolerances of the configurations). Four orders of magnitude below the 0.05 limit.
RUIDO_NUMERICO = 1e-6


def test_the_A_variable_passes_in_both_pairs(tmp_path: Path) -> None:
    # A is untouched by the reduction, so only C tells the two pairs apart.
    # Guards against a verdict that ignores C.
    for config_name, _, _ in PAIRS:
        resultado = reducheck.verificar(prepare(tmp_path / config_name, config_name))
        por_variavel = {c.variavel: c for c in resultado.criterios}
        assert por_variavel["A"].passou
        assert por_variavel["A"].valor < RUIDO_NUMERICO


def test_running_twice_gives_the_same_result(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    primeiro = reducheck.verificar(config)
    valores = [c.valor for c in primeiro.criterios]
    segundo = reducheck.verificar(config)
    assert [c.valor for c in segundo.criterios] == valores


def test_renamed_variable_is_mapped(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    # C in the original is the same species as C in the simplified model; declaring
    # it under another report name must not change the number.
    config.write_text(
        config.read_text(encoding="utf-8").replace("  - nome: C\n", "  - nome: produto\n").replace(
            "variaveis: [A, C]", "variaveis: [A, produto]"
        ),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(config)
    por_variavel = {c.variavel: c.valor for c in resultado.criterios}
    assert por_variavel["produto"] == pytest.approx(0.00072, abs=1e-4)
