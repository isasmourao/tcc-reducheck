"""Read and validate the YAML configuration file.

The schema is the whole "Input" section of ``docs/produto.md``, including fields that only
later versions of the pipeline will act on (sum mapping, ``core``, ``obrigatorio``,
qualitative criteria, report formats, parameter overrides). Parsing everything now is what
keeps the file format stable for the people who write it.

Validation happens in four separate passes, in this order, and each one produces messages
that name the offending field:

1. :func:`validar_esquema` -- types, ranges and unknown keys (pydantic);
2. :func:`_conferir_coerencia` -- what only makes sense when the whole file is read
   (repeated names, criteria citing undeclared variables, metric names in the registry);
3. :func:`_conferir_contra_modelos` -- the two SBML files: they exist, they load, and every
   name cited in the mapping is a name the corresponding model has;
4. :func:`_exigir_suportado` -- what this version cannot honour yet.

The last pass is deliberately apart from the schema: a request that is *valid* but not yet
implemented has to stop with an explicit message, never be silently ignored, or the verdict
would be wrong without anyone noticing.
"""

from __future__ import annotations

import difflib
import math
import re
from pathlib import Path
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from reducheck import metrics

__all__ = [
    "ANALISES_QUALITATIVAS",
    "FORMATOS_SUPORTADOS",
    "SOLVERS_SUPORTADOS",
    "Configuracao",
    "Criterio",
    "ErroDeConfiguracao",
    "Modelos",
    "Relatorio",
    "Simulacao",
    "Variavel",
    "carregar",
    "ler_yaml",
    "normalizar_alvo",
    "validar_esquema",
]

#: Names of the qualitative analyses of ``docs/produto.md``. They are criteria without a
#: threshold, and none of them is implemented yet (capabilities L1-L3).
ANALISES_QUALITATIVAS = frozenset({"equilibrio", "estabilidade_local"})

#: Solvers this version knows how to configure.
SOLVERS_SUPORTADOS = frozenset({"cvode"})

#: Report formats this version knows how to write.
FORMATOS_SUPORTADOS = frozenset({"json"})

#: How one side of a mapping may be written: one name, a sum, or a weighted sum.
Alvo = Union[str, list[str], dict[str, float]]  # noqa: UP007 (pydantic reads the annotation)

#: An SBML identifier: a letter or underscore, then letters, digits or underscores. Anything
#: else in that position is an expression, which this library deliberately does not read.
_IDENTIFICADOR = re.compile(r"[A-Za-z_]\w*\Z")


class ErroDeConfiguracao(Exception):
    """A configuração não pôde ser lida, está inválida, ou pede algo ainda não suportado."""


class _Base(BaseModel):
    """Common settings: an unknown key is an error, not something to ignore."""

    model_config = ConfigDict(extra="forbid")


class Modelos(_Base):
    """Paths of the two SBML files being compared."""

    original: Path
    simplificado: Path


class Simulacao(_Base):
    """Conditions shared by both simulations."""

    t_inicio: float = 0.0
    t_fim: float
    pontos: int = Field(ge=2)
    solver: str = "cvode"
    tol_relativa: float = Field(default=1e-8, gt=0.0)
    tol_absoluta: float = Field(default=1e-10, gt=0.0)
    #: Overrides of the values in the SBML, applied to both models (capability S2).
    parametros: dict[str, float] = Field(default_factory=dict)
    condicoes_iniciais: dict[str, float] = Field(default_factory=dict)


class Variavel(_Base):
    """One correspondence between the two models, under the name used in the report."""

    nome: str
    original: Alvo
    #: ``None`` means the reduction dropped this variable: there is nothing to compare.
    simplificado: Alvo | None = None
    #: Whether the variable is essential to the purpose of the model. A criterion written
    #: with ``variaveis: core`` is applied to exactly these (capability M4).
    core: bool = True


class Criterio(_Base):
    """One metric applied to a list of variables under a single threshold."""

    metrica: str
    #: Largest accepted error. Absent for a qualitative criterion.
    limite: float | None = Field(default=None, gt=0.0)
    #: Report names of the variables, or ``core`` to select every core variable at once.
    variaveis: list[str] | Literal["core"] | None = None
    obrigatorio: bool = True
    #: Options of the metric itself, such as the ``epsilon`` of ``mape``. The accepted names
    #: are the keyword arguments of the registered function (``metrics.parametros_de``).
    parametros: dict[str, float] = Field(default_factory=dict)


class Relatorio(_Base):
    """What is written, and where."""

    formatos: list[str] = Field(default_factory=lambda: ["json"])
    pasta: Path = Path("resultados")


class Configuracao(_Base):
    """The whole configuration file, with every path already resolved."""

    versao: Literal[1]
    modelos: Modelos
    simulacao: Simulacao
    variaveis: list[Variavel] = Field(min_length=1)
    criterios: list[Criterio] = Field(min_length=1)
    relatorio: Relatorio = Field(default_factory=Relatorio)

    def nomes_core(self) -> list[str]:
        """Return the report names of the core variables, in declaration order."""
        return [variavel.nome for variavel in self.variaveis if variavel.core]

    def variaveis_de(self, criterio: Criterio) -> list[str]:
        """Return the report names a criterion applies to, expanding ``variaveis: core``."""
        if criterio.variaveis == "core":
            return self.nomes_core()
        return list(criterio.variaveis or [])


# --- mapping targets ---------------------------------------------------------


def normalizar_alvo(alvo: Alvo) -> dict[str, float]:
    """Return one side of a mapping as ``name -> weight``, whichever way it was written.

    A plain name becomes ``{name: 1.0}`` and a list becomes every name with weight 1.0, so
    everything downstream -- validation, simulation and :mod:`reducheck.mapping` -- only ever
    deals with a weighted sum. The 1:1 case is just the one-term sum.
    """
    if isinstance(alvo, str):
        return {alvo: 1.0}
    if isinstance(alvo, dict):
        return {nome: float(peso) for nome, peso in alvo.items()}
    return dict.fromkeys(alvo, 1.0)


# --- loading -----------------------------------------------------------------


def carregar(caminho: Path | str) -> Configuracao:
    """Read the YAML at ``caminho``, validate it and return it with paths resolved.

    Relative paths inside the file are resolved against the directory of the file itself,
    so a configuration can be moved around together with its models.
    """
    caminho = Path(caminho)
    dados = ler_yaml(caminho)
    configuracao = validar_esquema(dados, caminho)
    configuracao = _resolver_caminhos(configuracao, caminho.parent)
    _conferir_coerencia(configuracao, caminho)
    _conferir_contra_modelos(configuracao, caminho)
    _exigir_suportado(configuracao, caminho)
    return configuracao


def ler_yaml(caminho: Path | str) -> dict[str, Any]:
    """Return the top-level mapping of the YAML at ``caminho``."""
    caminho = Path(caminho)
    try:
        texto = caminho.read_text(encoding="utf-8")
    except OSError as erro:
        raise ErroDeConfiguracao(
            f"Não foi possível ler a configuração '{caminho}': {erro}"
        ) from erro

    try:
        dados = yaml.safe_load(texto)
    except yaml.YAMLError as erro:
        raise ErroDeConfiguracao(
            f"A configuração '{caminho}' não é um YAML válido: {erro}"
        ) from erro

    if not isinstance(dados, dict):
        raise ErroDeConfiguracao(
            f"A configuração '{caminho}' deveria conter um mapeamento de chaves no topo."
        )
    return dados


def validar_esquema(dados: dict[str, Any], caminho: Path | str) -> Configuracao:
    """Validate ``dados`` against the schema, with one message per offending field."""
    try:
        return Configuracao.model_validate(dados)
    except ValidationError as erro:
        raise ErroDeConfiguracao(_formatar(erro, caminho)) from erro


# --- messages ----------------------------------------------------------------


def _reclamar(problemas: list[str], caminho: Path | str) -> None:
    """Raise with every collected problem, or return quietly when there is none."""
    if problemas:
        raise ErroDeConfiguracao(
            f"Configuração inválida em '{caminho}':\n"
            + "\n".join(f"  - {problema}" for problema in problemas)
        )


def _sugerir(nome: str, candidatos: set[str] | frozenset[str]) -> str:
    """Return a hint pointing at the closest of ``candidatos``, or listing them all.

    The case-insensitive match comes first on purpose: ``difflib`` scores ``c`` against
    ``C`` as nothing alike, and confusing the case of a variable is a common mistake.
    """
    if not candidatos:
        return ""
    por_minuscula = {candidato.lower(): candidato for candidato in sorted(candidatos)}
    if nome.lower() in por_minuscula:
        return f" Você quis dizer '{por_minuscula[nome.lower()]}'?"
    proximos = difflib.get_close_matches(nome, sorted(candidatos), n=1, cutoff=0.6)
    if proximos:
        return f" Você quis dizer '{proximos[0]}'?"
    return f" Disponíveis: {', '.join(sorted(candidatos))}."


#: Pydantic error types translated into Portuguese. Anything missing here falls back to the
#: message pydantic itself produced, which is in English but still names the field.
_TRADUCOES = {
    "missing": "campo obrigatório ausente.",
    "extra_forbidden": "chave desconhecida.",
    "string_type": "tem que ser um texto.",
    "bool_type": "tem que ser verdadeiro ou falso.",
    "bool_parsing": "tem que ser verdadeiro ou falso.",
    "int_type": "tem que ser um número inteiro.",
    "int_parsing": "tem que ser um número inteiro.",
    "int_from_float": "tem que ser um número inteiro.",
    "float_type": "tem que ser um número.",
    "float_parsing": "tem que ser um número.",
    "list_type": "tem que ser uma lista.",
    "dict_type": "tem que ser um mapeamento de chaves.",
    "model_type": "tem que ser um mapeamento de chaves.",
}


def _formatar(erro: ValidationError, caminho: Path | str) -> str:
    """Turn a pydantic error into one line per field, in Portuguese."""
    linhas: list[str] = []
    for detalhe in erro.errors():
        campo, modelo = _resolver_caminho(tuple(detalhe["loc"]))
        linha = f"{campo}: {_explicar(detalhe, modelo)}"
        if linha not in linhas:
            linhas.append(linha)
    _reclamar(linhas, caminho)
    raise AssertionError("uma ValidationError sempre tem ao menos um erro")  # pragma: no cover


def _explicar(detalhe: dict[str, Any], modelo: type[BaseModel] | None) -> str:
    tipo = str(detalhe["type"])
    contexto = detalhe.get("ctx") or {}
    if tipo == "extra_forbidden":
        campos = set(modelo.model_fields) if modelo is not None else set()
        chave = str(detalhe["loc"][-1])
        return _TRADUCOES[tipo] + _sugerir(chave, campos)
    if tipo == "greater_than":
        limite = contexto.get("gt")
        alvo = "zero" if limite == 0 else str(limite)
        return f"tem que ser maior que {alvo}."
    if tipo == "greater_than_equal":
        return f"tem que ser maior ou igual a {contexto.get('ge')}."
    if tipo == "too_short":
        return f"precisa de pelo menos {contexto.get('min_length')} item(ns)."
    if tipo in {"literal_error", "union_tag_invalid"}:
        return f"valor não reconhecido: {detalhe.get('msg')}."
    return _TRADUCOES.get(tipo, str(detalhe["msg"]) + ".")


def _resolver_caminho(loc: tuple[Any, ...]) -> tuple[str, type[BaseModel] | None]:
    """Format ``loc`` as ``criterios[0].limite`` and return the model that owns the leaf.

    Walking the schema, instead of just joining ``loc``, is what discards the tags pydantic
    appends when a union member fails (``variaveis[0].original.list[str]``): the walk stops
    at the last component that is really a field.
    """
    partes: list[str] = []
    atual: type[BaseModel] | None = Configuracao
    dono: type[BaseModel] | None = None
    for posicao, componente in enumerate(loc):
        if isinstance(componente, int):
            partes.append(f"[{componente}]")
            continue
        if atual is None:
            break
        if componente in atual.model_fields:
            partes.append(componente if not partes else f".{componente}")
            dono, atual = atual, _modelo_de(atual.model_fields[componente].annotation)
            continue
        # Not a field of the model being walked. When it is the last component it is the
        # unknown key the user wrote, so it belongs in the path and its model is the one
        # whose field names the suggestion should come from.
        if posicao == len(loc) - 1:
            partes.append(componente if not partes else f".{componente}")
            dono = atual
        break
    if not partes:
        return "(topo)", Configuracao
    return "".join(partes).lstrip("."), dono


def _modelo_de(anotacao: Any) -> type[BaseModel] | None:
    """Return the model reachable from ``anotacao``, looking inside lists and unions."""
    if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
        return anotacao
    if get_origin(anotacao) in {list, dict, Union, UnionType}:
        for argumento in get_args(anotacao):
            encontrado = _modelo_de(argumento)
            if encontrado is not None:
                return encontrado
    return None


# --- paths -------------------------------------------------------------------


def _resolver_caminhos(configuracao: Configuracao, base: Path) -> Configuracao:
    """Return a copy of ``configuracao`` with every path resolved against ``base``."""
    modelos = Modelos(
        original=_resolver(configuracao.modelos.original, base),
        simplificado=_resolver(configuracao.modelos.simplificado, base),
    )
    relatorio = configuracao.relatorio.model_copy(
        update={"pasta": _resolver(configuracao.relatorio.pasta, base)}
    )
    return configuracao.model_copy(update={"modelos": modelos, "relatorio": relatorio})


def _resolver(caminho: Path, base: Path) -> Path:
    return caminho if caminho.is_absolute() else (base / caminho).resolve()


# --- pass 2: the file as a whole ---------------------------------------------


def _e_qualitativo(criterio: Criterio) -> bool:
    return criterio.metrica in ANALISES_QUALITATIVAS


def _conferir_alvo(campo: str, alvo: Alvo | None) -> list[str]:
    """Check one side of a mapping: well-formed names, no repetitions, usable weights.

    An expression is caught here, and not by the check against the SBML file, so that the
    message says what the library does not support instead of claiming the model is missing
    a variable called ``C1 + C2``.
    """
    if alvo is None:
        return []
    problemas: list[str] = []
    if not isinstance(alvo, str) and not alvo:
        return [f"{campo}: a lista de variáveis está vazia; declare ao menos uma."]

    if isinstance(alvo, list):
        repetidos = [nome for nome in dict.fromkeys(alvo) if alvo.count(nome) > 1]
        if repetidos:
            problemas.append(
                f"{campo}: a variável {', '.join(repetidos)} aparece mais de uma vez na soma. "
                "Para somar com peso, use um mapeamento: {%s: 2.0}." % repetidos[0]
            )

    pesos = normalizar_alvo(alvo)
    for nome, peso in pesos.items():
        if not _IDENTIFICADOR.match(nome):
            problemas.append(
                f"{campo}: '{nome}' não é um nome de variável. Expressões (contas, razões, "
                "funções) não são suportadas; use uma lista [A, B] para a soma ou um "
                "mapeamento {A: 1.0, B: 0.5} para a soma ponderada."
            )
        if not math.isfinite(peso):
            problemas.append(f"{campo}: o peso de '{nome}' tem que ser um número finito.")
    return problemas


def _conferir_coerencia(configuracao: Configuracao, caminho: Path | str) -> None:
    """Check what only makes sense once the whole file is read."""
    problemas: list[str] = []
    if configuracao.simulacao.t_fim <= configuracao.simulacao.t_inicio:
        problemas.append(
            f"simulacao.t_fim: tem que ser maior que t_inicio "
            f"({configuracao.simulacao.t_inicio}); recebido {configuracao.simulacao.t_fim}."
        )

    vistos: dict[str, int] = {}
    for indice, variavel in enumerate(configuracao.variaveis):
        if variavel.nome in vistos:
            problemas.append(
                f"variaveis[{indice}].nome: o nome '{variavel.nome}' já foi usado em "
                f"variaveis[{vistos[variavel.nome]}].nome."
            )
        else:
            vistos[variavel.nome] = indice
        for papel in ("original", "simplificado"):
            problemas.extend(
                _conferir_alvo(f"variaveis[{indice}].{papel}", getattr(variavel, papel))
            )
        if variavel.core and variavel.simplificado is None:
            problemas.append(
                f"variaveis[{indice}].simplificado: a variável core '{variavel.nome}' não "
                "tem mapeamento no modelo simplificado. Declare a contrapartida, ou marque "
                "'core: false' se ela foi eliminada pela simplificação."
            )

    declaradas = set(vistos)
    sem_contrapartida = {
        variavel.nome for variavel in configuracao.variaveis if variavel.simplificado is None
    }
    conhecidas = metrics.disponiveis() | ANALISES_QUALITATIVAS
    for indice, criterio in enumerate(configuracao.criterios):
        if criterio.metrica not in conhecidas:
            problemas.append(
                f"criterios[{indice}].metrica: a métrica '{criterio.metrica}' não está no "
                f"registro.{_sugerir(criterio.metrica, conhecidas)}"
            )
        elif _e_qualitativo(criterio):
            if criterio.parametros:
                problemas.append(
                    f"criterios[{indice}].parametros: a análise qualitativa "
                    f"'{criterio.metrica}' não recebe parâmetros."
                )
            if criterio.limite is not None:
                problemas.append(
                    f"criterios[{indice}].limite: a análise qualitativa "
                    f"'{criterio.metrica}' não usa limite."
                )
        else:
            if criterio.limite is None:
                problemas.append(
                    f"criterios[{indice}].limite: campo obrigatório para a métrica "
                    f"'{criterio.metrica}'."
                )
            if criterio.variaveis is None:
                problemas.append(
                    f"criterios[{indice}].variaveis: campo obrigatório para a métrica "
                    f"'{criterio.metrica}'; use uma lista de nomes ou 'core'."
                )
            aceitos = metrics.parametros_de(criterio.metrica)
            for parametro in criterio.parametros:
                if parametro not in aceitos:
                    problemas.append(
                        f"criterios[{indice}].parametros: a métrica '{criterio.metrica}' "
                        f"não tem o parâmetro '{parametro}'."
                        + (
                            _sugerir(parametro, aceitos)
                            if aceitos
                            else " Ela não recebe parâmetros."
                        )
                    )
        if criterio.variaveis == "core" and not configuracao.nomes_core():
            problemas.append(
                f"criterios[{indice}].variaveis: 'core' não seleciona nada, porque nenhuma "
                "variável foi declarada com 'core: true'."
            )
        if not isinstance(criterio.variaveis, list):
            continue
        for nome in criterio.variaveis:
            if nome not in declaradas:
                problemas.append(
                    f"criterios[{indice}].variaveis: '{nome}' não está declarado em "
                    f"'variaveis'.{_sugerir(nome, declaradas)}"
                )
            elif nome in sem_contrapartida:
                problemas.append(
                    f"criterios[{indice}].variaveis: '{nome}' não tem contrapartida no "
                    "modelo simplificado, então não há o que comparar."
                )
    _reclamar(problemas, caminho)


# --- pass 3: against the two SBML files --------------------------------------


def _nomes_citados(alvo: Alvo | None) -> list[str]:
    """Return the model variables one side of a mapping reads."""
    return [] if alvo is None else list(normalizar_alvo(alvo))


def _conferir_contra_modelos(configuracao: Configuracao, caminho: Path | str) -> None:
    """Check that both SBML files load and that every name cited exists in them."""
    from reducheck import simulation  # deferred: simulation imports this module

    problemas: list[str] = []
    disponiveis: dict[str, frozenset[str]] = {}
    for papel in ("original", "simplificado"):
        arquivo: Path = getattr(configuracao.modelos, papel)
        if not arquivo.is_file():
            problemas.append(
                f"modelos.{papel}: o arquivo do modelo {papel} não existe: '{arquivo}'."
            )
            continue
        try:
            disponiveis[papel] = simulation.nomes_disponiveis(arquivo)
        except simulation.ErroDeSimulacao as erro:
            # The libsbml diagnostic comes in several lines; keep one problem per line.
            problemas.append(f"modelos.{papel}: {' '.join(str(erro).split())}")
    _reclamar(problemas, caminho)

    for indice, variavel in enumerate(configuracao.variaveis):
        for papel in ("original", "simplificado"):
            for nome in _nomes_citados(getattr(variavel, papel)):
                if nome not in disponiveis[papel]:
                    problemas.append(
                        f"variaveis[{indice}].{papel}: o modelo {papel} não tem a variável "
                        f"'{nome}'.{_sugerir(nome, disponiveis[papel])}"
                    )
    for campo in ("parametros", "condicoes_iniciais"):
        for nome in getattr(configuracao.simulacao, campo):
            ausentes = [
                papel
                for papel in ("original", "simplificado")
                if nome not in disponiveis[papel]
            ]
            if ausentes:
                problemas.append(
                    f"simulacao.{campo}: '{nome}' não existe no modelo "
                    f"{' nem no '.join(ausentes)}.{_sugerir(nome, disponiveis['original'])}"
                )
    _reclamar(problemas, caminho)


# --- pass 4: what this version cannot honour yet -----------------------------

#: Field -> (capability of docs/produto.md, issue that will implement it).
_PENDENTES = {
    "obrigatorio": ("critérios obrigatórios e desejáveis (V2)", "#13"),
    "qualitativo": ("equilíbrio e estabilidade local (L1-L3)", "#18"),
    "sobrescrita": ("sobrescrever parâmetros e condições iniciais (S2)", "#12"),
    "html": ("relatório em HTML (R2)", "#14"),
}


def _ainda_nao(campo: str, pedido: str, chave: str) -> str:
    capacidade, issue = _PENDENTES[chave]
    return (
        f"{campo}: ainda não há suporte para {pedido} nesta versão: {capacidade}, issue {issue}."
    )


def _exigir_suportado(configuracao: Configuracao, caminho: Path | str) -> None:
    """Refuse a valid configuration whose capabilities are not implemented yet.

    Ignoring these in silence would give a verdict computed from something other than what
    was asked, which is worse than refusing to run.
    """
    problemas: list[str] = []
    if configuracao.simulacao.solver not in SOLVERS_SUPORTADOS:
        suportados = ", ".join(sorted(SOLVERS_SUPORTADOS))
        problemas.append(
            f"simulacao.solver: o solver '{configuracao.simulacao.solver}' ainda não é "
            f"suportado. Disponíveis: {suportados}."
        )
    for campo in ("parametros", "condicoes_iniciais"):
        if getattr(configuracao.simulacao, campo):
            problemas.append(
                _ainda_nao(f"simulacao.{campo}", "a sobrescrita de valores", "sobrescrita")
            )

    for indice, criterio in enumerate(configuracao.criterios):
        if _e_qualitativo(criterio):
            problemas.append(
                _ainda_nao(
                    f"criterios[{indice}].metrica",
                    f"a análise '{criterio.metrica}'",
                    "qualitativo",
                )
            )
        if not criterio.obrigatorio:
            problemas.append(
                _ainda_nao(
                    f"criterios[{indice}].obrigatorio",
                    "'obrigatorio: false'",
                    "obrigatorio",
                )
            )

    nao_suportados = [
        formato for formato in configuracao.relatorio.formatos if formato not in FORMATOS_SUPORTADOS
    ]
    if nao_suportados:
        problemas.append(
            _ainda_nao(
                "relatorio.formatos", f"o formato '{', '.join(nao_suportados)}'", "html"
            )
        )
    _reclamar(problemas, caminho)
