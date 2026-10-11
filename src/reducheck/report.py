"""Render the results as JSON, as a readable report and as plots.

Two audiences, one set of numbers. ``resultado.json`` is for code and for tests;
``relatorio.html`` (or ``relatorio.md``) is for a person, and follows the order of
``docs/produto.md``: verdict, numeric summary, table of criteria with the failures first,
reasons, warnings, plots, and the data of the run.

The HTML is a single file: every plot goes into it as base64, so the report can be sent by
e-mail or attached to the dissertation without a folder beside it. The same plots are saved
as PNG at 300 dpi in ``graficos/`` for the text; the Markdown report links to those files,
since Markdown readers do not handle embedded images well.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy
import roadrunner
from jinja2 import Environment, PackageLoader, select_autoescape

import reducheck
from reducheck import plots, qualitative
from reducheck.config import Configuracao
from reducheck.mapping import SerieComparada
from reducheck.simulation import RuidoNumerico, unidade_de_tempo
from reducheck.verdict import Contagem, ItemAvaliado, Veredito

__all__ = [
    "ARQUIVOS",
    "NOME_DO_JSON",
    "como_dicionario",
    "razoes",
    "salvar",
    "salvar_json",
]

#: File name used for the machine-readable result, as in ``docs/produto.md``.
NOME_DO_JSON = "resultado.json"

#: File written for each requested format, as in ``docs/produto.md``.
ARQUIVOS = {"json": NOME_DO_JSON, "html": "relatorio.html", "md": "relatorio.md"}

#: What the reasons section cannot say yet, stated in the report instead of left implicit.
NOTA_DAS_RAZOES = (
    "Por ora a razão diz o critério, o valor e por quanto o limite foi ultrapassado; "
    "onde no tempo o erro se concentra entra na issue #19 (T15)."
)


def como_dicionario(
    veredito: Veredito,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
    comparacao: qualitative.Comparacao | None = None,
    t_fim: float | None = None,
) -> dict[str, Any]:
    """Return the verdict as the structure written to ``resultado.json``.

    ``avisos`` are the warnings that do not belong to a single metric -- the reference
    numerical noise and the thresholds too close to it -- and come first, because they say
    how much of the numbers below is worth reading.
    """
    return {
        "veredito": veredito.nivel,
        "aprovado": veredito.aprovado,
        "porcentagem": veredito.porcentagem,
        "obrigatorios": _contagem(veredito.obrigatorios),
        "desejaveis": _contagem(veredito.desejaveis),
        "avisos": [*avisos, *veredito.avisos],
        "ruido_numerico": None if ruido is None else _ruido(ruido),
        "qualitativo": (
            None if comparacao is None else _qualitativo(comparacao, t_fim)
        ),
        "criterios": [
            {
                "metrica": item.metrica,
                "variavel": item.variavel,
                "valor": item.valor,
                "limite": item.limite,
                **({"valor_texto": item.valor_texto} if item.valor_texto else {}),
                **({"limite_texto": item.limite_texto} if item.limite_texto else {}),
                "resultado": "passou" if item.passou else "falhou",
                "tipo": "obrigatório" if item.obrigatorio else "desejável",
                "descricao": item.descricao,
                "avisos": list(item.avisos),
                "detalhes": dict(item.detalhes),
            }
            for item in veredito.criterios
        ],
    }


def _qualitativo(
    comparacao: qualitative.Comparacao, t_fim: float | None
) -> dict[str, Any]:
    """Return the qualitative analysis of both models as the JSON records it.

    The warning about a single equilibrium travels with the numbers, and not only in the
    report meant for a person: whoever reads ``resultado.json`` in a script is the reader
    most likely to take an equilibrium for *the* equilibrium.
    """
    return {
        "aviso": qualitative.AVISO_DO_EQUILIBRIO_UNICO,
        "original": _analise(comparacao.original, t_fim),
        "simplificado": _analise(comparacao.simplificado, t_fim),
    }


def _analise(analise: qualitative.Analise, t_fim: float | None) -> dict[str, Any]:
    equilibrio, estabilidade = analise.equilibrio, analise.estabilidade
    return {
        "equilibrio": dict(equilibrio.ponto),
        "metodo": equilibrio.metodo,
        "instante": equilibrio.instante,
        "vezes_o_horizonte": (
            None if t_fim is None else equilibrio.vezes_o_horizonte(t_fim)
        ),
        "residuo": equilibrio.residuo,
        "residuo_absoluto": equilibrio.residuo_absoluto,
        "escala_de_taxa": equilibrio.escala_de_taxa,
        "classificacao": estabilidade.classificacao,
        "autovalores_dominantes": [
            [valor.real, valor.imag] for valor in estabilidade.dominantes()
        ],
        "metodo_da_jacobiana": estabilidade.metodo,
        "tolerancia_marginal": estabilidade.tolerancia,
        "limiar_marginal": estabilidade.limiar,
    }


def _contagem(contagem: Contagem) -> dict[str, int]:
    return {"passados": contagem.passados, "total": contagem.total}


def _ruido(ruido: RuidoNumerico) -> dict[str, Any]:
    return {
        "fator_de_tolerancia": ruido.fator,
        "maximo": ruido.maximo,
        "por_variavel": dict(ruido.por_variavel),
        "sem_medida": dict(ruido.sem_medida),
        "resumo": ruido.resumo(),
    }


def salvar_json(
    veredito: Veredito,
    pasta: Path | str,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
    comparacao: qualitative.Comparacao | None = None,
    t_fim: float | None = None,
) -> Path:
    """Write ``resultado.json`` into ``pasta``, creating the folder if needed."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_DO_JSON
    conteudo = json.dumps(
        como_dicionario(veredito, ruido, avisos, comparacao, t_fim),
        ensure_ascii=False,
        indent=2,
    )
    caminho.write_text(conteudo + "\n", encoding="utf-8")
    return caminho


def razoes(veredito: Veredito) -> list[str]:
    """Return one line per failed item, saying which criterion failed and by how much.

    Deliberately shallow: the detailed reason -- where in time the error concentrates --
    is issue #19 (T15). What is here is what the metrics already measured, so that no
    failure ever appears in the report without an explanation next to it.
    """
    linhas = []
    for item in veredito.criterios:
        if item.passou:
            continue
        if item.valor is None:
            # A qualitative item has no number and no threshold: what it failed on is the
            # comparison of two labels, which the description already states.
            linhas.append(f"{item.metrica} falhou: {item.descricao}.")
            continue
        excesso = "" if item.limite in (0, None) else f", {item.valor / item.limite:.3g}× o limite"
        linha = (
            f"{item.metrica} em {item.variavel} falhou: {_numero(item.valor)} contra o "
            f"limite {_numero(item.limite)}{excesso}."
        )
        if item.descricao:
            linha += f" O valor é {item.descricao}."
        instante = item.detalhes.get("instante")
        if instante is not None:
            linha += f" O pior ponto está em t = {_numero(float(instante))}."
        linhas.append(linha)
    return linhas


def salvar(
    veredito: Veredito,
    configuracao: Configuracao,
    series: Mapping[str, SerieComparada] | None = None,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
    caminho_config: Path | str | None = None,
    comparacao: qualitative.Comparacao | None = None,
) -> dict[str, Path]:
    """Write every format asked for in ``relatorio.formatos`` and return where each went.

    The plots are drawn once and reused by both readable formats, so asking for HTML and
    Markdown together does not simulate or draw anything twice.
    """
    pasta = Path(configuracao.relatorio.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    formatos = list(dict.fromkeys(configuracao.relatorio.formatos))
    caminhos: dict[str, Path] = {}

    if "json" in formatos:
        caminhos["json"] = salvar_json(
            veredito, pasta, ruido, avisos, comparacao, configuracao.simulacao.t_fim
        )

    legiveis = [formato for formato in formatos if formato in ("html", "md")]
    if not legiveis:
        return caminhos

    graficos = plots.desenhar(
        series or {},
        pasta,
        unidade_de_tempo=_unidade_de_tempo(configuracao),
    )
    contexto = _contexto(
        veredito, configuracao, graficos, ruido, avisos, caminho_config, comparacao
    )
    for formato in legiveis:
        caminho = pasta / ARQUIVOS[formato]
        caminho.write_text(_renderizar(formato, contexto), encoding="utf-8")
        caminhos[formato] = caminho
    return caminhos


def _unidade_de_tempo(configuracao: Configuracao) -> str | None:
    return unidade_de_tempo(configuracao.modelos.original)


def _ambiente() -> Environment:
    return Environment(
        loader=PackageLoader("reducheck", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _renderizar(formato: str, contexto: Mapping[str, Any]) -> str:
    return _ambiente().get_template(f"relatorio.{formato}.j2").render(**contexto)


#: CSS class of each verdict level, in the order the report shows them.
_CLASSES = {
    "APROVADO": "aprovado",
    "APROVADO COM RESSALVAS": "ressalvas",
    "REPROVADO": "reprovado",
}


def _contexto(
    veredito: Veredito,
    configuracao: Configuracao,
    graficos: Sequence[plots.Grafico],
    ruido: RuidoNumerico | None,
    avisos: Sequence[str],
    caminho_config: Path | str | None,
    comparacao: qualitative.Comparacao | None = None,
) -> dict[str, Any]:
    passados = sum(1 for item in veredito.criterios if item.passou)
    return {
        "titulo": _titulo(configuracao),
        "veredito": veredito,
        "classe_do_veredito": _CLASSES.get(veredito.nivel, "reprovado"),
        "passados": passados,
        "total": len(veredito.criterios),
        "porcentagem": _porcentagem(veredito.porcentagem),
        "obrigatorios": veredito.obrigatorios,
        "desejaveis": veredito.desejaveis,
        "nota_dos_niveis": _nota_dos_niveis(veredito, configuracao.relatorio.niveis),
        # Failures first: the reader looks for what went wrong, and the sort is stable, so
        # inside each group the criteria stay in the order they were declared.
        "criterios": [_linha(item) for item in sorted(veredito.criterios, key=_falhou_primeiro)],
        "razoes": razoes(veredito),
        "nota_das_razoes": NOTA_DAS_RAZOES,
        "avisos": [*avisos, *veredito.avisos],
        "qualitativo": _secao_qualitativa(comparacao, configuracao, veredito),
        "graficos": [_grafico(grafico) for grafico in graficos],
        "execucao": _execucao(configuracao, ruido, caminho_config, avisos),
    }


def _nota_dos_niveis(veredito: Veredito, niveis: int) -> str:
    """Say, in words, why an APROVADO can sit next to a percentage below 100.

    With ``relatorio.niveis: 2`` a failed desirable item does not lower the verdict but
    still counts against the percentage (question 26 of ``docs/questoes-em-aberto.md``,
    which asks for exactly this sentence). Without it the report reads as a contradiction.
    """
    fora = sum(1 for item in veredito.criterios if not item.passou and not item.obrigatorio)
    if niveis != 2 or fora == 0 or not veredito.aprovado:
        return ""
    if fora > 1:
        frase = f"{fora} itens desejáveis ficaram fora do limite e não impedem"
        resto = "a aprovação, mas continuam contando na porcentagem."
    else:
        frase = "1 item desejável ficou fora do limite e não impede"
        resto = "a aprovação, mas continua contando na porcentagem."
    return f"Veredito em dois níveis (relatorio.niveis: 2): {frase} {resto}"


def _secao_qualitativa(
    comparacao: qualitative.Comparacao | None,
    configuracao: Configuracao,
    veredito: Veredito,
) -> dict[str, Any] | None:
    """Return the qualitative section of the readable report, or ``None`` if there is none.

    Three things, in this order: the equilibrium of the mapped variables side by side (the
    items the ``equilibrio`` criterion already measured, so the table and the verdict cannot
    disagree), the summary of each model with its three dominant eigenvalues, and the fixed
    warning that a single equilibrium was analysed.
    """
    if comparacao is None:
        return None
    t_fim = configuracao.simulacao.t_fim
    itens = [item for item in veredito.criterios if item.metrica == "equilibrio"]
    return {
        "aviso": qualitative.AVISO_DO_EQUILIBRIO_UNICO,
        "modelos": [
            _resumo_qualitativo(analise, t_fim)
            for analise in (comparacao.original, comparacao.simplificado)
        ],
        "equilibrio": [_linha_de_equilibrio(item) for item in itens],
        "nota": (
            ""
            if itens
            else "Nenhum critério 'equilibrio' foi declarado, então o equilíbrio aqui "
            "serviu só para classificar a estabilidade local; os pontos completos estão "
            f"em {NOME_DO_JSON}."
        ),
    }


def _resumo_qualitativo(analise: qualitative.Analise, t_fim: float) -> dict[str, Any]:
    equilibrio, estabilidade = analise.equilibrio, analise.estabilidade
    vezes = equilibrio.vezes_o_horizonte(t_fim)
    if equilibrio.instante is None:
        instante = "—"
    else:
        instante = f"t = {_numero(equilibrio.instante)}"
        if vezes is not None and vezes > 1.0:
            instante += f" ({_numero(vezes)}× o horizonte simulado)"
    return {
        "papel": analise.papel,
        "classificacao": estabilidade.classificacao,
        "metodo": equilibrio.metodo,
        "instante": instante,
        "residuo": _numero(equilibrio.residuo),
        "autovalores": [_autovalor(valor) for valor in estabilidade.dominantes()],
        "metodo_da_jacobiana": estabilidade.metodo,
    }


def _linha_de_equilibrio(item: ItemAvaliado) -> dict[str, str]:
    return {
        "variavel": item.variavel,
        "original": _numero(_como_numero(item.detalhes.get("equilibrio_original"))),
        "simplificado": _numero(_como_numero(item.detalhes.get("equilibrio_simplificado"))),
        "erro": _numero(item.valor),
        "limite": _numero(item.limite),
        "resultado": "passou" if item.passou else "falhou",
    }


def _como_numero(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def _autovalor(valor: complex) -> str:
    """Format one eigenvalue, hiding the imaginary part when it is a real number."""
    if valor.imag == 0.0:
        return _numero(valor.real)
    sinal = "+" if valor.imag >= 0 else "−"
    return f"{_numero(valor.real)} {sinal} {_numero(abs(valor.imag))}i"


def _falhou_primeiro(item: ItemAvaliado) -> int:
    return int(item.passou)


def _titulo(configuracao: Configuracao) -> str:
    original = Path(configuracao.modelos.original).stem
    simplificado = Path(configuracao.modelos.simplificado).stem
    return f"Verificação: {simplificado} vs. {original}"


def _linha(item: ItemAvaliado) -> dict[str, str]:
    return {
        "metrica": item.metrica,
        "variavel": item.variavel,
        "valor": item.valor_texto or _numero(item.valor),
        "limite": item.limite_texto or _numero(item.limite),
        "tipo": "obrigatório" if item.obrigatorio else "desejável",
        "resultado": "passou" if item.passou else "falhou",
        "descricao": item.descricao,
    }


def _grafico(grafico: plots.Grafico) -> dict[str, str]:
    combinacao = ""
    if (
        grafico.legenda_original != grafico.variavel
        or grafico.legenda_simplificado != grafico.variavel
    ):
        combinacao = f"{grafico.legenda_original} (original) vs. {grafico.legenda_simplificado}"
    return {
        "variavel": grafico.variavel,
        "base64": grafico.base64,
        "arquivo": f"{plots.PASTA_DOS_GRAFICOS}/{grafico.caminho.name}",
        "combinacao": combinacao,
    }


def _execucao(
    configuracao: Configuracao,
    ruido: RuidoNumerico | None,
    caminho_config: Path | str | None,
    avisos: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """Return what is needed to tell two runs apart, as label/value pairs."""
    simulacao = configuracao.simulacao
    itens = [
        ("Data", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Modelo original", str(configuracao.modelos.original)),
        ("Modelo simplificado", str(configuracao.modelos.simplificado)),
    ]
    if caminho_config is not None:
        itens.append(("Configuração", str(caminho_config)))
    itens.append(
        (
            "Simulação",
            f"t de {simulacao.t_inicio:g} a {simulacao.t_fim:g} em {simulacao.pontos} pontos, "
            f"solver {simulacao.solver}, tolerâncias {simulacao.tol_relativa:g} (relativa) e "
            f"{simulacao.tol_absoluta:g} (absoluta)",
        )
    )
    # The noise already leads the warnings when the run measured it; repeating it here
    # would say the same sentence twice on the same page.
    if ruido is not None and ruido.resumo() not in avisos:
        itens.append(("Ruído numérico", ruido.resumo()))
    itens.append(("Níveis do veredito", str(configuracao.relatorio.niveis)))
    itens.append(
        (
            "Versões",
            f"reducheck {reducheck.__version__}, Python {_versao_do_python()}, "
            f"libRoadRunner {roadrunner.__version__}, numpy {numpy.__version__}, "
            f"matplotlib {matplotlib.__version__}",
        )
    )
    return itens


def _versao_do_python() -> str:
    return ".".join(str(parte) for parte in sys.version_info[:3])


def _numero(valor: float | None) -> str:
    """Format a number the way the report of ``docs/produto.md`` shows it (decimal comma)."""
    if valor is None:
        return "—"
    return f"{valor:.5g}".replace(".", ",")


def _porcentagem(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")
