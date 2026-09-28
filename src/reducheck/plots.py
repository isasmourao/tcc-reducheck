"""Draw one panel per mapped variable: the two trajectories and the error over time.

Each panel answers the two questions a reader has in front of a reduction: does the
simplified model follow the original, and *where* in time it stops following. The error is
plotted below, sharing the time axis, so both are read in one glance.

The same PNG goes to ``graficos/`` at 300 dpi, for the text of the dissertation, and into
the HTML report as base64, so the report stays a single file.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import matplotlib

# The library writes files; it never opens a window. Chosen here so that generating a
# report works the same in a terminal, in the CI and inside a notebook.
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402 (has to come after the backend is chosen)
import numpy as np  # noqa: E402

from reducheck.mapping import SerieComparada  # noqa: E402

__all__ = ["DPI", "PASTA_DOS_GRAFICOS", "Grafico", "desenhar", "rotulo_da_combinacao"]

#: Resolution of the saved PNG files. 300 dpi is what a printed figure needs.
DPI = 300

#: Subfolder of the results folder where the PNG files go, as in ``docs/produto.md``.
PASTA_DOS_GRAFICOS = "graficos"

#: Width and height of one panel, in inches, before the dpi is applied.
_TAMANHO = (7.0, 5.0)


@dataclass(frozen=True)
class Grafico:
    """One saved panel: where it is on disk and its bytes, for embedding."""

    variavel: str
    caminho: Path
    png: bytes
    #: What each side of the comparison is made of, when it is not a plain 1:1 mapping.
    legenda_original: str = ""
    legenda_simplificado: str = ""

    @property
    def base64(self) -> str:
        """The PNG as a base64 string, to embed in the HTML with a ``data:`` URI."""
        return base64.b64encode(self.png).decode("ascii")


def rotulo_da_combinacao(pesos: Mapping[str, float]) -> str:
    """Return how a combination reads in the report, such as ``Mo + M1 + 0,5·C2``.

    A weight of 1 is left out: writing ``1·Mo`` would suggest the weight was chosen.
    """
    partes = [
        nome if peso == 1.0 else f"{peso:g}·{nome}".replace(".", ",")
        for nome, peso in pesos.items()
    ]
    return " + ".join(partes)


def desenhar(
    series: Mapping[str, SerieComparada],
    pasta: Path | str,
    unidade_de_tempo: str | None = None,
) -> list[Grafico]:
    """Draw and save one panel per series, into ``pasta/graficos``.

    ``pasta`` is the results folder; ``unidade_de_tempo`` is what the model declares, and
    is left out of the axis label when the model does not declare it.
    """
    destino = Path(pasta) / PASTA_DOS_GRAFICOS
    destino.mkdir(parents=True, exist_ok=True)
    return [_desenhar_um(serie, destino, unidade_de_tempo) for serie in series.values()]


def _desenhar_um(serie: SerieComparada, destino: Path, unidade: str | None) -> Grafico:
    legenda_original = rotulo_da_combinacao(serie.pesos_original)
    legenda_simplificado = rotulo_da_combinacao(serie.pesos_simplificado)
    erro = np.abs(serie.original - serie.simplificado)

    figura, (cima, baixo) = plt.subplots(
        2,
        1,
        figsize=_TAMANHO,
        sharex=True,
        gridspec_kw={"height_ratios": [2, 1]},
        constrained_layout=True,
    )
    cima.plot(serie.tempo, serie.original, linestyle="-", color="#1f77b4", label="original")
    cima.plot(
        serie.tempo,
        serie.simplificado,
        linestyle="--",
        color="#d62728",
        label="simplificado",
    )
    cima.set_ylabel(serie.nome)
    cima.set_title(_titulo(serie.nome, legenda_original, legenda_simplificado))
    cima.legend(loc="best")
    cima.grid(alpha=0.3)

    baixo.plot(serie.tempo, erro, color="#333333")
    baixo.set_ylabel(f"|erro| em {serie.nome}")
    baixo.set_xlabel(_rotulo_do_tempo(unidade))
    baixo.grid(alpha=0.3)

    caminho = destino / f"{_arquivo(serie.nome)}.png"
    figura.savefig(caminho, dpi=DPI)
    plt.close(figura)

    return Grafico(
        variavel=serie.nome,
        caminho=caminho,
        png=caminho.read_bytes(),
        legenda_original=legenda_original,
        legenda_simplificado=legenda_simplificado,
    )


def _titulo(nome: str, original: str, simplificado: str) -> str:
    """Name the variable, and say what was summed when it is not a 1:1 mapping."""
    if original == nome and simplificado == nome:
        return nome
    return f"{nome}: {original} (original) vs. {simplificado} (simplificado)"


def _rotulo_do_tempo(unidade: str | None) -> str:
    return f"tempo ({unidade})" if unidade else "tempo (unidade do modelo)"


def _arquivo(nome: str) -> str:
    """Turn a report name into a file name, keeping it readable and safe on Windows."""
    seguro = "".join(letra if letra.isalnum() or letra in "-_" else "_" for letra in nome)
    return seguro or "variavel"
