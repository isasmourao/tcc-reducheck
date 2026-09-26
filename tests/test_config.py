"""Tests of the configuration schema and of the message every rejection produces.

One test per kind of error, as issue #9 asks. The assertions check the *message*, not only
that it failed: the field path and the suggestion are the deliverable here, since the user
of the library does not read the code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reducheck import config as config_mod

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: A valid configuration for the qssa_ok toy pair, used as the base of every mutation.
BASE = """
versao: 1
modelos:
  original: qssa_ok_original.xml
  simplificado: qssa_ok_simplified.xml
simulacao:
  t_inicio: 0
  t_fim: 40
  pontos: 401
variaveis:
  - nome: A
    original: A
    simplificado: A
  - nome: C
    original: C
    simplificado: C
criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: [A, C]
"""


def escrever(tmp_path: Path, texto: str) -> Path:
    """Write one configuration into tmp_path, next to copies of the fixture models."""
    for modelo in FIXTURES_DIR.glob("qssa_ok_*.xml"):
        (tmp_path / modelo.name).write_bytes(modelo.read_bytes())
    caminho = tmp_path / "config.yaml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def recusa(tmp_path: Path, texto: str) -> str:
    """Load a configuration expecting it to be refused, and return the message."""
    with pytest.raises(config_mod.ErroDeConfiguracao) as erro:
        config_mod.carregar(escrever(tmp_path, texto))
    return str(erro.value)


# --- the base configuration is accepted ---------------------------------------


def test_the_fixture_configuration_reads_every_field() -> None:
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


def test_the_base_configuration_loads(tmp_path: Path) -> None:
    cfg = config_mod.carregar(escrever(tmp_path, BASE))

    assert [v.nome for v in cfg.variaveis] == ["A", "C"]
    # Defaults of docs/produto.md: every variable is core and every criterion is mandatory.
    assert all(v.core for v in cfg.variaveis)
    assert all(c.obrigatorio for c in cfg.criterios)
    assert cfg.simulacao.t_inicio == 0.0
    assert cfg.simulacao.solver == "cvode"
    assert cfg.simulacao.tol_relativa == 1e-8
    assert cfg.simulacao.tol_absoluta == 1e-10
    assert cfg.relatorio.formatos == ["json"]
    assert cfg.relatorio.pasta == tmp_path / "resultados"


# --- the whole schema of docs/produto.md is accepted --------------------------


COMPLETA = """
versao: 1
modelos:
  original: qssa_ok_original.xml
  simplificado: qssa_ok_simplified.xml
simulacao:
  t_inicio: 0
  t_fim: 40
  pontos: 401
  solver: cvode
  tol_relativa: 1e-8
  tol_absoluta: 1e-10
  parametros:
    k1: 0.5
  condicoes_iniciais:
    A: 2.0
variaveis:
  - nome: soma
    original: [A, C]
    simplificado: A
    core: true
  - nome: ponderada
    original: {A: 1.0, C: 0.5}
    simplificado: C
    core: false
  - nome: eliminada
    original: C
    simplificado: null
    core: false
criterios:
  - metrica: nrmse
    limite: 0.05
    variaveis: core
    obrigatorio: true
  - metrica: estabilidade_local
    obrigatorio: false
relatorio:
  formatos: [html, json]
  pasta: resultados/
"""


def test_the_full_schema_of_the_product_document_is_parsed(tmp_path: Path) -> None:
    # Parsed, but not runnable: the capabilities it asks for are later issues. The schema
    # is validated apart from the support gate so that the file format is already stable.
    dados = config_mod.ler_yaml(escrever(tmp_path, COMPLETA))
    cfg = config_mod.validar_esquema(dados, Path("config.yaml"))

    assert cfg.simulacao.parametros == {"k1": 0.5}
    assert cfg.simulacao.condicoes_iniciais == {"A": 2.0}
    assert [v.original for v in cfg.variaveis] == [["A", "C"], {"A": 1.0, "C": 0.5}, "C"]
    assert cfg.variaveis[2].simplificado is None
    assert [v.core for v in cfg.variaveis] == [True, False, False]
    assert cfg.criterios[0].variaveis == "core"
    assert cfg.criterios[1].limite is None
    assert cfg.criterios[1].obrigatorio is False
    assert cfg.relatorio.formatos == ["html", "json"]


def test_the_full_schema_still_stops_before_simulating(tmp_path: Path) -> None:
    # Whatever this version cannot honour has to stop, never be silently ignored.
    assert "ainda não" in recusa(tmp_path, COMPLETA)


# --- one test per kind of error ----------------------------------------------


def test_missing_configuration_file(tmp_path: Path) -> None:
    with pytest.raises(config_mod.ErroDeConfiguracao, match="ausente.yaml"):
        config_mod.carregar(tmp_path / "ausente.yaml")


def test_missing_model_file_says_which_role_and_which_path(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("qssa_ok_original.xml", "nao_existe.xml"))

    assert "modelos.original" in mensagem
    assert "nao_existe.xml" in mensagem


def test_invalid_sbml_is_reported_as_such(tmp_path: Path) -> None:
    (tmp_path / "quebrado.xml").write_text("nao sou sbml", encoding="utf-8")
    mensagem = recusa(tmp_path, BASE.replace("qssa_ok_simplified.xml", "quebrado.xml"))

    assert "modelos.simplificado" in mensagem
    assert "quebrado.xml" in mensagem
    assert "SBML" in mensagem


def test_variable_absent_from_the_model_suggests_a_similar_name(tmp_path: Path) -> None:
    # 'c' (lowercase) does not exist in the original; 'C' does.
    mensagem = recusa(tmp_path, BASE.replace("    original: C", "    original: c"))

    assert "variaveis[1].original" in mensagem
    assert "'c'" in mensagem
    assert "'C'" in mensagem  # the suggestion


def test_variable_absent_without_a_similar_name_lists_what_exists(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("    original: C", "    original: zzzzzz"))

    assert "variaveis[1].original" in mensagem
    assert "Disponíveis" in mensagem


def test_core_variable_without_a_counterpart_is_refused(tmp_path: Path) -> None:
    texto = BASE.replace(
        "  - nome: C\n    original: C\n    simplificado: C",
        "  - nome: C\n    original: C\n    simplificado: null",
    )
    mensagem = recusa(tmp_path, texto)

    assert "variaveis[1].simplificado" in mensagem
    assert "core" in mensagem


def test_a_criterion_may_not_cite_a_variable_without_a_counterpart(tmp_path: Path) -> None:
    texto = BASE.replace(
        "  - nome: C\n    original: C\n    simplificado: C",
        "  - nome: C\n    original: C\n    simplificado: null\n    core: false",
    )
    mensagem = recusa(tmp_path, texto)

    assert "criterios[0].variaveis" in mensagem
    assert "'C'" in mensagem


def test_unknown_metric_suggests_the_closest_registered_one(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("metrica: nrmse", "metrica: nrmsee"))

    assert "criterios[0].metrica" in mensagem
    assert "nrmse" in mensagem


def test_negative_threshold_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("limite: 0.05", "limite: -0.05"))

    assert "criterios[0].limite" in mensagem
    assert "maior que zero" in mensagem


def test_a_quantitative_criterion_needs_a_threshold(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("    limite: 0.05\n", ""))

    assert "criterios[0].limite" in mensagem


def test_criterion_citing_an_undeclared_variable_suggests_a_declared_one(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("variaveis: [A, C]", "variaveis: [A, Cc]"))

    assert "criterios[0].variaveis" in mensagem
    assert "'Cc'" in mensagem
    assert "'C'" in mensagem


def test_unknown_key_is_refused_and_a_typo_gets_a_suggestion(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("  pontos: 401", "  pontos: 401\n  ponto: 10"))

    assert "simulacao.ponto" in mensagem
    assert "pontos" in mensagem


def test_a_repeated_report_name_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("  - nome: C", "  - nome: A"))

    assert "variaveis" in mensagem
    assert "'A'" in mensagem


def test_a_time_horizon_that_does_not_advance_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("t_fim: 40", "t_fim: 0"))

    assert "simulacao.t_fim" in mensagem


def test_too_few_output_points_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("pontos: 401", "pontos: 1"))

    assert "simulacao.pontos" in mensagem


def test_a_missing_required_section_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("versao: 1\n", ""))

    assert "versao" in mensagem


def test_a_file_that_is_not_yaml_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, "versao: 1\n  isto: nao indenta\n")

    assert "YAML" in mensagem


def test_a_yaml_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, "- versao: 1\n")

    assert "chaves" in mensagem


# --- capabilities of later issues: parsed, then refused ----------------------


@pytest.mark.parametrize(
    ("de", "para", "campo"),
    [
        # A qualitative criterion carries no threshold and no list of variables.
        (
            "metrica: nrmse\n    limite: 0.05\n    variaveis: [A, C]",
            "metrica: estabilidade_local",
            "criterios[0].metrica",
        ),
        (
            "    variaveis: [A, C]",
            "    variaveis: [A, C]\n    obrigatorio: false",
            "criterios[0].obrigatorio",
        ),
        ("  pontos: 401", "  pontos: 401\n  parametros:\n    k1: 0.5", "simulacao.parametros"),
        (
            "  pontos: 401",
            "  pontos: 401\n  condicoes_iniciais:\n    A: 2.0",
            "simulacao.condicoes_iniciais",
        ),
        ("  pontos: 401", "  pontos: 401\n  solver: euler", "simulacao.solver"),
    ],
)
def test_what_is_not_supported_yet_stops_with_the_field_and_the_reason(
    tmp_path: Path, de: str, para: str, campo: str
) -> None:
    mensagem = recusa(tmp_path, BASE.replace(de, para))

    assert campo in mensagem
    assert "ainda não" in mensagem


def test_an_unsupported_report_format_stops(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE + "relatorio:\n  formatos: [html]\n")

    assert "relatorio.formatos" in mensagem
    assert "ainda não" in mensagem


# --- mapping by sum, weighted sum and core selection (issue #10) -------------


def test_a_sum_and_a_weighted_sum_are_accepted(tmp_path: Path) -> None:
    cfg = config_mod.carregar(
        escrever(
            tmp_path,
            BASE.replace(
                "    original: A\n    simplificado: A",
                "    original: [A, B]\n    simplificado: A",
            ).replace("    original: C\n", "    original: {A: 1.0, C: 0.5}\n"),
        )
    )

    assert [v.original for v in cfg.variaveis] == [["A", "B"], {"A": 1.0, "C": 0.5}]


def test_the_three_spellings_normalize_to_the_same_shape() -> None:
    assert config_mod.normalizar_alvo("A") == {"A": 1.0}
    assert config_mod.normalizar_alvo(["A", "B"]) == {"A": 1.0, "B": 1.0}
    assert config_mod.normalizar_alvo({"A": 1.0, "B": 0.5}) == {"A": 1.0, "B": 0.5}


def test_an_arbitrary_expression_says_it_is_not_supported(tmp_path: Path) -> None:
    # It must not be reported as "the model has no variable called A + C": the reason is
    # that the library deliberately does not read expressions.
    mensagem = recusa(tmp_path, BASE.replace("original: C\n", "original: A + C\n"))

    assert "variaveis[1].original" in mensagem
    assert "Expressões" in mensagem


def test_a_ratio_inside_a_sum_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("original: C\n", "original: [A, C/B]\n"))

    assert "variaveis[1].original" in mensagem
    assert "Expressões" in mensagem


def test_an_empty_sum_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("original: C\n", "original: []\n"))

    assert "variaveis[1].original" in mensagem
    assert "vazia" in mensagem


def test_a_variable_repeated_inside_a_sum_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("original: C\n", "original: [C, C]\n"))

    assert "variaveis[1].original" in mensagem
    assert "mais de uma vez" in mensagem


def test_a_non_finite_weight_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(tmp_path, BASE.replace("original: C\n", "original: {C: .nan}\n"))

    assert "variaveis[1].original" in mensagem
    assert "finito" in mensagem


def test_a_dropped_variable_is_accepted_when_it_is_not_core(tmp_path: Path) -> None:
    cfg = config_mod.carregar(
        escrever(
            tmp_path,
            BASE.replace(
                "criterios:",
                "  - nome: B\n    original: B\n    simplificado: null\n"
                "    core: false\ncriterios:",
            ),
        )
    )

    assert cfg.variaveis[-1].simplificado is None
    assert cfg.nomes_core() == ["A", "C"]


def test_the_core_selector_expands_to_the_core_variables(tmp_path: Path) -> None:
    cfg = config_mod.carregar(
        escrever(
            tmp_path,
            BASE.replace(
                "    simplificado: C\n", "    simplificado: C\n    core: false\n"
            ).replace("variaveis: [A, C]", "variaveis: core"),
        )
    )

    assert cfg.nomes_core() == ["A"]
    assert cfg.variaveis_de(cfg.criterios[0]) == ["A"]


def test_the_core_selector_with_nothing_core_is_refused(tmp_path: Path) -> None:
    mensagem = recusa(
        tmp_path,
        BASE.replace("    simplificado: A\n", "    simplificado: A\n    core: false\n")
        .replace("    simplificado: C\n", "    simplificado: C\n    core: false\n")
        .replace("variaveis: [A, C]", "variaveis: core"),
    )

    assert "criterios[0].variaveis" in mensagem
    assert "core" in mensagem


# --- the commented example is a valid configuration --------------------------


def test_the_example_configuration_is_valid() -> None:
    exemplo = Path(__file__).resolve().parents[1] / "exemplos" / "config_exemplo.yaml"

    cfg = config_mod.carregar(exemplo)

    assert cfg.versao == 1
    # B is there to show the eliminated variable read from an assignment rule; it is not
    # core, because the QSSA does not get it right at t = 0 (tests/fixtures/README.md).
    assert [v.nome for v in cfg.variaveis] == ["A", "C", "B"]
    assert cfg.nomes_core() == ["A", "C"]
