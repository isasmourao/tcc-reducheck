"""End-to-end tests of the minimal pipeline, on the toy pairs of tests/fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import reducheck
from reducheck import config as config_mod
from reducheck import metrics

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


# --- pluggable metrics (issue #11) -------------------------------------------


@metrics.registrar("erro_no_ultimo_ponto")
def erro_no_ultimo_ponto(
    tempo: np.ndarray,
    original: np.ndarray,
    simplificado: np.ndarray,
    escala: float = 1.0,
) -> metrics.ResultadoDeMetrica:
    """A metric defined outside the package, to prove the registry is really pluggable."""
    return metrics.ResultadoDeMetrica(
        valor=escala * abs(float(original[-1]) - float(simplificado[-1])),
        descricao="erro absoluto no último ponto, definido num arquivo de teste",
    )


def test_a_metric_registered_outside_the_package_is_usable_from_the_yaml(
    tmp_path: Path,
) -> None:
    # Nothing in src/reducheck knows this metric exists: it is registered above, in this
    # file, and the configuration cites it by name like any other.
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  - metrica: nrmse\n    limite: 0.05\n    variaveis: [A, C]",
            "  - metrica: erro_no_ultimo_ponto\n    limite: 0.05\n    variaveis: [A, C]\n"
            "    parametros:\n      escala: 2.0",
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    por_variavel = {c.variavel: c for c in resultado.criterios}
    assert set(por_variavel) == {"A", "C"}
    assert por_variavel["A"].metrica == "erro_no_ultimo_ponto"
    assert por_variavel["A"].descricao.startswith("erro absoluto no último ponto")
    # A is identical in both models, so the error at the last point is numerical noise.
    assert por_variavel["A"].valor < RUIDO_NUMERICO
    assert resultado.aprovado is True


def test_an_unknown_parameter_of_a_metric_stops_the_run(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "    variaveis: [A, C]", "    variaveis: [A, C]\n    parametros:\n      epsilon: 1.0"
        ),
        encoding="utf-8",
    )
    with pytest.raises(config_mod.ErroDeConfiguracao, match="parametros"):
        reducheck.verificar(config)


#: Values of the four metrics of the MVP on the C variable of the qssa_ok pair, measured
#: with the tolerances of the configuration (see fixtures/README.md).
METRICAS_EM_C = {
    "nrmse": 0.00072,
    "mape": 0.00277,
    "erro_max_abs": 0.01971,
    "erro_max_rel": 0.24695,
    "erro_estacionario": 0.00004,
}


def test_the_mvp_metrics_reproduce_the_recorded_values(tmp_path: Path) -> None:
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    criterios = "\n".join(
        f"  - metrica: {nome}\n    limite: 1.0\n    variaveis: [C]" for nome in METRICAS_EM_C
    )
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  - metrica: nrmse\n    limite: 0.05\n    variaveis: [A, C]", criterios
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    itens = {c.metrica: c for c in resultado.criterios}
    for nome, esperado in METRICAS_EM_C.items():
        assert itens[nome].valor == pytest.approx(esperado, abs=1e-5), nome

    # C starts at zero, so the relative metrics have to drop that one point and say so.
    assert itens["mape"].detalhes["pontos_excluidos"] == 1
    assert "1 de 401" in itens["mape"].avisos[0]
    # The same pair passes in nrmse and is 24,7% wrong at its worst point (t = 0,1, the
    # initial layer of the QSSA): the metrics answer different questions, on purpose.
    assert itens["nrmse"].valor < 0.05 < itens["erro_max_rel"].valor
    assert itens["erro_max_rel"].detalhes["instante"] == pytest.approx(0.1)


# --- simulation conditions (issue #12) ---------------------------------------

#: Reference numerical noise of each pair, per report variable (see fixtures/README.md).
RUIDO_DOS_PARES = {
    "config_qssa_ok.yaml": {"A": 9.53e-07, "C": 9.56e-07},
    "config_qssa_fail.yaml": {"A": 2.50e-07, "C": 2.22e-07},
    "config_aggregation.yaml": {"X": 1.59e-06},
}


@pytest.mark.parametrize("config_name", list(RUIDO_DOS_PARES))
def test_the_run_measures_and_records_the_reference_numerical_noise(
    tmp_path: Path, config_name: str
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, config_name))

    esperado = RUIDO_DOS_PARES[config_name]
    assert set(resultado.ruido.por_variavel) == set(esperado)
    for nome, valor in esperado.items():
        assert resultado.ruido.por_variavel[nome] == pytest.approx(valor, rel=0.05)
    # Four orders of magnitude below the 0.05 threshold of the fixtures: nothing here is
    # measuring the solver.
    assert resultado.ruido.maximo < 0.05 / 10
    assert resultado.avisos[0].startswith("Ruído numérico de referência")
    assert len(resultado.avisos) == 1

    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))
    assert dados["ruido_numerico"]["maximo"] == resultado.ruido.maximo
    assert dados["avisos"][0] == resultado.avisos[0]


def test_a_threshold_under_ten_times_the_noise_is_warned_about_without_failing(
    tmp_path: Path,
) -> None:
    # A is identical in both models, so a threshold at the level of the noise still passes:
    # the warning is there to say the number means nothing, not to change the verdict.
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "    limite: 0.05\n    variaveis: [A, C]",
            "    limite: 1e-6\n    variaveis: [A]",
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    assert resultado.aprovado is True
    assert len(resultado.avisos) == 2
    assert "o limite 1e-06 é menor que 10× o ruído numérico" in resultado.avisos[1]


def test_an_override_turns_the_approved_pair_into_the_failing_one(tmp_path: Path) -> None:
    # qssa_fail is qssa_ok with k2 = 0.05 in both models and nothing else changed, so
    # overriding k2 has to reproduce its recorded NRMSE (0.52006) and its verdict.
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  tol_absoluta: 1e-10",
            "  tol_absoluta: 1e-10\n  sobrescrever:\n    parametros:\n      k2: 0.05",
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    assert resultado.aprovado is False
    por_variavel = {c.variavel: c.valor for c in resultado.criterios}
    assert por_variavel["C"] == pytest.approx(0.52006, abs=1e-4)


def test_an_override_of_one_model_alone_changes_only_that_model(tmp_path: Path) -> None:
    # Same k2 = 0.05, but only in the simplified model: now the two models do not even
    # share the parameter, and A, which was identical, stays identical.
    config = prepare(tmp_path, "config_qssa_ok.yaml")
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "  tol_absoluta: 1e-10",
            "  tol_absoluta: 1e-10\n  sobrescrever:\n    simplificado:\n"
            "      parametros:\n        k2: 0.05",
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    por_variavel = {c.variavel: c.valor for c in resultado.criterios}
    # k2 does not appear in the equations of A in either model, nor in the equation of C of
    # the reduction, so nothing that is compared moves: only the noise of the original.
    assert por_variavel["A"] < RUIDO_NUMERICO
    assert por_variavel["C"] == pytest.approx(0.00072, abs=1e-4)
    assert resultado.aprovado is True


def test_a_simulation_that_goes_negative_stops_the_run_instead_of_giving_a_verdict(
    tmp_path: Path,
) -> None:
    # config_negativa.yaml compares the zeroth-order model with itself: every metric would
    # be exactly zero, that is, a perfect verdict, on a run that went below zero.
    with pytest.raises(reducheck.simulation.ErroDeSimulacao) as erro:
        reducheck.verificar(prepare(tmp_path, "config_negativa.yaml"))

    assert "'X'" in str(erro.value)
    assert "t = 1.1" in str(erro.value)


# --- three-level verdict (issue #13) -----------------------------------------

#: A desirable criterion that the qssa_ok pair fails: erro_max_rel in C is 0,24695, against
#: the same 0,05 limit that NRMSE passes (tests/fixtures/README.md, and question 18 of
#: docs/questoes-em-aberto.md). It is the real case the three levels exist for.
DESEJAVEL_QUE_FALHA = """
  - metrica: erro_max_rel
    limite: 0.05
    variaveis: [C]
    obrigatorio: false
"""


def com_criterio_extra(config: Path, trecho: str) -> Path:
    """Append ``trecho`` to the criteria of ``config``, in place."""
    texto = config.read_text(encoding="utf-8")
    config.write_text(
        texto.replace("\nrelatorio:", trecho + "\nrelatorio:", 1), encoding="utf-8"
    )
    return config


def test_only_a_desirable_criterion_failing_gives_reservations(tmp_path: Path) -> None:
    config = com_criterio_extra(prepare(tmp_path, "config_qssa_ok.yaml"), DESEJAVEL_QUE_FALHA)

    resultado = reducheck.verificar(config)

    assert resultado.nivel == "APROVADO COM RESSALVAS"
    assert resultado.aprovado is False
    assert resultado.veredito.obrigatorios == (2, 2)
    assert resultado.veredito.desejaveis == (0, 1)
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))
    assert dados["veredito"] == "APROVADO COM RESSALVAS"
    assert dados["criterios"][-1]["valor"] == pytest.approx(0.24695, abs=1e-4)
    assert dados["criterios"][-1]["tipo"] == "desejável"


def test_the_same_criterion_as_mandatory_rejects_the_pair(tmp_path: Path) -> None:
    # Same number, same limit: only 'obrigatorio' changes, and the verdict changes with it.
    config = com_criterio_extra(
        prepare(tmp_path, "config_qssa_ok.yaml"),
        DESEJAVEL_QUE_FALHA.replace("obrigatorio: false", "obrigatorio: true"),
    )

    resultado = reducheck.verificar(config)

    assert resultado.nivel == "REPROVADO"
    # Two of three items passed, and the pair is rejected anyway.
    assert resultado.porcentagem == pytest.approx(200 / 3)


def test_two_levels_report_the_same_run_as_approved(tmp_path: Path) -> None:
    config = com_criterio_extra(prepare(tmp_path, "config_qssa_ok.yaml"), DESEJAVEL_QUE_FALHA)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "relatorio:\n  pasta: resultados/", "relatorio:\n  pasta: resultados/\n  niveis: 2"
        ),
        encoding="utf-8",
    )

    resultado = reducheck.verificar(config)

    assert resultado.nivel == "APROVADO"
    assert resultado.aprovado is True
    # The item that failed is still in the table and still out of the percentage.
    assert resultado.veredito.desejaveis == (0, 1)
    assert resultado.porcentagem == pytest.approx(200 / 3)


# --- qualitative criteria end to end (issue #18) -----------------------------

#: From tests/fixtures/README.md: the aggregation pair misses the equilibrium by 0.36%.
ERRO_NO_EQUILIBRIO = 0.00362


def test_the_two_qualitative_criteria_become_items_of_the_verdict(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))

    metricas = [(item.metrica, item.variavel) for item in resultado.criterios]
    assert metricas == [("nrmse", "X"), ("equilibrio", "X"), ("estabilidade_local", "—")]
    assert resultado.aprovado
    assert resultado.porcentagem == 100.0


def test_the_equilibrium_item_measures_the_hand_computed_error(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    item = next(c for c in resultado.criterios if c.metrica == "equilibrio")

    assert item.valor == pytest.approx(ERRO_NO_EQUILIBRIO, abs=1e-5)
    assert item.detalhes["equilibrio_original"] == pytest.approx(
        1.0 / 0.20 + 0.5 / 0.22, rel=1e-6
    )
    assert item.detalhes["equilibrio_simplificado"] == pytest.approx(
        1.5 / 0.207, rel=1e-6
    )


def test_the_stability_item_compares_labels_and_not_eigenvalues(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    item = next(c for c in resultado.criterios if c.metrica == "estabilidade_local")

    assert item.valor is None and item.limite is None
    assert item.valor_texto == "estável / estável"
    assert item.limite_texto == "igual"
    assert item.passou
    # Different dimensions: 2 eigenvalues against 1. Comparing the vectors is meaningless,
    # which is why the criterion compares the classification.
    assert len(item.detalhes["autovalores_dominantes_original"]) == 2
    assert len(item.detalhes["autovalores_dominantes_simplificado"]) == 1


def test_a_tight_threshold_fails_the_equilibrium_without_touching_the_rest(
    tmp_path: Path,
) -> None:
    caminho = prepare(tmp_path, "config_qualitativo.yaml")
    caminho.write_text(
        caminho.read_text(encoding="utf-8").replace(
            "metrica: equilibrio\n    limite: 0.05", "metrica: equilibrio\n    limite: 0.001"
        ),
        encoding="utf-8",
    )
    resultado = reducheck.verificar(caminho)

    assert not resultado.aprovado
    assert resultado.nivel == "REPROVADO"
    item = next(c for c in resultado.criterios if c.metrica == "equilibrio")
    assert not item.passou
    assert item.valor == pytest.approx(ERRO_NO_EQUILIBRIO, abs=1e-5)


def test_the_json_records_the_equilibrium_of_both_models(tmp_path: Path) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))

    qualitativo = dados["qualitativo"]
    assert "um único equilíbrio" in qualitativo["aviso"]
    assert qualitativo["original"]["equilibrio"]["X1"] == pytest.approx(5.0, rel=1e-6)
    assert qualitativo["original"]["classificacao"] == "estável"
    assert qualitativo["simplificado"]["classificacao"] == "estável"
    assert "steadyState" in qualitativo["original"]["metodo"]


def test_the_readable_report_shows_the_equilibrium_and_the_eigenvalues(
    tmp_path: Path,
) -> None:
    resultado = reducheck.verificar(prepare(tmp_path, "config_qualitativo.yaml"))
    markdown = (tmp_path / "resultados" / "relatorio.md").read_text(encoding="utf-8")

    # The qualitative tables live in the "Longo prazo" section since the report was split
    # by question.
    assert "## Longo prazo" in markdown
    assert "### Equilíbrio e estabilidade" in markdown
    assert "Autovalores dominantes" in markdown
    assert "-0,2" in markdown  # autovalor do original, com vírgula decimal
    assert "estável / estável" in resultado.criterios[-1].valor_texto
    assert "outros equilíbrios não foram buscados" in markdown


def test_without_a_qualitative_criterion_nothing_is_analysed(tmp_path: Path) -> None:
    """The analysis can integrate far past the horizon, so it only runs when asked."""
    resultado = reducheck.verificar(prepare(tmp_path, "config_aggregation.yaml"))

    assert resultado.comparacao is None
    dados = json.loads(resultado.caminho_json.read_text(encoding="utf-8"))
    assert dados["qualitativo"] is None
