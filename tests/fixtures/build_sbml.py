"""Translate the Antimony toy models in this folder into SBML.

Run it after editing any ``.ant`` file::

    python tests/fixtures/build_sbml.py

Both the ``.ant`` and the generated ``.xml`` files are kept under version
control, so the test suite does not depend on the Antimony translator.
"""

from __future__ import annotations

import sys
from pathlib import Path

import antimony

FIXTURES_DIR = Path(__file__).parent


def antimony_to_sbml(ant_path: Path) -> Path:
    """Translate one Antimony file into SBML and return the written path."""
    antimony.clearPreviousLoads()
    if antimony.loadAntimonyFile(str(ant_path)) < 0:
        raise RuntimeError(f"{ant_path.name}: {antimony.getLastError()}")
    module = antimony.getMainModuleName()
    sbml = antimony.getSBMLString(module)
    if not sbml:
        raise RuntimeError(f"{ant_path.name}: {antimony.getLastError()}")
    xml_path = ant_path.with_suffix(".xml")
    xml_path.write_text(sbml, encoding="utf-8")
    return xml_path


def main() -> int:
    """Translate every Antimony file in the fixtures folder."""
    for ant_path in sorted(FIXTURES_DIR.glob("*.ant")):
        xml_path = antimony_to_sbml(ant_path)
        print(f"{ant_path.name} -> {xml_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
