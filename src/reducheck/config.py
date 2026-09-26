"""Read and validate the YAML configuration file.

The schema follows the "Input" section of ``docs/produto.md``, but only the fields this
version of the pipeline actually uses are read: paths, time grid, 1:1 variable mapping and
``nrmse`` criteria. Unknown keys are ignored so that the template of the product document
can be copied as is; constructs that are not supported *yet* and whose silent omission
would change the result -- sum mappings, other metrics, ``variaveis: core`` -- are
rejected with an explicit message instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

__all__ = [
    "Configuracao",
    "Criterio",
    "ErroDeConfiguracao",
    "Modelos",
    "Relatorio",
    "Simulacao",
    "Variavel",
    "carregar",
]

#: Metrics this version knows how to compute. Kept in sync with :mod:`reducheck.metrics`.
METRICAS_SUPORTADAS = frozenset({"nrmse"})

#: Solvers this version knows how to configure.
SOLVERS_SUPORTADOS = frozenset({"cvode"})


class ErroDeConfiguracao(Exception):
    """A configuração não pôde ser lida, ou pede algo que ainda não é suportado."""


class Modelos(BaseModel):
    """Paths of the two SBML files being compared."""

    original: Path
    simplificado: Path


class Simulacao(BaseModel):
    """Conditions shared by both simulations."""

    t_inicio: float = 0.0
    t_fim: float
    pontos: int = Field(ge=2)
    solver: str = "cvode"
    tol_relativa: float = Field(default=1e-8, gt=0.0)
    tol_absoluta: float = Field(default=1e-10, gt=0.0)

    @model_validator(mode="after")
    def _horizonte_crescente(self) -> Simulacao:
        if self.t_fim <= self.t_inicio:
            raise ValueError(
                f"simulacao: t_fim ({self.t_fim}) tem que ser maior que t_inicio ({self.t_inicio})."
            )
        return self


class Variavel(BaseModel):
    """One 1:1 correspondence between a variable of each model."""

    #: Name used in the report; may differ from the name in either model.
    nome: str
    original: str
    simplificado: str

    @field_validator("original", "simplificado", mode="before")
    @classmethod
    def _apenas_um_para_um(cls, valor: Any) -> Any:
        if isinstance(valor, (list, tuple, dict)):
            raise ValueError(
                "variaveis: só o mapeamento 1:1 é suportado nesta versão; "
                f"'{valor}' pede soma ou soma ponderada."
            )
        return valor


class Criterio(BaseModel):
    """One metric applied to a list of variables under a single threshold."""

    metrica: str
    limite: float = Field(gt=0.0)
    #: Report names of the variables this criterion applies to.
    variaveis: list[str] = Field(min_length=1)

    @field_validator("metrica")
    @classmethod
    def _metrica_suportada(cls, valor: str) -> str:
        if valor not in METRICAS_SUPORTADAS:
            suportadas = ", ".join(sorted(METRICAS_SUPORTADAS))
            raise ValueError(
                f"criterios: a métrica '{valor}' ainda não existe. Disponíveis: {suportadas}."
            )
        return valor

    @field_validator("variaveis", mode="before")
    @classmethod
    def _apenas_lista_explicita(cls, valor: Any) -> Any:
        if isinstance(valor, str):
            raise ValueError(
                "criterios: 'variaveis' tem que ser uma lista de nomes; "
                f"'{valor}' (seleção em bloco) ainda não é suportado."
            )
        return valor


class Relatorio(BaseModel):
    """Where the results are written."""

    pasta: Path = Path("resultados")


class Configuracao(BaseModel):
    """The whole configuration file, with every path already resolved."""

    versao: int
    modelos: Modelos
    simulacao: Simulacao
    variaveis: list[Variavel] = Field(min_length=1)
    criterios: list[Criterio] = Field(min_length=1)
    relatorio: Relatorio = Relatorio()

    @model_validator(mode="after")
    def _criterios_citam_variaveis_declaradas(self) -> Configuracao:
        declaradas = {variavel.nome for variavel in self.variaveis}
        for criterio in self.criterios:
            desconhecidas = [nome for nome in criterio.variaveis if nome not in declaradas]
            if desconhecidas:
                disponiveis = ", ".join(sorted(declaradas))
                raise ValueError(
                    f"criterios: o critério '{criterio.metrica}' cita "
                    f"{', '.join(desconhecidas)}, que não está em 'variaveis'. "
                    f"Declaradas: {disponiveis}."
                )
        return self

    @model_validator(mode="after")
    def _nomes_de_variaveis_sao_unicos(self) -> Configuracao:
        nomes = [variavel.nome for variavel in self.variaveis]
        repetidos = sorted({nome for nome in nomes if nomes.count(nome) > 1})
        if repetidos:
            raise ValueError(
                f"variaveis: o nome {', '.join(repetidos)} aparece mais de uma vez."
            )
        return self


def carregar(caminho: Path | str) -> Configuracao:
    """Read the YAML at ``caminho`` and return it validated, with paths resolved.

    Relative paths inside the file are resolved against the directory of the file itself,
    so a configuration can be moved around together with its models.
    """
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

    try:
        configuracao = Configuracao.model_validate(dados)
    except ValidationError as erro:
        raise ErroDeConfiguracao(f"Configuração inválida em '{caminho}':\n{erro}") from erro

    base = caminho.parent
    configuracao = _resolver_caminhos(configuracao, base)
    _exigir_solver_suportado(configuracao.simulacao)
    _exigir_modelos_existentes(configuracao.modelos)
    return configuracao


def _resolver_caminhos(configuracao: Configuracao, base: Path) -> Configuracao:
    """Return a copy of ``configuracao`` with every path resolved against ``base``."""
    modelos = Modelos(
        original=_resolver(configuracao.modelos.original, base),
        simplificado=_resolver(configuracao.modelos.simplificado, base),
    )
    relatorio = Relatorio(pasta=_resolver(configuracao.relatorio.pasta, base))
    return configuracao.model_copy(update={"modelos": modelos, "relatorio": relatorio})


def _resolver(caminho: Path, base: Path) -> Path:
    return caminho if caminho.is_absolute() else (base / caminho).resolve()


def _exigir_solver_suportado(simulacao: Simulacao) -> None:
    if simulacao.solver not in SOLVERS_SUPORTADOS:
        suportados = ", ".join(sorted(SOLVERS_SUPORTADOS))
        raise ErroDeConfiguracao(
            f"simulacao: o solver '{simulacao.solver}' não é suportado. Disponíveis: {suportados}."
        )


def _exigir_modelos_existentes(modelos: Modelos) -> None:
    for papel, caminho in (("original", modelos.original), ("simplificado", modelos.simplificado)):
        if not caminho.is_file():
            raise ErroDeConfiguracao(
                f"modelos: o arquivo do modelo {papel} não existe: '{caminho}'."
            )
