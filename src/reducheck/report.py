"""Render the results as JSON, a readable report and plots.

This version writes ``resultado.json`` only; the HTML report and the plots are later tasks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reducheck.verdict import Veredito

__all__ = ["NOME_DO_JSON", "como_dicionario", "salvar_json"]

#: File name used for the machine-readable result, as in ``docs/produto.md``.
NOME_DO_JSON = "resultado.json"


def como_dicionario(veredito: Veredito) -> dict[str, Any]:
    """Return the verdict as the structure written to ``resultado.json``."""
    return {
        "aprovado": veredito.aprovado,
        "porcentagem": veredito.porcentagem,
        "avisos": list(veredito.avisos),
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


def salvar_json(veredito: Veredito, pasta: Path | str) -> Path:
    """Write ``resultado.json`` into ``pasta``, creating the folder if needed."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_DO_JSON
    conteudo = json.dumps(como_dicionario(veredito), ensure_ascii=False, indent=2)
    caminho.write_text(conteudo + "\n", encoding="utf-8")
    return caminho
