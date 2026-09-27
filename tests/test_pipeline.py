"""End-to-end tests of the minimal pipeline, on the toy pairs of tests/fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import reducheck

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: (configuration file, expected verdict, worst NRMSE, report names), from fixtures/README.md.
PAIRS = [
    ("config_qssa_ok.yaml", True, 0.00072, ["A", "C"]),
    ("config_qssa_fail.yaml", False, 0.52006, ["A", "C"]),
    ("config_aggregation.yaml", True, 0.00523, ["X"]),
]

#: The two pairs that share the A -> B -> C chain, and therefore the A variable.
QSSA_PAIRS = [par for par in PAIRS if par[0].startswith("config_qssa")]


def prepare(tmp_path: Path, config_name: str) -> Path:
    """Copy one configuration and every fixture model into tmp_path, return the config."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for path in [*FIXTURES_DIR.glob("*.xml"), FIXTURES_DIR / config_name]:
        shutil.copy(path, tmp_path / path.name)
    return tmp_path / config_name


@pytest.mark.parametrize(("config_name", "aprovado", "pior", "variaveis"), PAIRS)
def test_verdict_matches_the_known_one(
    tmp_path: Path, config_name: str, aprovado: bool, pior: float, variaveis: list[str]
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, config_name))

    assert resultado.aprovado is aprovado
    assert max(c.valor for c in resultado.criterios) == pytest.approx(pior, abs=1e-4)


@pytest.mark.parametrize(("config_name", "aprovado", "pior", "variaveis"), PAIRS)
def test_json_records_every_criterion(
    tmp_path: Path, config_name: str, aprovado: bool, pior: float, variaveis: list[str]
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, config_name))

    assert resultado.caminho_json == tmp_path / "resultados" / "resultado.json"
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))

    assert dados["aprovado"] is aprovado
    assert [c["variavel"] for c in dados["criterios"]] == variaveis
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
    for config_name, _, _, _ in QSSA_PAIRS:
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


# --- sum mapping, weighted sum and core selection (issue #10) ----------------


def test_the_aggregation_pair_needs_the_sum_mapping(tmp_path: Path) -> None:
    # The whole point of the pair: X of the simplified model corresponds to X1 + X2, and
    # neither of them alone. Comparing against X1 only would be far above the limit.
    resultado = reducheck.verificar(prepare(tmp_path, "config_aggregation.yaml"))

    assert resultado.aprovado is True
    assert [c.variavel for c in resultado.criterios] == ["X"]
    assert resultado.criterios[0].valor == pytest.approx(0.00523, abs=1e-4)


def test_unit_weights_give_the_same_number_as_a_plain_sum(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_aggregation.yaml")
    soma = reducheck.verificar(config).criterios[0].valor

    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "original: [X1, X2]", "original: {X1: 1.0, X2: 1.0}"
        ),
        encoding="utf-8",
    )
    ponderada = reducheck.verificar(config).criterios[0].valor

    assert ponderada == soma


def test_a_wrong_weight_moves_the_number(tmp_path: Path) -> None:
    # Guards against weights being parsed and then ignored: halving X2 must not be free.
    config = prepare(tmp_path, "config_aggregation.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "original: [X1, X2]", "original: {X1: 1.0, X2: 0.5}"
        ),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(config)

    assert resultado.aprovado is False
    assert resultado.criterios[0].valor > 0.05


def test_the_core_selector_picks_the_criterion_variables(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    # C stops being core, so 'variaveis: core' must evaluate A alone.
    config.write_text(
        config.read_text(encoding="utf-8")
        .replace("    simplificado: C", "    simplificado: C\n    core: false")
        .replace("variaveis: [A, C]", "variaveis: core"),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(config)

    assert [c.variavel for c in resultado.criterios] == ["A"]


#: NRMSE of B, the variable the QSSA eliminates, measured on the qssa_ok pair. It is above
#: the 0.05 limit, and all of it comes from t = 0: see fixtures/README.md.
NRMSE_DE_B = 0.05069


def test_the_eliminated_variable_is_read_from_the_assignment_rule(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    # B is a species in the original and an assignment rule in the simplified model; the
    # mapping has to reach it on both sides.
    config.write_text(
        config.read_text(encoding="utf-8")
        .replace("  - nome: C", "  - nome: B\n    original: B\n    simplificado: B\n  - nome: C")
        .replace("variaveis: [A, C]", "variaveis: [A, B, C]"),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(config)
    por_variavel = {c.variavel: c for c in resultado.criterios}

    assert por_variavel["B"].valor == pytest.approx(NRMSE_DE_B, abs=1e-4)
    # The QSSA is faithful in A and C but not in B itself, which the initial layer spoils.
    assert por_variavel["B"].passou is False
    assert por_variavel["A"].passou and por_variavel["C"].passou
