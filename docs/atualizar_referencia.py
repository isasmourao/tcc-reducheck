"""Rewrite the configuration reference of the README from the pydantic schema.

Run after changing a field in ``src/reducheck/config.py``::

    python docs/atualizar_referencia.py

The table lives between two HTML comments in the README; ``tests/test_readme.py`` fails
while the copy there differs from what :func:`reducheck.config.referencia_dos_campos`
generates.
"""

from __future__ import annotations

from pathlib import Path

from reducheck.config import referencia_dos_campos

README = Path(__file__).resolve().parents[1] / "README.md"
INICIO = "<!-- referencia:inicio -->"
FIM = "<!-- referencia:fim -->"


def main() -> None:
    """Replace the text between the two markers with the generated table."""
    texto = README.read_text(encoding="utf-8")
    antes, resto = texto.split(INICIO, 1)
    _, depois = resto.split(FIM, 1)
    README.write_text(
        f"{antes}{INICIO}\n{referencia_dos_campos()}\n{FIM}{depois}", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
