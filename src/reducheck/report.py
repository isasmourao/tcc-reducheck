"""Render the results as JSON, a readable report and plots.

This version writes ``resultado.json`` only; the HTML report and the plots are later tasks.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from reducheck.simulation import RuidoNumerico
from reducheck.verdict import Veredito

__all__ = ["NOME_DO_JSON", "como_dicionario", "salvar_json"]

#: File name used for the machine-readable result, as in ``docs/produto.md``.
NOME_DO_JSON = "resultado.json"


def como_dicionario(
    veredito: Veredito,
    ruido: RuidoNumerico | None = None,
    avisos: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the verdict as the structure written to ``resultado.json``.

    ``avisos`` are the warnings that do not belong to a single metric -- the reference
    numerical noise and the thresholds too close to it -- and come first, because they say
    how much of the numbers below is worth reading.
    """
    return {
        "aprovado": veredito.aprovado,
        "porcentagem": veredito.porcentagem,
        "avisos": [*avisos, *veredito.avisos],
        "ruido_numerico": None if ruido is None else _ruido(ruido),
        "criterios": [
            {
                "metrica": item.metrica,
                "variavel": item.variavel,
                "valor": item.valor,
                "limite": item.limite,
                "resultado": "passou" if item.passou else "falhou",
                "descricao": item.descricao,
                "avisos": list(item.avisos),
                "detalhes": dict(item.detalhes),
            }
            for item in veredito.criterios
        ],
    }


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
) -> Path:
    """Write ``resultado.json`` into ``pasta``, creating the folder if needed."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_DO_JSON
    conteudo = json.dumps(
        como_dicionario(veredito, ruido, avisos), ensure_ascii=False, indent=2
    )
    caminho.write_text(conteudo + "\n", encoding="utf-8")
    return caminho
