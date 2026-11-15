r"""Sensibilidade do longo prazo ao teste de convergência, no modelo da Verly.

Rodar a partir da raiz do repositório:

    python estudo_de_caso/sensibilidade_convergencia.py

**A pergunta** (da orientadora, 15/11/2026): até onde o teste de convergência aceita, e o
veredito de longo prazo muda conforme ele? A questão 42 de `docs/questoes-em-aberto.md` já
mostrava que o erro de equilíbrio em `C1` depende de onde a integração para. Este script mede
isso de forma sistemática, de dois jeitos:

1. **Varredura da tolerância.** Roda a análise qualitativa da biblioteca
   (:func:`reducheck.qualitative.analisar`) com a tolerância do equilíbrio de 10⁻³ a 10⁻¹²,
   em vez do padrão de 10⁻⁶. Para cada uma, registra onde cada modelo parou, o resíduo, o
   erro de equilíbrio de cada variável core, a classificação de estabilidade e o veredito de
   longo prazo. Mostra a faixa de tolerâncias em que o veredito se mantém.
2. **Varredura do horizonte.** Sem teste de parada, integra os dois modelos até horizontes
   fixos de 720 · 10ᵏ dias e compara os dois pontos. Mostra *por que* o veredito muda: o erro
   de cada variável em função de onde se parou.

O erro de cada variável e o veredito saem de :func:`reducheck.verdict.avaliar`, com os
critérios qualitativos de `simp1.yaml`, então são calculados exatamente como no relatório.
Nada da biblioteca é alterado.

**O que este script não é.** Não é uma capacidade da biblioteca e não vale para outro modelo
sem leitura humana: a varredura é mecânica, mas dizer se uma mudança de veredito vem do
modelo ou do teste depende de quem conhece o modelo. A versão genérica ficou registrada como
trabalho futuro (questão 59 de `docs/questoes-em-aberto.md`).

Grava:

* `estudo_de_caso/resultados/convergencia/tolerancia.csv` e `horizonte.csv` (os números);
* `texto/tabelas/convergencia_tolerancia.tex` e `convergencia_horizonte.tex` (com PNG);
* `texto/figuras/convergencia_horizonte.pdf` e `.png`.
"""

from __future__ import annotations

import csv
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gerar_resultados import (  # noqa: E402
    ESTILO,
    FIGURAS,
    FORMATOS_DE_FIGURA,
    LARGURA_CM,
    TABELAS,
    UNIDADE,
    _escrever,
    _tabela,
    numero_latex,
)

import reducheck  # noqa: E402
from reducheck import config as _config  # noqa: E402
from reducheck import mapping, plots, qualitative, simulation, verdict  # noqa: E402
from reducheck.config import Configuracao, Criterio, Simulacao  # noqa: E402
from reducheck.mapping import SerieComparada  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
ESTUDO = RAIZ / "estudo_de_caso"
SAIDA = ESTUDO / "resultados" / "convergencia"

#: Tolerâncias do equilíbrio varridas, de 10⁻³ a 10⁻¹², uma por década. O padrão da
#: biblioteca (:data:`qualitative.TOLERANCIA_DO_EQUILIBRIO`) é 10⁻⁶.
TOLERANCIAS = tuple(10.0**-k for k in range(3, 13))

#: Horizontes fixos varridos, como múltiplos de ``t_fim``: 10⁰ a 10¹¹. O último é uma
#: década abaixo do teto da biblioteca (10¹² × ``t_fim``, :data:`qualitative.EXTENSOES_MAXIMAS`).
EXPOENTES_DO_HORIZONTE = tuple(range(0, 12))

#: Cores das variáveis na figura. As que não aparecem no gráfico (erro exatamente zero em
#: todos os horizontes) não precisam de cor, mas ficam aqui para a ordem ser estável.
CORES = {
    "Cb": "#222222",
    "Mb": "#00798c",
    "C1": "#d1495b",
    "C2": "#edae49",
    "E2": "#66a182",
}


#: Abaixo disto, um erro relativo é arredondamento (dez vezes o épsilon de máquina já fica
#: em 2×10⁻¹⁵) e não vai para a figura. Só a figura usa o piso: os CSV e as tabelas trazem
#: o número medido.
PISO_DA_FIGURA = 1e-12


@dataclass(frozen=True)
class Ponto:
    """Uma linha de uma das varreduras: o que mudou e o que se mediu."""

    #: A tolerância usada, ou ``None`` na varredura de horizonte.
    tolerancia: float | None
    #: O horizonte fixo, ou ``None`` na varredura de tolerância.
    horizonte: float | None
    #: Onde cada modelo parou (``None``: ``steadyState`` do libRoadRunner, sem integração).
    instante: Mapping[str, float | None] = field(default_factory=dict)
    #: Resíduo relativo de cada modelo no ponto.
    residuo: Mapping[str, float] = field(default_factory=dict)
    #: Classificação de estabilidade de cada modelo.
    classificacao: Mapping[str, str] = field(default_factory=dict)
    #: Erro relativo de equilíbrio por variável, como o critério ``equilibrio`` calcula.
    erro: Mapping[str, float] = field(default_factory=dict)
    #: Itens de longo prazo que passaram, e quantos são.
    passados: int = 0
    total: int = 0
    #: APROVADO, APROVADO COM RESSALVAS ou REPROVADO; vazio se a análise falhou.
    nivel: str = ""
    #: Por que a análise falhou, quando falhou (por exemplo, não convergiu em 12 extensões).
    falha: str = ""


# --- Preparação ----------------------------------------------------------------------


def criterios_de_longo_prazo(configuracao: Configuracao) -> list[Criterio]:
    """Só os critérios qualitativos da configuração, os que esta análise pode mudar."""
    return [
        criterio
        for criterio in configuracao.criterios
        if criterio.metrica in _config.ANALISES_QUALITATIVAS
    ]


def series_mapeadas(configuracao: Configuracao) -> Mapping[str, SerieComparada]:
    """As séries dos 720 dias, que o critério ``equilibrio`` usa para o piso do denominador."""
    sobrescrever = configuracao.simulacao.sobrescrever
    trajetorias = {
        papel: simulation.simular(
            getattr(configuracao.modelos, papel),
            configuracao.simulacao,
            mapping.nomes_simulados(configuracao.variaveis, papel),
            sobrescrever.para(papel),
        )
        for papel in ("original", "simplificado")
    }
    return mapping.mapear(
        configuracao.variaveis, trajetorias["original"], trajetorias["simplificado"]
    )


# --- Um ponto de cada varredura ------------------------------------------------------


def equilibrio_no_horizonte(
    caminho_sbml: Path, condicoes: Simulacao, horizonte: float, sobrescrever: object
) -> qualitative.Analise:
    """Integra até ``horizonte``, sem teste de parada, e trata o ponto como o equilíbrio.

    O resíduo é medido como :func:`qualitative.encontrar_equilibrio` mede (``max|dx/dt|``
    relativo ao do instante inicial), para poder ser lido contra as mesmas tolerâncias.
    ``convergiu`` diz se esse ponto passaria no teste padrão de 10⁻⁶.
    """
    modelo = qualitative.preparar_modelo(caminho_sbml, condicoes, sobrescrever)
    nomes = qualitative.estado(modelo)
    modelo.reset()
    escala = float(np.max(np.abs(qualitative.taxas(modelo)))) or 1.0
    modelo.simulate(condicoes.t_inicio, horizonte, 2)
    absoluto = float(np.max(np.abs(qualitative.taxas(modelo))))
    ponto = dict(zip(nomes, qualitative.valores(modelo, nomes), strict=True))
    equilibrio = qualitative.Equilibrio(
        ponto=ponto,
        metodo=f"integração até t = {horizonte:g}, sem teste de parada",
        residuo=absoluto / escala,
        residuo_absoluto=absoluto,
        escala_de_taxa=escala,
        instante=horizonte,
        tolerancia=qualitative.TOLERANCIA_DO_EQUILIBRIO,
        convergiu=absoluto / escala <= qualitative.TOLERANCIA_DO_EQUILIBRIO,
    )
    estabilidade = qualitative.estabilidade_local(modelo, ponto)
    return qualitative.Analise(papel="", equilibrio=equilibrio, estabilidade=estabilidade)


def medir(
    analisar: Callable[[str], qualitative.Analise],
    configuracao: Configuracao,
    series: Mapping[str, SerieComparada],
    tolerancia: float | None = None,
    horizonte: float | None = None,
) -> Ponto:
    """Analisa os dois modelos com ``analisar`` e aplica os critérios de longo prazo."""
    try:
        comparacao = qualitative.Comparacao(
            original=analisar("original"), simplificado=analisar("simplificado")
        )
    except qualitative.ErroDeQualitativo as erro:
        return Ponto(tolerancia=tolerancia, horizonte=horizonte, falha=str(erro))
    veredito = verdict.avaliar(
        criterios_de_longo_prazo(configuracao),
        series,
        core=configuracao.nomes_core(),
        niveis=configuracao.relatorio.niveis,
        comparacao=comparacao,
    )
    analises = {"original": comparacao.original, "simplificado": comparacao.simplificado}
    return Ponto(
        tolerancia=tolerancia,
        horizonte=horizonte,
        instante={papel: a.equilibrio.instante for papel, a in analises.items()},
        residuo={papel: a.equilibrio.residuo for papel, a in analises.items()},
        classificacao={papel: a.estabilidade.classificacao for papel, a in analises.items()},
        erro={
            item.variavel: float(item.valor)
            for item in veredito.criterios
            if item.metrica == "equilibrio" and item.valor is not None
        },
        passados=sum(item.passou for item in veredito.criterios),
        total=len(veredito.criterios),
        nivel=veredito.nivel,
    )


def varrer_tolerancia(
    configuracao: Configuracao, series: Mapping[str, SerieComparada]
) -> list[Ponto]:
    """Roda a análise da biblioteca como ela é, trocando só a tolerância do equilíbrio."""
    sobrescrever = configuracao.simulacao.sobrescrever
    pontos = []
    for tolerancia in TOLERANCIAS:

        def analisar(papel: str, tolerancia: float = tolerancia) -> qualitative.Analise:
            return qualitative.analisar(
                getattr(configuracao.modelos, papel),
                configuracao.simulacao,
                sobrescrever.para(papel),
                papel=papel,
                tolerancia_do_equilibrio=tolerancia,
            )

        pontos.append(medir(analisar, configuracao, series, tolerancia=tolerancia))
        print(f"  tolerância {tolerancia:g}: {_resumo(pontos[-1])}")
    return pontos


def varrer_horizonte(
    configuracao: Configuracao, series: Mapping[str, SerieComparada]
) -> list[Ponto]:
    """Os dois modelos integrados até o mesmo horizonte fixo, sem teste de parada."""
    condicoes = configuracao.simulacao
    sobrescrever = condicoes.sobrescrever
    pontos = []
    for expoente in EXPOENTES_DO_HORIZONTE:
        horizonte = condicoes.t_fim * 10.0**expoente

        def analisar(papel: str, horizonte: float = horizonte) -> qualitative.Analise:
            return equilibrio_no_horizonte(
                getattr(configuracao.modelos, papel),
                condicoes,
                horizonte,
                sobrescrever.para(papel),
            )

        pontos.append(medir(analisar, configuracao, series, horizonte=horizonte))
        print(f"  horizonte {horizonte:g}: {_resumo(pontos[-1])}")
    return pontos


def _parada_padrao(pontos: Sequence[Ponto]) -> float | None:
    """Onde o original parou com a tolerância padrão, para marcar na figura."""
    for p in pontos:
        if p.tolerancia is not None and math.isclose(
            p.tolerancia, qualitative.TOLERANCIA_DO_EQUILIBRIO
        ):
            return p.instante.get("original")
    return None


def _resumo(ponto: Ponto) -> str:
    if ponto.falha:
        return "falhou"
    erros = ", ".join(f"{nome} {valor:.3g}" for nome, valor in ponto.erro.items())
    return f"{ponto.nivel} {ponto.passados}/{ponto.total}; {erros}"


# --- Leitura dos resultados ----------------------------------------------------------


def faixa_estavel(pontos: Sequence[Ponto], referencia: float) -> tuple[float, float] | None:
    """Devolve a faixa contínua de tolerâncias, em torno de ``referencia``, de mesmo veredito.

    O par é ``(mais frouxa, mais apertada)``, ou ``None`` se a análise falhou na própria
    referência. "Mesmo veredito" é mesmo nível, mesma contagem de itens *e* mesmo ponto de
    parada dos dois modelos: um item que troca de lado sem mudar o nível ainda é uma
    mudança, e a mesma contagem medida em outro ponto é coincidência (na Verly, 10⁻¹¹ dá
    5/6 como o padrão, mas com `C1` errando 93% em vez de 9,3%).
    """
    ordenados = sorted(
        (p for p in pontos if p.tolerancia is not None),
        key=lambda p: p.tolerancia,
        reverse=True,
    )
    indices = [i for i, p in enumerate(ordenados) if math.isclose(p.tolerancia, referencia)]
    if not indices or ordenados[indices[0]].falha:
        return None
    i = indices[0]
    def chave(p: Ponto) -> tuple[object, ...]:
        return (p.nivel, p.passados, tuple(sorted(p.instante.items())))

    alvo = chave(ordenados[i])

    def igual(p: Ponto) -> bool:
        return not p.falha and chave(p) == alvo

    inicio = i
    while inicio > 0 and igual(ordenados[inicio - 1]):
        inicio -= 1
    fim = i
    while fim < len(ordenados) - 1 and igual(ordenados[fim + 1]):
        fim += 1
    return ordenados[inicio].tolerancia, ordenados[fim].tolerancia


# --- Saídas --------------------------------------------------------------------------


def gravar_csv(pontos: Sequence[Ponto], variaveis: Sequence[str], caminho: Path) -> Path:
    """Uma linha por ponto, com tudo o que foi medido, para quem quiser refazer a figura."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    papeis = ("original", "simplificado")
    cabecalho = [
        "tolerancia",
        "horizonte",
        *(f"instante_{p}" for p in papeis),
        *(f"residuo_{p}" for p in papeis),
        *(f"estabilidade_{p}" for p in papeis),
        *(f"erro_{v}" for v in variaveis),
        "passados",
        "total",
        "veredito",
        "falha",
    ]
    with caminho.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(cabecalho)
        for p in pontos:
            escritor.writerow(
                [
                    _ou_vazio(p.tolerancia),
                    _ou_vazio(p.horizonte),
                    *(_ou_vazio(p.instante.get(papel)) for papel in papeis),
                    *(_ou_vazio(p.residuo.get(papel)) for papel in papeis),
                    *(p.classificacao.get(papel, "") for papel in papeis),
                    *(_ou_vazio(p.erro.get(v)) for v in variaveis),
                    p.passados,
                    p.total,
                    p.nivel,
                    p.falha,
                ]
            )
    return caminho


def _ou_vazio(valor: float | None) -> str:
    return "" if valor is None else repr(float(valor))


def _cabecalho(latex: str) -> str:
    """Troca o comentário de origem que :func:`gerar_resultados._tabela` escreve."""
    return latex.replace(
        "gerar_resultados.py", "sensibilidade_convergencia.py", 1
    )


def _celula_erro(valor: float | None, limite: float) -> str:
    """O erro na tabela, em negrito quando passa do limite do critério."""
    if valor is None:
        return "---"
    texto = numero_latex(valor)
    return f"\\textbf{{{texto}}}" if valor > limite else texto


def _instante(ponto: Ponto) -> str:
    """Onde os dois modelos pararam: um número se coincidem, ``original / simplificado`` se não.

    Cada modelo passa pelo teste de convergência sozinho, então eles podem parar em
    instantes diferentes -- e aí o critério ``equilibrio`` compara pontos de tempos
    distintos. A tabela tem que mostrar isso. ``SS`` é o ``steadyState`` do libRoadRunner,
    que não integra e não tem instante.
    """
    if not ponto.instante:
        return "---"
    textos = [
        "SS" if valor is None else numero_latex(valor)
        for valor in (ponto.instante.get("original"), ponto.instante.get("simplificado"))
    ]
    return textos[0] if textos[0] == textos[1] else " / ".join(textos)


def _veredito(ponto: Ponto) -> str:
    if ponto.falha:
        return "não convergiu"
    nivel = "aprovado" if ponto.nivel == verdict.APROVADO else ponto.nivel.lower()
    return f"{nivel} ({ponto.passados}/{ponto.total})"


def tabela_tolerancia(
    pontos: Sequence[Ponto], variaveis: Sequence[str], limite: float
) -> str:
    """Tolerância × (onde parou, erro por variável, veredito de longo prazo)."""
    linhas = []
    for p in pontos:
        assert p.tolerancia is not None
        rotulo = f"$10^{{{round(math.log10(p.tolerancia))}}}$"
        if math.isclose(p.tolerancia, qualitative.TOLERANCIA_DO_EQUILIBRIO):
            rotulo += " (padrão)"
        linhas.append(
            (
                rotulo,
                _instante(p),
                *(_celula_erro(p.erro.get(v), limite) for v in variaveis),
                _veredito(p),
            )
        )
    return _cabecalho(_tabela(
        ["Tolerância", "Parou em", *(f"\\texttt{{{v}}}" for v in variaveis), "Longo prazo"],
        linhas,
        "ll" + "r" * len(variaveis) + "l",
        "Sensibilidade do critério de equilíbrio à tolerância do teste de convergência "
        f"(resíduo relativo $\\max|dx/dt|$). Erro relativo entre os equilíbrios dos dois "
        f"modelos; em negrito, acima do limite de {numero_latex(limite)}. "
        "``Parou em'' dá o instante de cada modelo (original / simplificado) quando "
        "diferem; SS é o \\texttt{steadyState} do libRoadRunner, sem integração. "
        f"Tempo em {UNIDADE}.",
        "tab:convergencia-tolerancia",
    ))


def tabela_horizonte(
    pontos: Sequence[Ponto], variaveis: Sequence[str], limite: float, t_fim: float
) -> str:
    """Horizonte fixo × (resíduo, erro por variável, veredito de longo prazo)."""
    linhas = []
    for p in pontos:
        assert p.horizonte is not None
        residuo = max(p.residuo.values()) if p.residuo else float("nan")
        linhas.append(
            (
                f"$10^{{{round(math.log10(p.horizonte / t_fim))}}}$",
                numero_latex(residuo),
                *(_celula_erro(p.erro.get(v), limite) for v in variaveis),
                _veredito(p),
            )
        )
    return _cabecalho(_tabela(
        [
            "Horizonte ($\\times t_{\\mathrm{fim}}$)",
            "Resíduo",
            *(f"\\texttt{{{v}}}" for v in variaveis),
            "Longo prazo",
        ],
        linhas,
        "lr" + "r" * len(variaveis) + "l",
        "Erro relativo entre os dois modelos quando ambos são integrados até o mesmo "
        f"horizonte fixo, sem teste de parada ($t_{{\\mathrm{{fim}}}} = {t_fim:g}$ {UNIDADE}). "
        "O resíduo é o maior dos dois modelos. Em negrito, acima do limite de "
        f"{numero_latex(limite)}.",
        "tab:convergencia-horizonte",
    ))


def figura_horizonte(
    pontos: Sequence[Ponto],
    variaveis: Sequence[str],
    limite: float,
    t_fim: float,
    caminho: Path,
    parada: float | None = None,
) -> tuple[Path, ...]:
    """Dois painéis: o resíduo e o erro por variável, ambos contra o horizonte.

    Erros abaixo de :data:`PISO_DA_FIGURA` são arredondamento de ponto flutuante (``Mb`` e
    ``E2`` na Verly ficam em 10⁻¹⁶, ou exatamente 0, que nem cabe num eixo logarítmico), e
    não são desenhados; a legenda da figura no texto precisa dizer isso. A linha vertical
    marca onde a biblioteca para com a tolerância padrão, lida de ``parada``.
    """
    vezes = np.array([p.horizonte / t_fim for p in pontos if p.horizonte is not None])
    residuos = np.array([max(p.residuo.values()) for p in pontos])
    largura = LARGURA_CM / 2.54
    with plt.rc_context(ESTILO):
        figura, (acima, abaixo) = plt.subplots(
            2, 1, figsize=(largura, 0.62 * largura), sharex=True
        )
        acima.loglog(vezes, residuos, marker="o", color="#222222", markersize=3)
        acima.axhline(
            qualitative.TOLERANCIA_DO_EQUILIBRIO,
            color="#888888",
            linestyle=":",
            label="tolerância padrão (10⁻⁶)",
        )
        acima.set_ylabel("resíduo relativo")
        acima.legend(frameon=False, loc="center left", bbox_to_anchor=(1.01, 0.5))

        for nome in variaveis:
            erros = np.array([p.erro.get(nome, np.nan) for p in pontos], dtype=float)
            erros[erros < PISO_DA_FIGURA] = np.nan
            if np.all(np.isnan(erros)):
                continue
            abaixo.loglog(
                vezes, erros, marker="o", markersize=3, label=nome, color=CORES.get(nome)
            )
        abaixo.axhline(
            limite,
            color="#888888",
            linestyle="--",
            label=f"limite ({limite:g})".replace(".", ","),
        )
        if parada is not None:
            for eixo in (acima, abaixo):
                eixo.axvline(parada / t_fim, color="#bbbbbb", linewidth=0.8)
            acima.annotate(
                "padrão para aqui",
                xy=(parada / t_fim, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(3, -10),
                textcoords="offset points",
                fontsize=7,
                color="#666666",
            )
        abaixo.set_ylabel("erro relativo no equilíbrio")
        abaixo.set_xlabel(f"horizonte de integração (× t_fim = {t_fim:g} {UNIDADE})")
        abaixo.legend(frameon=False, loc="center left", bbox_to_anchor=(1.01, 0.5))
        figura.tight_layout()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        gravados = tuple(caminho.with_suffix(f".{formato}") for formato in FORMATOS_DE_FIGURA)
        for gravado in gravados:
            figura.savefig(gravado, dpi=plots.DPI)
        plt.close(figura)
    return gravados


# --- Execução ------------------------------------------------------------------------


def main() -> None:
    """Roda as duas varreduras e grava os números, as tabelas e a figura."""
    configuracao = _config.carregar(ESTUDO / "simp1.yaml")
    criterios = criterios_de_longo_prazo(configuracao)
    (limite,) = {c.limite for c in criterios if c.metrica == "equilibrio"}
    variaveis = list(configuracao.nomes_core())
    series = series_mapeadas(configuracao)
    t_fim = configuracao.simulacao.t_fim

    print(f"reducheck {reducheck.__version__}; varredura da tolerância")
    tolerancia = varrer_tolerancia(configuracao, series)
    print("varredura do horizonte")
    horizonte = varrer_horizonte(configuracao, series)

    faixa = faixa_estavel(tolerancia, qualitative.TOLERANCIA_DO_EQUILIBRIO)
    if faixa is None:
        print("o veredito padrão não pôde ser medido")
    else:
        print(
            f"mesmo veredito que o padrão para tolerâncias de {faixa[0]:g} a {faixa[1]:g}"
        )

    gerados = [
        gravar_csv(tolerancia, variaveis, SAIDA / "tolerancia.csv"),
        gravar_csv(horizonte, variaveis, SAIDA / "horizonte.csv"),
        *_escrever(
            TABELAS / "convergencia_tolerancia.tex",
            tabela_tolerancia(tolerancia, variaveis, limite),
        ),
        *_escrever(
            TABELAS / "convergencia_horizonte.tex",
            tabela_horizonte(horizonte, variaveis, limite, t_fim),
        ),
        *figura_horizonte(
            horizonte,
            variaveis,
            limite,
            t_fim,
            FIGURAS / "convergencia_horizonte",
            parada=_parada_padrao(tolerancia),
        ),
    ]
    for caminho in gerados:
        print(f"gravado: {caminho.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
