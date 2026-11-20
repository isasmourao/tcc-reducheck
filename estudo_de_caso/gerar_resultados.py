r"""Gera os resultados do estudo de caso para o texto do TCC.

Rodar a partir da raiz do repositório:

    python estudo_de_caso/gerar_resultados.py

O que faz, em ordem:

1. refaz a verificação do estudo de caso (`simp1.yaml`, que responde às duas perguntas:
   trajetória e longo prazo) com a versão atual da biblioteca, regravando
   `estudo_de_caso/resultados/`;
2. desenha as figuras do texto em `texto/figuras/`, cada uma em PDF vetorial e em PNG de
   300 dpi, num estilo só;
3. escreve as tabelas em LaTeX em `texto/tabelas/`: critérios × resultado, equilíbrios,
   autovalores e tempo de execução;
4. mede o tempo de simulação de cada modelo (10 execuções, média e desvio).

Não faz parte da biblioteca: é o caminho do estudo de caso até o texto. Os números das
tabelas saem do mesmo :class:`reducheck.Resultado` que gera o relatório, então o texto e o
relatório não podem discordar. As tabelas usam `booktabs` (`\toprule`, `\midrule`).
"""

from __future__ import annotations

import math
import statistics
import textwrap
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import roadrunner  # noqa: E402
from matplotlib.ticker import ScalarFormatter  # noqa: E402

import reducheck  # noqa: E402
from reducheck import mapping, plots, qualitative, simulation  # noqa: E402
from reducheck.config import Simulacao  # noqa: E402
from reducheck.mapping import SerieComparada  # noqa: E402
from reducheck.verdict import LONGO_PRAZO, TRAJETORIA, ItemAvaliado, Veredito  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
ESTUDO = RAIZ / "estudo_de_caso"
FIGURAS = RAIZ / "texto" / "figuras"
TABELAS = RAIZ / "texto" / "tabelas"

#: Quantas vezes cada modelo é simulado para a tabela de tempo.
EXECUCOES = 10

#: Unidade de tempo do estudo de caso. Os SBML não a declaram; "dias" vem do TCC I,
#: seção 4 ("720 dias").
UNIDADE = "dias"

#: Estilo comum a todas as figuras. A largura é a da coluna de texto do template SBC
#: (cerca de 16 cm) e as fontes são de 9 pt nesse tamanho, então a figura continua legível
#: ocupando meia página, que é o tamanho em que ela vai entrar no texto.
LARGURA_CM = 16.0
ESTILO: dict[str, object] = {
    "font.family": "serif",
    "mathtext.fontset": "dejavuserif",
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "lines.linewidth": 1.4,
    "pdf.fonttype": 42,
    "savefig.bbox": "tight",
}
#: Em que formatos cada figura é gravada, com o mesmo nome.
FORMATOS_DE_FIGURA = ("pdf", "png")
COR_ORIGINAL = "#222222"
COR_SIMPLIFICADO = "#d1495b"

ROTULOS = {"original": "Original", "simplificado": "Simplificação 1"}


@dataclass(frozen=True)
class Tempos:
    """Os tempos de cada execução de um modelo, em segundos."""

    #: Ler o SBML e compilar o modelo (libRoadRunner gera código de máquina na carga).
    carga: list[float] = field(default_factory=list)
    #: Só a integração, de ``t_inicio`` a ``t_fim``.
    integracao: list[float] = field(default_factory=list)


# --- Números em LaTeX ----------------------------------------------------------------


def _mantissa(texto: str) -> str:
    return texto.replace(".", "{,}")


def numero_latex(valor: float) -> str:
    r"""Escreve ``valor`` com três algarismos significativos e vírgula decimal.

    Entre 10⁻³ e 10⁴ sai em notação fixa (``0{,}450``); fora disso, científica
    (``$7{,}40 \times 10^{-10}$``). Zero sai ``0``, porque "0,00" sugeriria um
    arredondamento que não houve.
    """
    if valor == 0:
        return "0"
    if math.isinf(valor) or math.isnan(valor):
        return "---"
    magnitude = abs(valor)
    if 100 <= magnitude < 1e4:
        return f"{valor:.0f}"
    if 1e-3 <= magnitude < 100:
        # "#" mantém os zeros à direita (0,450), e "g" refaz as casas depois de arredondar,
        # então 0,99999 sai "1,00" e não "1,000".
        return _mantissa(f"{valor:#.3g}".rstrip("."))
    mantissa, expoente = f"{valor:.2e}".split("e")
    return f"${_mantissa(mantissa)} \\times 10^{{{int(expoente)}}}$"


def autovalor_latex(valor: complex) -> str:
    r"""Escreve um autovalor; os complexos saem como ``a \pm b i``."""
    real = numero_latex(float(valor.real)).strip("$")
    if valor.imag == 0:
        return f"${real}$"
    imaginaria = numero_latex(abs(float(valor.imag))).strip("$")
    return f"${real} \\pm {imaginaria}\\, i$"


def _texto(valor: str) -> str:
    return valor.replace("_", "\\_")


def _tabela(
    cabecalho: Sequence[str],
    linhas: Iterable[Sequence[str]],
    alinhamento: str,
    legenda: str,
    rotulo: str,
) -> str:
    corpo = [" & ".join(linha) + " \\\\" for linha in linhas]
    return "\n".join(
        [
            "% Gerado por estudo_de_caso/gerar_resultados.py. Não editar à mão.",
            "\\begin{table}[htbp]",
            "\\centering",
            f"\\caption{{{legenda}}}",
            f"\\label{{{rotulo}}}",
            f"\\begin{{tabular}}{{{alinhamento}}}",
            "\\toprule",
            " & ".join(cabecalho) + " \\\\",
            "\\midrule",
            *corpo,
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )


# --- Tabelas -------------------------------------------------------------------------


def _variavel(nome: str) -> str:
    # `estabilidade_local` é sobre o modelo inteiro e chega com "—" no lugar da variável.
    return "---" if nome in ("", "—") else f"\\texttt{{{_texto(nome)}}}"


def _valor(item: ItemAvaliado) -> str:
    if item.valor is None:
        return _texto(item.valor_texto) or "---"
    return numero_latex(item.valor)


def tabela_criterios(itens: Sequence[ItemAvaliado], legenda: str, rotulo: str) -> str:
    """Uma linha por par (critério, variável): valor, limite, nível e resultado."""
    linhas = [
        (
            f"\\texttt{{{_texto(item.metrica)}}}",
            _variavel(item.variavel),
            _valor(item),
            "---" if item.limite is None else numero_latex(item.limite),
            "obrigatório" if item.obrigatorio else "desejável",
            "passou" if item.passou else "falhou",
        )
        for item in itens
    ]
    return _tabela(
        ["Critério", "Variável", "Valor", "Limite", "Nível", "Resultado"],
        linhas,
        "llrrll",
        legenda,
        rotulo,
    )


def tabela_equilibrios(itens: Sequence[ItemAvaliado], legenda: str, rotulo: str) -> str:
    """O equilíbrio de cada variável nos dois modelos, a partir dos itens ``equilibrio``.

    Usa os números que o critério já calculou (``detalhes``), e não uma conta própria,
    para o erro relativo da tabela ser o mesmo que decidiu o veredito.
    """
    linhas = [
        (
            f"\\texttt{{{_texto(item.variavel)}}}",
            numero_latex(item.detalhes["equilibrio_original"]),
            numero_latex(item.detalhes["equilibrio_simplificado"]),
            _valor(item),
            "passou" if item.passou else "falhou",
        )
        for item in itens
        if item.metrica == "equilibrio"
    ]
    return _tabela(
        ["Variável", ROTULOS["original"], ROTULOS["simplificado"], "Erro relativo", "Resultado"],
        linhas,
        "lrrrl",
        legenda,
        rotulo,
    )


def tabela_autovalores(
    comparacao: qualitative.Comparacao, legenda: str, rotulo: str, quantos: int = 3
) -> str:
    """Dimensão, instante do equilíbrio, classificação e os autovalores dominantes."""
    analises = (comparacao.original, comparacao.simplificado)

    def instante(analise: qualitative.Analise) -> str:
        valor = analise.equilibrio.instante
        return "---" if valor is None else numero_latex(valor)

    linhas: list[tuple[str, ...]] = [
        ("Variáveis de estado", *(str(len(a.equilibrio.ponto)) for a in analises)),
        (f"Equilíbrio alcançado em $t$ ({UNIDADE})", *(instante(a) for a in analises)),
        ("Classificação", *(a.estabilidade.classificacao for a in analises)),
    ]
    for indice in range(quantos):
        linhas.append(
            (
                f"$\\lambda_{{{indice + 1}}}$",
                *(
                    autovalor_latex(a.estabilidade.autovalores[indice])
                    if indice < len(a.estabilidade.autovalores)
                    else "---"
                    for a in analises
                ),
            )
        )
    return _tabela(
        ["", ROTULOS["original"], ROTULOS["simplificado"]], linhas, "lrr", legenda, rotulo
    )


def _media_e_desvio(valores: Sequence[float]) -> str:
    milissegundos = [valor * 1000 for valor in valores]
    desvio = statistics.stdev(milissegundos) if len(milissegundos) > 1 else 0.0
    return f"{numero_latex(statistics.mean(milissegundos))} $\\pm$ {numero_latex(desvio)}"


def tabela_tempo(tempos: Mapping[str, Tempos], legenda: str, rotulo: str) -> str:
    """Média ± desvio padrão (amostral) da carga e da integração, em milissegundos.

    A última coluna divide a integração média de cada modelo pela do primeiro da lista,
    que é o original: é o ganho de eficiência que motivou a simplificação.
    """
    referencia = statistics.mean(next(iter(tempos.values())).integracao)
    linhas = [
        (
            nome,
            _media_e_desvio(medidos.carga),
            _media_e_desvio(medidos.integracao),
            numero_latex(statistics.mean(medidos.integracao) / referencia),
        )
        for nome, medidos in tempos.items()
    ]
    return _tabela(
        ["Modelo", "Carga (ms)", "Integração (ms)", "Integração / original"],
        linhas,
        "lrrr",
        legenda,
        rotulo,
    )


def ler_tabela(latex: str) -> tuple[str, list[str], list[list[str]]]:
    """Separa uma tabela escrita por :func:`_tabela` em legenda, cabeçalho e linhas."""
    linhas = latex.splitlines()
    legenda = next(linha for linha in linhas if linha.startswith("\\caption{"))
    topo, meio, fim = (linhas.index(marca) for marca in ("\\toprule", "\\midrule", "\\bottomrule"))

    def celulas(linha: str) -> list[str]:
        return [celula.strip() for celula in linha.strip().removesuffix("\\\\").split("&")]

    return (
        legenda.removeprefix("\\caption{").removesuffix("}"),
        celulas(linhas[topo + 1]),
        [celulas(linha) for linha in linhas[meio + 1 : fim]],
    )


def para_mathtext(celula: str) -> str:
    r"""Escreve uma célula em LaTeX como o texto que o matplotlib desenha.

    Só os trechos fora de ``$...$`` mudam; dentro, o mathtext do matplotlib entende o que
    este script escreve (``{,}``, ``\times``, ``10^{-10}``, ``\pm``, ``\lambda_{1}``).
    """
    partes = celula.split("$")
    for indice in range(0, len(partes), 2):
        texto = partes[indice]
        while "\\texttt{" in texto:
            inicio = texto.index("\\texttt{")
            fim = texto.index("}", inicio)
            texto = texto[:inicio] + texto[inicio + len("\\texttt{") : fim] + texto[fim + 1 :]
        partes[indice] = (
            texto.replace("{,}", ",").replace("\\_", "_").replace("\\%", "%").replace("---", "—")
        )
    return "$".join(partes)


def tabela_png(latex: str, caminho: Path) -> Path:
    """Desenha a tabela em PNG de 300 dpi, com os três filetes do ``booktabs``."""
    legenda, cabecalho, linhas = ler_tabela(latex)
    largura = LARGURA_CM / 2.54
    with plt.rc_context(ESTILO):
        figura, eixo = plt.subplots(figsize=(largura, 0.25 * (len(linhas) + 1) + 0.4))
        eixo.axis("off")
        tabela = eixo.table(
            cellText=[[para_mathtext(celula) for celula in linha] for linha in linhas],
            colLabels=[para_mathtext(celula) for celula in cabecalho],
            loc="upper center",
            cellLoc="center",
        )
        tabela.auto_set_font_size(False)
        tabela.set_fontsize(9)
        tabela.auto_set_column_width(list(range(len(cabecalho))))
        for (linha, _coluna), celula in tabela.get_celld().items():
            if linha == 0:
                celula.visible_edges = "TB"
                celula.get_text().set_fontweight("bold")
            else:
                celula.visible_edges = "B" if linha == len(linhas) else ""
        eixo.set_title(textwrap.fill(para_mathtext(legenda), 100), loc="left")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        figura.savefig(caminho, dpi=plots.DPI)
        plt.close(figura)
    return caminho


# --- Tempo de execução ---------------------------------------------------------------


def medir_tempo(
    caminho_sbml: Path | str,
    condicoes: Simulacao,
    variaveis: Sequence[str],
    execucoes: int = EXECUCOES,
) -> Tempos:
    """Simula o modelo ``execucoes`` vezes, medindo carga e integração separadas.

    Cada execução carrega o modelo de novo, pelo mesmo :func:`simulation.preparar` que a
    biblioteca usa, então o solver e as tolerâncias são os da verificação. Uma execução de
    aquecimento, antes, é descartada: a primeira carga do processo inclui inicializar o
    libRoadRunner, que não é custo do modelo.

    O libRoadRunner guarda o modelo compilado e, sem ``LOADSBMLOPTIONS_RECOMPILE``, a
    segunda carga do mesmo arquivo leva ~6 ms em vez de ~95 ms: mediria o cache, não a
    compilação. Por isso a opção fica ligada durante a medição e é restaurada no fim.
    """
    opcao = roadrunner.Config.LOADSBMLOPTIONS_RECOMPILE
    anterior = roadrunner.Config.getValue(opcao)
    roadrunner.Config.setValue(opcao, True)
    medidos = Tempos()
    try:
        for indice in range(execucoes + 1):
            inicio = time.perf_counter()
            modelo = simulation.preparar(caminho_sbml, condicoes, variaveis)
            carregado = time.perf_counter()
            modelo.selections = ["time", *variaveis]
            modelo.simulate(condicoes.t_inicio, condicoes.t_fim, condicoes.pontos)
            fim = time.perf_counter()
            if indice > 0:
                medidos.carga.append(carregado - inicio)
                medidos.integracao.append(fim - carregado)
    finally:
        roadrunner.Config.setValue(opcao, anterior)
    return medidos


# --- Figuras -------------------------------------------------------------------------


class _FormatoComVirgula(ScalarFormatter):
    """Rótulos de eixo com vírgula decimal, como no resto do texto."""

    def __init__(self) -> None:
        super().__init__(useMathText=True)
        # 300000 vira 3 × 10⁵ no canto do eixo, como nas tabelas.
        self.set_powerlimits((-3, 4))

    def __call__(self, x: float, pos: int | None = None) -> str:
        return super().__call__(x, pos).replace(".", "{,}")

    def get_offset(self) -> str:
        return super().get_offset().replace(".", "{,}")


def figura_trajetorias(
    series: Mapping[str, SerieComparada],
    nomes: Sequence[str],
    caminho: Path,
    colunas: int = 3,
) -> tuple[Path, ...]:
    """Um painel por variável, com o original em linha cheia e a simplificação tracejada.

    ``caminho`` é o nome sem extensão: a mesma figura é gravada em cada um de
    :data:`FORMATOS_DE_FIGURA`, o PDF para o LaTeX e o PNG para slides e para quem só quer
    olhar. O PNG usa os mesmos 300 dpi dos gráficos do relatório (:data:`plots.DPI`).
    """
    linhas = math.ceil(len(nomes) / colunas)
    largura = LARGURA_CM / 2.54
    with plt.rc_context(ESTILO):
        figura, eixos = plt.subplots(
            linhas, colunas, figsize=(largura, 0.32 * largura * linhas), squeeze=False
        )
        for eixo, nome in zip(eixos.flat, nomes, strict=False):
            serie = series[nome]
            eixo.plot(serie.tempo, serie.original, color=COR_ORIGINAL, label=ROTULOS["original"])
            eixo.plot(
                serie.tempo,
                serie.simplificado,
                color=COR_SIMPLIFICADO,
                linestyle="--",
                label=ROTULOS["simplificado"],
            )
            eixo.set_title(nome)
            eixo.set_xlabel(f"tempo ({UNIDADE})")
            eixo.yaxis.set_major_formatter(_FormatoComVirgula())
            eixo.xaxis.set_major_formatter(_FormatoComVirgula())
        sobras = list(eixos.flat)[len(nomes) :]
        for eixo in sobras:
            eixo.axis("off")
        alcas, rotulos = eixos.flat[0].get_legend_handles_labels()
        if sobras:
            sobras[0].legend(alcas, rotulos, loc="center", frameon=False)
        else:
            figura.legend(
                alcas, rotulos, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2,
                frameon=False,
            )
        figura.tight_layout()
        caminho.parent.mkdir(parents=True, exist_ok=True)
        gravados = tuple(caminho.with_suffix(f".{formato}") for formato in FORMATOS_DE_FIGURA)
        for gravado in gravados:
            figura.savefig(gravado, dpi=plots.DPI)
        plt.close(figura)
    return gravados


# --- Execução ------------------------------------------------------------------------


def _porcentagem(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + "\\%"


def _resumo_do_veredito(parte: Veredito) -> str:
    passados = sum(item.passou for item in parte.criterios)
    return (
        f"Veredito: {parte.nivel}, {passados} de {len(parte.criterios)} critérios "
        f"({_porcentagem(parte.porcentagem)})."
    )


def _escrever(caminho: Path, conteudo: str) -> tuple[Path, Path]:
    """Grava a tabela em ``.tex`` e, desenhada a partir dele, em ``.png`` com o mesmo nome."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho, tabela_png(conteudo, caminho.with_suffix(".png"))


def main() -> None:
    """Refaz o estudo de caso e grava as figuras e as tabelas do texto."""
    resultado = reducheck.verificar(ESTUDO / "simp1.yaml")
    # Uma execução, duas perguntas: cada tabela do texto fala de uma delas, com a sua contagem.
    trajetorias = resultado
    caminho = resultado.veredito.parte(TRAJETORIA)
    destino = resultado.veredito.parte(LONGO_PRAZO)
    print(f"simp1.yaml: {resultado.nivel}, {resultado.porcentagem:.1f}%")
    print(f"  trajetória: {caminho.nivel}, {caminho.porcentagem:.1f}%")
    print(f"  longo prazo: {destino.nivel}, {destino.porcentagem:.1f}%")

    configuracao = trajetorias.configuracao
    core = configuracao.nomes_core()
    comparadas = [
        variavel.nome
        for variavel in configuracao.variaveis
        if variavel.simplificado is not None and variavel.nome not in core
    ]
    gerados = [
        *figura_trajetorias(trajetorias.series, core, FIGURAS / "simp1_core"),
        *figura_trajetorias(
            trajetorias.series, comparadas, FIGURAS / "simp1_nao_core", colunas=2
        ),
        *_escrever(
            TABELAS / "simp1_criterios.tex",
            tabela_criterios(
                caminho.criterios,
                "Critérios de trajetória da simplificação 1 nas variáveis core. "
                + _resumo_do_veredito(caminho),
                "tab:simp1-criterios",
            ),
        ),
        *_escrever(
            TABELAS / "simp1_criterios_qualitativos.tex",
            tabela_criterios(
                destino.criterios,
                "Critérios qualitativos da simplificação 1. "
                + _resumo_do_veredito(destino),
                "tab:simp1-qualitativos",
            ),
        ),
        *_escrever(
            TABELAS / "simp1_equilibrios.tex",
            tabela_equilibrios(
                destino.criterios,
                "Equilíbrio das variáveis core no original e na simplificação 1.",
                "tab:simp1-equilibrios",
            ),
        ),
    ]
    assert resultado.comparacao is not None
    gerados.extend(
        _escrever(
            TABELAS / "simp1_autovalores.tex",
            tabela_autovalores(
                resultado.comparacao,
                "Estabilidade local no equilíbrio: os três autovalores de maior parte real "
                "da Jacobiana de cada modelo.",
                "tab:simp1-autovalores",
            ),
        )
    )

    condicoes = configuracao.simulacao
    tempos = {
        ROTULOS["original"]: medir_tempo(
            configuracao.modelos.original, condicoes, _variaveis_do_modelo(trajetorias, "original")
        ),
        ROTULOS["simplificado"]: medir_tempo(
            configuracao.modelos.simplificado,
            condicoes,
            _variaveis_do_modelo(trajetorias, "simplificado"),
        ),
    }
    gerados.extend(
        _escrever(
            TABELAS / "tempo_execucao.tex",
            tabela_tempo(
                tempos,
                f"Tempo de simulação (média $\\pm$ desvio padrão de {EXECUCOES} execuções, "
                f"{condicoes.t_fim:g} {UNIDADE}, {condicoes.pontos} pontos, "
                f"{condicoes.solver.upper()}). A carga inclui ler o SBML e compilar o "
                "modelo; uma execução de aquecimento foi descartada.",
                "tab:tempo",
            ),
        )
    )
    for nome, medidos in tempos.items():
        print(
            f"{nome}: carga {statistics.mean(medidos.carga) * 1000:.1f} ms, "
            f"integração {statistics.mean(medidos.integracao) * 1000:.2f} ± "
            f"{statistics.stdev(medidos.integracao) * 1000:.2f} ms"
        )
    for caminho in gerados:
        print(f"gravado: {caminho.relative_to(RAIZ)}")


def _variaveis_do_modelo(resultado: reducheck.Resultado, papel: str) -> list[str]:
    """Todas as variáveis de estado que o modelo de ``papel`` declara no mapeamento."""
    return mapping.nomes_simulados(resultado.configuracao.variaveis, papel)


if __name__ == "__main__":
    main()
