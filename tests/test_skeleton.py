"""Smoke tests for the package skeleton: it imports and exposes every pipeline module."""

import importlib

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


@pytest.mark.parametrize("name", PIPELINE_MODULES)
def test_pipeline_module_is_importable_and_documented(name: str) -> None:
    module = importlib.import_module(f"reducheck.{name}")
    assert module.__doc__, f"módulo {name} sem docstring"
