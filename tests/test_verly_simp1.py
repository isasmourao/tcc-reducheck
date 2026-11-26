"""Checks on the SBML translation of simplification 1 of the Verly model.

These tests guard `modelos/verly_simp1.ant` against typos, and they pin the
structural consequence of the simplification that the case study is about: the
term `F1 * Cm` was the only source of osteoblasts, so what replaces it decides
whether `Cb` ever leaves zero.

The equations come from `referencia/simplificacao_2026-04-22.md`; the numbers of
the comparison against the original live in `estudo_de_caso/NOTAS.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import roadrunner

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "modelos" / "verly_simp1.xml"
ORIGINAL_PATH = ROOT / "modelos" / "verly_original.xml"

STATE_VARIABLES = ["D", "Mo", "M1", "M2", "C1", "C2", "Cb", "Mb", "E2"]

# Removed with Cm and Mc, according to `referencia/simplificacao_2026-04-22.md`.
REMOVED_VARIABLES = ["Cm", "Mc"]
REMOVED_PARAMETERS = [
    "kpm",
    "apm",
    "apm1",
    "K_lm",
    "dm",
    "amb1",
    "p_cs",
    "q_cd1",
    "q_cd2",
    "k_3",
]

# Every parameter kept from the original, with the value of the original code.
# The note replaces the term F1 * Cm by a source `Es`, read here as the
# estradiol E2, so it adds no parameter of its own.
PARAMETERS = {
    "ke_1": 3.0,
    "ke_2": 3.0,
    "a_ed": 4.71e6,
    "d_o": 0.156,
    "k_12": 0.075,
    "k_21": 0.005,
    "d_1": 0.121,
    "d_2": 0.163,
    "k_o": 0.0000005,
    "k_1": 0.0000083,
    "d_c1": 0.2,
    "k_2": 0.00000372,
    "d_c2": 0.25,
    "k_lb": 1000000.0,
    "d_b": 0.15,
    "p_bs": 0.00000005,
    "q_bd": 0.00000005,
    "aed": 4.71e6,
    "kmax": 0.015,
    "Mmax": 6.0e5,
    "k_01": 0.55,
    "a_01": 0.01,
    "k_02": 0.3,
    "a_02": 0.005,
    "a_12": 0.025,
    "a_22": 0.1,
    "kpb": 0.2202,
    "apb": 10.0,
    "ae2": 0.5,
    "de2": 0.03,
    "E2max": 0.060,
}

INITIAL_CONDITIONS = {
    "D": 1000000.0,
    "Mo": 4000.0,
    "M1": 0.0,
    "M2": 0.0,
    "C1": 0.0,
    "C2": 0.0,
    "Cb": 0.0,
    "Mb": 0.0,
    "E2": 0.060,
}


@pytest.fixture(scope="module")
def runner() -> roadrunner.RoadRunner:
    """Load the SBML model once for the whole module."""
    return roadrunner.RoadRunner(str(MODEL_PATH))


def test_sbml_is_valid() -> None:
    """libsbml reads the file without errors."""
    libsbml = pytest.importorskip("libsbml")
    document = libsbml.readSBMLFromFile(str(MODEL_PATH))
    assert document.getNumErrors() == 0


def test_has_nine_state_variables(runner: roadrunner.RoadRunner) -> None:
    """The simplification keeps exactly the nine variables of the note.

    As in `verly_original.ant`, the state variables are rate rules over plain
    parameters, not species in a compartment, so they are listed by
    `getRateRuleIds`.
    """
    assert sorted(runner.getRateRuleIds()) == sorted(STATE_VARIABLES)


@pytest.mark.parametrize("name", REMOVED_VARIABLES + REMOVED_PARAMETERS)
def test_removed_symbol_is_absent(runner: roadrunner.RoadRunner, name: str) -> None:
    """Nothing removed by the simplification survives in the SBML."""
    assert name not in runner.model.getGlobalParameterIds()


@pytest.mark.parametrize(("name", "value"), sorted(PARAMETERS.items()))
def test_parameter_value(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every kept parameter has the name and the value of the original code."""
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


@pytest.mark.parametrize(("name", "value"), sorted(INITIAL_CONDITIONS.items()))
def test_initial_condition(runner: roadrunner.RoadRunner, name: str, value: float) -> None:
    """Every state variable starts at the value of the original script."""
    runner.reset()
    assert runner[name] == pytest.approx(value, rel=0, abs=0)


def test_osteoblasts_leave_zero_through_the_estradiol_source(
    runner: roadrunner.RoadRunner,
) -> None:
    """With `Es` read as E2, bone formation starts instead of staying at zero."""
    runner.reset()
    runner.selections = ["time", "Cb", "Mb"]
    result = runner.simulate(0, 720, 1000)
    assert result[:, 1].max() > 0.0
    assert result[:, 2].max() > 0.0


def test_without_any_source_the_osteoblasts_stay_at_zero(
    runner: roadrunner.RoadRunner,
) -> None:
    """The source term is what unlocks Cb, and this is the finding of the study.

    `F1 * Cm` was the only term of `dCb/dt` that does not carry a factor of `Cb`,
    so with no replacement the equation is homogeneous and `Cb(0) = 0` is a fixed
    point: removing it leaves bone formation with no source at all. Starting E2
    at zero holds it at zero (`dE2/dt` vanishes there) and so zeroes the source,
    which is how that case is reproduced here. See `estudo_de_caso/NOTAS.md`.
    """
    runner.reset()
    runner["init(E2)"] = 0.0
    runner.selections = ["time", "Cb", "Mb"]
    result = runner.simulate(0, 720, 1000)
    runner.reset()
    runner["init(E2)"] = 0.060
    assert result[:, 1].max() == 0.0
    assert result[:, 2].max() == 0.0


def test_the_source_sets_the_level_because_the_logistic_is_scaled_by_k_lb(
    runner: roadrunner.RoadRunner,
) -> None:
    """Cb stays small, at the level the source E2 alone can hold.

    The logistic term is `Ab * Cb * (1 - Cb) / k_lb`, with k_lb = 1e6, so the net
    proliferation rate `Ab / k_lb` is about a million times smaller than the death rate
    d_b. With Cb << 1 the equation is close to linear:
    `dCb/dt ~ E2 - (d_b - Ab / k_lb) * Cb`, whose equilibrium is `E2 / (d_b - Ab / k_lb)`.
    """
    runner.reset()
    runner.selections = ["time", "Cb", "C1", "E2"]
    result = runner.simulate(0, 720, 1000)
    cb_final, c1_final, e2_final = result[-1, 1], result[-1, 2], result[-1, 3]
    ab_final = PARAMETERS["kpb"] * PARAMETERS["apb"] / (PARAMETERS["apb"] + c1_final)
    proliferacao = ab_final / PARAMETERS["k_lb"]
    assert proliferacao < 1e-5 * PARAMETERS["d_b"]
    esperado = e2_final / (PARAMETERS["d_b"] - proliferacao)
    assert cb_final == pytest.approx(esperado, rel=1e-2)


def test_c1_equation_is_the_one_of_the_original() -> None:
    """Removing Cm and Mc does not touch C1, so its equation stays as in the original.

    The note writes it without the E2 that multiplies the degradation; the
    simplification keeps the E2 of the original code.
    """
    libsbml = pytest.importorskip("libsbml")

    def c1_rate(path: Path) -> str:
        model = libsbml.readSBMLFromFile(str(path)).getModel()
        return libsbml.formulaToL3String(model.getRateRuleByVariable("C1").getMath())

    assert c1_rate(MODEL_PATH) == c1_rate(ORIGINAL_PATH)
    assert "E2" in c1_rate(MODEL_PATH)


def test_estradiol_matches_the_original_exactly() -> None:
    """E2 is untouched by the simplification, so the two models must agree on it.

    `dE2/dt` does not depend on any other variable, so any difference here would
    mean a typo in the transcription rather than an effect of the simplification.
    """
    simplified = roadrunner.RoadRunner(str(MODEL_PATH))
    original = roadrunner.RoadRunner(str(ORIGINAL_PATH))
    for model in (simplified, original):
        model.integrator.relative_tolerance = 1e-8
        model.integrator.absolute_tolerance = 1e-10
        model.selections = ["time", "E2"]
    assert simplified.simulate(0, 720, 1000)[-1, 1] == pytest.approx(
        original.simulate(0, 720, 1000)[-1, 1], rel=1e-8
    )


# --- qualitative analysis of the case study -----------------------------------

#: Measured by `reducheck verificar estudo_de_caso/simp1.yaml` ("Longo prazo") with the models
#: where RM carries the factor D and the logistic of Cb is divided by k_lb. The equilibrium is
#: reached at t = 72000, 100 times the 720-day horizon. In the original, Cb goes to zero.
EQUILIBRIO_VERLY = {
    "Mb": (1.0, 0.99865),
    "C1": (0.0221518, 0.00266),
    "C2": (5.38010e-06, 0.00279),
    "E2": (0.0564, 0.0),
}
ERRO_EQUILIBRIO_CB = 0.75273


def test_the_qualitative_analysis_of_the_case_study(tmp_path: Path) -> None:
    """The library on the real case study: same stability, different equilibrium.

    Both models are classified the same way, but the equilibrium of Cb and Mb fails: in
    the original Cb dies out, while in the simplification the source E2 holds it at about
    `E2 / d_b`. C1, C2 and E2 agree within the 5% limit.
    """
    import reducheck

    resultado = reducheck.verificar(ROOT / "estudo_de_caso" / "simp1.yaml", pasta_de_saida=tmp_path)
    comparacao = resultado.comparacao
    assert comparacao is not None

    # Neither steadyState nor getFullJacobian is usable: the model has no floating species.
    assert "integração até" in comparacao.original.equilibrio.metodo
    assert comparacao.original.estabilidade.metodo.startswith("diferenças finitas")
    assert comparacao.original.equilibrio.instante == pytest.approx(7.2e4, rel=1e-9)
    assert comparacao.original.equilibrio.vezes_o_horizonte(720.0) == pytest.approx(100.0)

    # Same classification in both models, so the stability criterion passes.
    assert comparacao.original.estabilidade.classificacao == "marginal"
    assert comparacao.simplificado.estabilidade.classificacao == "marginal"
    estabilidade = next(
        item for item in resultado.criterios if item.metrica == "estabilidade_local"
    )
    assert estabilidade.passou

    itens = {
        item.variavel: item
        for item in resultado.criterios
        if item.metrica == "equilibrio"
    }
    for nome, (valor_original, erro) in EQUILIBRIO_VERLY.items():
        assert itens[nome].detalhes["equilibrio_original"] == pytest.approx(
            valor_original, rel=1e-4
        )
        assert itens[nome].valor == pytest.approx(erro, abs=5e-5)
    assert itens["Cb"].detalhes["equilibrio_original"] == pytest.approx(0.0, abs=1e-6)
    assert itens["Cb"].valor == pytest.approx(ERRO_EQUILIBRIO_CB, abs=5e-5)
    assert not itens["Cb"].passou
    assert not itens["Mb"].passou
    assert itens["C1"].passou and itens["C2"].passou and itens["E2"].passou

    # One file answers both questions: trajectory 3 of 15, long run 4 of 6.
    from reducheck.verdict import LONGO_PRAZO, TRAJETORIA

    longo = resultado.veredito.parte(LONGO_PRAZO)
    caminho = resultado.veredito.parte(TRAJETORIA)
    assert longo.nivel == "REPROVADO"
    assert sum(item.passou for item in longo.criterios) == 4
    assert len(longo.criterios) == 6
    assert sum(item.passou for item in caminho.criterios) == 3
    assert len(caminho.criterios) == 15
    assert resultado.nivel == "REPROVADO"
    assert resultado.porcentagem == pytest.approx(100.0 * 7 / 21)
