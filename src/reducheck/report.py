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

import csv
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy
import roadrunner
import scipy
import yaml
from jinja2 import Environment, PackageLoader, select_autoescape

import reducheck
from reducheck import plots, qualitative
from reducheck.config import Configuracao
from reducheck.mapping import SerieComparada
from reducheck.simulation import RuidoNumerico, unidade_de_tempo
from reducheck.verdict import (
    AO_LONGO,
    ESTACIONARIO,
    SEM_VARIAVEL,
    TRANSIENTE,
    Contagem,
    ItemAvaliado,
    Veredito,
)

__all__ = [
    "ARQUIVOS",
    "ARQUIVOS_DE_REPRODUCAO",
    "EXPLICACOES_DAS_METRICAS",
    "NOME_DO_JSON",
    "MODELOS_DE_RAZAO",
    "como_dicionario",
    "data_legivel",
    "execucao",
    "explicar_metricas",
    "razao",
    "razoes",
    "salvar",
    "salvar_config_usada",
    "salvar_json",
    "salvar_reproducao",
    "salvar_series",
    "versoes",
]

#: File name used for the machine-readable result, as in ``docs/produto.md``.
NOME_DO_JSON = "resultado.json"

#: File written for each requested format, as in ``docs/produto.md``.
ARQUIVOS = {"json": NOME_DO_JSON, "html": "relatorio.html", "md": "relatorio.md"}

#: Files written on every run, whatever the formats, so the run can be redone or audited.
ARQUIVOS_DE_REPRODUCAO = {"series": "series.csv", "config": "config_usada.yaml"}

#: Every sentence of a reason, in one place, so the wording is changed here and nowhere
#: else. :func:`razao` joins them: the head, then the window when there is one, then what
#: the error is at the other end of the run, then the worst instant of a maximum.
MODELOS_DE_RAZAO = {
    "cabecalho": "{metrica} em {variavel} falhou: {valor} (limite {limite}{excesso})",
    "excesso": ", {excesso} acima do limite",
    "janela": ", erro concentrado entre t = {inicio} e t = {fim} ({fase})",
    TRANSIENTE: "; no estado estacionário o erro é {estacionario}",
    ESTACIONARIO: "; no transiente o erro é {transiente}",
    AO_LONGO: "; no transiente o erro é {transiente} e no estado estacionário, {estacionario}",
    "fim": ".",
    "pior_ponto": " O pior ponto está em t = {instante}.",
    "qualitativo": "{metrica} falhou: {descricao}.",
}


def como_dicionario(
    veredito: Veredito,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
    comparacao: qualitative.Comparacao | None = None,
    t_fim: float | None = None,
    registro: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the verdict as the structure written to ``resultado.json``.

    ``avisos`` are the warnings that do not belong to a single metric -- the reference
    numerical noise and the thresholds too close to it -- and come first, because they say
    how much of the numbers below is worth reading. ``registro`` is the ``execucao`` block
    built by :func:`execucao`, which goes last: it says how the numbers were obtained.
    """
    return {
        "veredito": veredito.nivel,
        "aprovado": veredito.aprovado,
        "porcentagem": veredito.porcentagem,
        "obrigatorios": _contagem(veredito.obrigatorios),
        "desejaveis": _contagem(veredito.desejaveis),
        "razoes": razoes(veredito),
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
                "razao": razao(item),
                "diagnostico": (
                    None if item.diagnostico is None else asdict(item.diagnostico)
                ),
                "avisos": list(item.avisos),
                "detalhes": dict(item.detalhes),
            }
            for item in veredito.criterios
        ],
        "execucao": None if registro is None else dict(registro),
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
    registro: Mapping[str, Any] | None = None,
) -> Path:
    """Write ``resultado.json`` into ``pasta``, creating the folder if needed."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_DO_JSON
    conteudo = json.dumps(
        como_dicionario(veredito, ruido, avisos, comparacao, t_fim, registro),
        ensure_ascii=False,
        indent=2,
    )
    caminho.write_text(conteudo + "\n", encoding="utf-8")
    return caminho


#: What each metric measures, in plain words, for the "O que cada métrica mede" section of
#: the readable report. No formula: the formulas are in the docstrings of
#: :mod:`reducheck.metrics` and in the text of the TCC. A metric registered from outside the
#: library has no entry here, and the report falls back to its own ``descricao``.
EXPLICACOES_DAS_METRICAS = {
    "nrmse": (
        "O erro médio ao longo de toda a simulação, comparado com a faixa que a variável "
        "percorre no original (do menor ao maior valor). 5% quer dizer que, em média, o "
        "simplificado fica afastado do original 5% dessa faixa. Olha a curva inteira, então "
        "um erro só no começo ou só no fim pesa pouco."
    ),
    "mape": (
        "O erro percentual médio: em cada instante, quanto o simplificado erra em relação ao "
        "valor do original naquele instante, e depois a média desses erros. Os instantes em "
        "que o original é praticamente zero ficam de fora, porque dividir por quase zero "
        "faria um erro minúsculo parecer enorme; o relatório avisa quantos saíram."
    ),
    "erro_max_abs": (
        "A maior distância entre as duas curvas em toda a simulação, na unidade da própria "
        "variável, e o instante em que ela acontece. Mostra o pior momento, e não a média."
    ),
    "erro_max_rel": (
        "O maior erro percentual em um único instante. Responde \"quanto o simplificado "
        "chega a errar no pior momento\", mesmo que esse momento seja curto e se dilua na "
        "média."
    ),
    "erro_estacionario": (
        "A diferença percentual entre os dois modelos no fim da simulação (ou na média do "
        "trecho final, quando configurado). Diz se o simplificado chega ao mesmo lugar, sem "
        "olhar o caminho até lá."
    ),
    "equilibrio": (
        "A diferença percentual entre os valores em que cada modelo para de mudar (o "
        "equilíbrio). Atenção: esse ponto pode estar muito depois do tempo simulado, e o "
        "relatório diz quando ele foi alcançado."
    ),
    "estabilidade_local": (
        "Se os dois modelos têm o mesmo tipo de equilíbrio: estável (depois de um pequeno "
        "empurrão, o sistema volta), instável (se afasta) ou marginal (fica no limite entre "
        "os dois). Não é um número: passa quando a classificação dos dois é a mesma."
    ),
}


def explicar_metricas(veredito: Veredito) -> list[dict[str, str]]:
    """Return what each metric used in ``veredito`` measures, in the order they appear.

    Only the metrics of this report, so the section stays short and every entry is one the
    reader is looking at in the table.
    """
    vistas: dict[str, str] = {}
    for item in veredito.criterios:
        if item.metrica in vistas:
            continue
        texto = EXPLICACOES_DAS_METRICAS.get(item.metrica)
        if texto is None:
            texto = item.descricao[:1].upper() + item.descricao[1:] if item.descricao else ""
            texto = texto and texto.rstrip(".") + "."
        vistas[item.metrica] = texto
    return [{"nome": nome, "texto": texto} for nome, texto in vistas.items()]


def razoes(veredito: Veredito) -> list[str]:
    """Return one sentence per failed item, in the order the criteria were declared."""
    return [texto for item in veredito.criterios if (texto := razao(item)) is not None]


def razao(item: ItemAvaliado) -> str | None:
    """Return why ``item`` failed -- by how much and where in time -- or ``None`` if it passed.

    The sentence follows the model of issue #19: the value against the threshold and the
    relative excess, the shortest window holding 80% of the error and the phase it falls
    in, and the same metric at the other end of the run, so a failure confined to the
    transient is told apart from one that never goes away. A metric that does not give its
    pointwise error has no window, and its sentence stops at the excess.
    """
    if item.passou:
        return None
    if item.valor is None:
        # A qualitative item has no number and no threshold: what it failed on is the
        # comparison of two labels, which the description already states.
        return MODELOS_DE_RAZAO["qualitativo"].format(
            metrica=item.metrica, descricao=item.descricao
        )

    def formatar(valor: float | None) -> str:
        return _porcento(valor) if item.fracao else _numero(valor)

    excesso = ""
    if item.limite is not None and item.limite > 0:
        relativo = (item.valor - item.limite) / item.limite
        excesso = MODELOS_DE_RAZAO["excesso"].format(excesso=_porcento(relativo))
    texto = MODELOS_DE_RAZAO["cabecalho"].format(
        metrica=item.metrica,
        variavel=item.variavel,
        valor=formatar(item.valor),
        limite=formatar(item.limite),
        excesso=excesso,
    )
    diagnostico = item.diagnostico
    if diagnostico is not None:
        texto += MODELOS_DE_RAZAO["janela"].format(
            inicio=_numero(diagnostico.inicio),
            fim=_numero(diagnostico.fim),
            fase=diagnostico.fase,
        )
        outra_ponta = (
            diagnostico.valor_transiente,
            diagnostico.valor_estacionario,
        )
        if None not in outra_ponta:
            texto += MODELOS_DE_RAZAO[diagnostico.fase].format(
                transiente=formatar(diagnostico.valor_transiente),
                estacionario=formatar(diagnostico.valor_estacionario),
            )
    texto += MODELOS_DE_RAZAO["fim"]
    instante = item.detalhes.get("instante")
    if instante is not None:
        texto += MODELOS_DE_RAZAO["pior_ponto"].format(instante=_numero(float(instante)))
    return texto


def salvar(
    veredito: Veredito,
    configuracao: Configuracao,
    series: Mapping[str, SerieComparada] | None = None,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
    caminho_config: Path | str | None = None,
    comparacao: qualitative.Comparacao | None = None,
    registro: Mapping[str, Any] | None = None,
) -> dict[str, Path]:
    """Write every format asked for in ``relatorio.formatos`` and return where each went.

    The plots are drawn once and reused by both readable formats, so asking for HTML and
    Markdown together does not simulate or draw anything twice. ``registro`` is the
    :func:`execucao` block; passing the one the caller already built keeps a single date
    across the JSON, the report and ``config_usada.yaml``.
    """
    if registro is None:
        registro = execucao(configuracao, caminho_config)
    pasta = Path(configuracao.relatorio.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    formatos = list(dict.fromkeys(configuracao.relatorio.formatos))
    caminhos: dict[str, Path] = {}

    if "json" in formatos:
        caminhos["json"] = salvar_json(
            veredito,
            pasta,
            ruido,
            avisos,
            comparacao,
            configuracao.simulacao.t_fim,
            registro,
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
        veredito, configuracao, graficos, ruido, avisos, caminho_config, comparacao, registro
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
    registro: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if registro is None:
        registro = execucao(configuracao, caminho_config)
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
        "metricas": explicar_metricas(veredito),
        "razoes": razoes(veredito),
        "avisos": [*avisos, *veredito.avisos],
        # The same reasons and warnings, each tagged with its variable (or "" when it is
        # about the whole run), so the HTML can filter them together with the table.
        "razoes_por_variavel": [
            (_filtravel(item.variavel), texto)
            for item in veredito.criterios
            if (texto := razao(item)) is not None
        ],
        "avisos_por_variavel": [
            *(("", aviso) for aviso in avisos),
            *(
                (_filtravel(item.variavel), f"{item.variavel}: {aviso}")
                for item in veredito.criterios
                for aviso in item.avisos
            ),
        ],
        "variaveis_do_filtro": [
            variavel.nome
            for variavel in configuracao.variaveis
            if variavel.simplificado is not None
        ],
        "qualitativo": _secao_qualitativa(comparacao, configuracao, veredito),
        "graficos": [_grafico(grafico) for grafico in graficos],
        "execucao": _execucao(configuracao, ruido, caminho_config, registro, avisos),
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
        "filtro": _filtravel(item.variavel),
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


def _filtravel(variavel: str) -> str:
    """Return the variable an element is filtered by, or "" for one about the whole model.

    ``estabilidade_local`` is one item with no variable (printed as "—"); it stays visible
    whatever the reader filters, since it is about every variable at once.
    """
    return "" if variavel == SEM_VARIAVEL else variavel


def _linha(item: ItemAvaliado) -> dict[str, str]:
    return {
        "metrica": item.metrica,
        "variavel": item.variavel,
        "filtro": _filtravel(item.variavel),
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
    registro: Mapping[str, Any],
    avisos: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """Return what is needed to tell two runs apart, as label/value pairs."""
    simulacao = configuracao.simulacao
    itens = [
        ("Data", data_legivel(registro["data"])),
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
    itens.append(("Versões", _versoes_em_texto(registro["versoes"])))
    return itens


# --- reproducibility ---------------------------------------------------------

#: How each library is named in a sentence, in the order the versions are listed.
_NOMES_DAS_BIBLIOTECAS = {
    "reducheck": "reducheck",
    "python": "Python",
    "libroadrunner": "libRoadRunner",
    "numpy": "numpy",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
}


def versoes() -> dict[str, str]:
    """Return the version of everything that can change a number of the run.

    matplotlib does not change a number, but it draws the plots, which are part of the
    output too.
    """
    return {
        "reducheck": reducheck.__version__,
        "python": ".".join(str(parte) for parte in sys.version_info[:3]),
        "libroadrunner": roadrunner.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
    }


def execucao(
    configuracao: Configuracao, caminho_config: Path | str | None = None
) -> dict[str, Any]:
    """Return the ``execucao`` block: when the run happened, with what, on which models.

    The SHA-256 of each SBML is what lets an auditor tell that a report was produced from
    *this* file and not from an older copy with the same name. The date is the only field
    that differs between two runs of the same configuration on the same machine.
    """
    return {
        "data": datetime.now().astimezone().isoformat(timespec="seconds"),
        "configuracao": None if caminho_config is None else str(caminho_config),
        "versoes": versoes(),
        "modelos": {
            papel: {"arquivo": str(arquivo), "sha256": _sha256(Path(arquivo))}
            for papel, arquivo in (
                ("original", configuracao.modelos.original),
                ("simplificado", configuracao.modelos.simplificado),
            )
        },
    }


def data_legivel(data: str) -> str:
    """Format the ISO date of :func:`execucao` the way the report shows it."""
    return datetime.fromisoformat(data).strftime("%d/%m/%Y %H:%M")


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _versoes_em_texto(versoes_: Mapping[str, str]) -> str:
    return ", ".join(
        f"{_NOMES_DAS_BIBLIOTECAS.get(nome, nome)} {versao}" for nome, versao in versoes_.items()
    )


def salvar_reproducao(
    configuracao: Configuracao,
    series: Mapping[str, SerieComparada],
    registro: Mapping[str, Any],
) -> dict[str, Path]:
    """Write ``series.csv`` and ``config_usada.yaml`` and return where each went.

    Both are written on every run, whatever ``relatorio.formatos`` asks for: the formats
    choose how the result is read, and these two are what lets someone redo it.
    """
    pasta = Path(configuracao.relatorio.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    return {
        "series": salvar_series(series, pasta),
        "config": salvar_config_usada(configuracao, pasta, registro),
    }


def salvar_series(series: Mapping[str, SerieComparada], pasta: Path | str) -> Path:
    """Write the time and the two series of every mapped variable to ``series.csv``.

    The series are the mapped ones -- a lumped variable is already summed --, because those
    are what the metrics compared. Every number is written with ``repr``, the shortest text
    that reads back as the same float, so the CSV redoes the analysis to the last digit.
    """
    caminho = Path(pasta) / ARQUIVOS_DE_REPRODUCAO["series"]
    comparadas = list(series.values())
    cabecalho = ["tempo"]
    colunas: list[numpy.ndarray] = []
    for serie in comparadas:
        cabecalho += [f"{serie.nome}_original", f"{serie.nome}_simplificado"]
        colunas += [serie.original, serie.simplificado]
    tempo = comparadas[0].tempo if comparadas else numpy.empty(0)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, lineterminator="\n")
        escritor.writerow(cabecalho)
        for indice, instante in enumerate(tempo):
            escritor.writerow(
                [repr(float(instante)), *(repr(float(coluna[indice])) for coluna in colunas)]
            )
    return caminho


def salvar_config_usada(
    configuracao: Configuracao, pasta: Path | str, registro: Mapping[str, Any]
) -> Path:
    """Write the effective configuration to ``config_usada.yaml``.

    Effective means after the defaults were filled in and the paths resolved, so the file
    states every choice the run made, including the ones nobody wrote. It is a valid
    configuration -- :func:`reducheck.config.carregar` reads it back into the same object --
    and the date and the versions go in a comment on top, because the schema accepts no
    key it does not know.
    """
    caminho = Path(pasta) / ARQUIVOS_DE_REPRODUCAO["config"]
    dados = configuracao.model_dump(mode="json")
    cabecalho = [
        "# Configuração efetiva usada pelo reducheck: valores padrão preenchidos e",
        "# caminhos resolvidos. Pode ser passada de novo para 'reducheck verificar'.",
        f"# Data: {registro['data']}",
        f"# Versões: {_versoes_em_texto(registro['versoes'])}",
    ]
    if registro.get("configuracao"):
        cabecalho.append(f"# Configuração de origem: {registro['configuracao']}")
    corpo = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False)
    caminho.write_text("\n".join(cabecalho) + "\n" + corpo, encoding="utf-8")
    return caminho


def _numero(valor: float | None) -> str:
    """Format a number the way the report of ``docs/produto.md`` shows it (decimal comma)."""
    if valor is None:
        return "—"
    return f"{valor:.5g}".replace(".", ",")


def _porcento(valor: float | None) -> str:
    """Format a fraction as a percentage with three significant digits: 0,081 -> 8,1%."""
    if valor is None:
        return "—"
    porcento = 100 * valor
    texto = f"{porcento:.0f}" if abs(porcento) >= 1000 else f"{porcento:.3g}"
    return texto.replace(".", ",") + "%"


def _porcentagem(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")
