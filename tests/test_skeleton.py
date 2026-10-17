"""Smoke tests for the package skeleton: it imports and exposes every pipeline module."""

import importlib
import tomllib
from pathlib import Path

import pytest

import reducheck

PIPELINE_MODULES = [
    "config",
    "simulation",
    "mapping",
    "metrics",
    "qualitative",
    "verdict",
    "report",
    "cli",
]


def test_package_exposes_version() -> None:
    assert reducheck.__version__


def test_version_is_the_same_in_pyproject_and_readme() -> None:
    # The version is written in three places by hand; the tag v0.3.0 has to match all three.
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == reducheck.__version__
    assert f"reducheck {reducheck.__version__}" in (root / "README.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("name", PIPELINE_MODULES)
def test_pipeline_module_is_importable_and_documented(name: str) -> None:
    module = importlib.import_module(f"reducheck.{name}")
    assert module.__doc__, f"módulo {name} sem docstring"
