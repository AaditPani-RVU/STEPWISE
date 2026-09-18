"""Fixtures built from the spec examples in the plan (sections 4.2 and 4.3)."""

from pathlib import Path

import pytest

from stepwise.compiler.schema import ConstraintSpec, DagSpec, load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"


@pytest.fixture
def dag_spec() -> DagSpec:
    spec = load_spec(SPECS / "example_dag.json")
    assert isinstance(spec, DagSpec)
    return spec


@pytest.fixture
def constraint_spec() -> ConstraintSpec:
    spec = load_spec(SPECS / "example_constraints.json")
    assert isinstance(spec, ConstraintSpec)
    return spec
