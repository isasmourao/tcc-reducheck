"""Allow ``python -m reducheck`` to run the same command line as the installed script."""

from __future__ import annotations

from reducheck.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
