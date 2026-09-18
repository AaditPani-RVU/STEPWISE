"""Spec validation (FR-CMP-6, FR-CMP-7).

A compiled spec is rejected unless it passes every check below. The output is a
list of `Problem`s rather than an exception, because FR-CMP-7 needs the failing
check and the offending id to hand back to the LLM for one repair round, and
FR-CMP-9 needs them to show a human in the spec editor.

Errors block the run. Warnings do not, but they are the compiler-accuracy
signal that EV-CMP-2 reports on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stepwise.compiler.expr import check_expr
from stepwise.compiler.schema import ConstraintSpec, DagSpec, Step

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    code: str
    severity: Severity
    target: str  # step, action or precondition id ("" when spec-wide)
    message: str

    def __str__(self) -> str:
        where = f" [{self.target}]" if self.target else ""
        return f"{self.severity}: {self.code}{where}: {self.message}"


def errors(problems: list[Problem]) -> list[Problem]:
    return [p for p in problems if p.severity == "error"]


def is_valid(problems: list[Problem]) -> bool:
    return not errors(problems)


# --- DAG checks ---------------------------------------------------------------------

def _check_ids(spec: DagSpec) -> list[Problem]:
    seen: set[str] = set()
    out = []
    for step in spec.steps:
        if step.id in seen:
            out.append(Problem("duplicate_id", "error", step.id, "step id is used twice"))
        seen.add(step.id)
    for step in spec.steps:
        for kind in ("hard_depends_on", "soft_depends_on"):
            for dep in getattr(step, kind):
                if dep not in seen:
                    out.append(
                        Problem("unknown_dependency", "error", step.id,
                                f"{kind} names {dep!r}, which is not a step")
                    )
                elif dep == step.id:
                    out.append(
                        Problem("self_dependency", "error", step.id, "step depends on itself")
                    )
    return out


def _check_cycles(spec: DagSpec) -> list[Problem]:
    """Depth-first cycle detection over hard and soft dependencies together."""
    ids = {s.id for s in spec.steps}
    deps = {
        s.id: [d for d in (*s.hard_depends_on, *s.soft_depends_on) if d in ids and d != s.id]
        for s in spec.steps
    }
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(deps, WHITE)
    out: list[Problem] = []

    def visit(node: str, path: list[str]) -> None:
        colour[node] = GREY
        for dep in deps[node]:
            if colour[dep] == GREY:
                cycle = " -> ".join([*path[path.index(dep):], node, dep])
                out.append(Problem("cycle", "error", node, f"dependency cycle: {cycle}"))
            elif colour[dep] == WHITE:
                visit(dep, [*path, node])
        colour[node] = BLACK

    for node in deps:
        if colour[node] == WHITE:
            visit(node, [])
    return out


def _check_bounds(spec: DagSpec) -> list[Problem]:
    out = []
    for step in spec.steps:
        outside = {
            (x, y) for x, y in step.footprint
            if not (0 <= x < spec.baseplate.studs_x and 0 <= y < spec.baseplate.studs_y)
        }
        if outside:
            out.append(
                Problem("out_of_bounds", "error", step.id,
                        f"{step.part} at {step.pose.x},{step.pose.y} runs off the baseplate "
                        f"at {sorted(outside)[:3]}")
            )
    return out


def _check_collisions(spec: DagSpec) -> list[Problem]:
    """Two parts may not occupy the same cell on the same layer."""
    occupied: dict[tuple[int, int, int], str] = {}
    out = []
    for step in spec.steps:
        for x, y in step.footprint:
            key = (x, y, step.pose.layer)
            if key in occupied:
                out.append(
                    Problem("collision", "error", step.id,
                            f"cell {x},{y} on layer {step.pose.layer} is already used "
                            f"by {occupied[key]}")
                )
            else:
                occupied[key] = step.id
    return out


def _supporters(step: Step, spec: DagSpec) -> set[str]:
    """Steps whose footprint lies directly beneath this one."""
    if step.pose.layer == 0:
        return set()
    below = step.pose.layer - 1
    cells = step.footprint
    return {
        other.id for other in spec.steps
        if other.id != step.id and other.pose.layer == below and other.footprint & cells
    }


def _check_support(spec: DagSpec) -> list[Problem]:
    """Nothing floats, and hard dependencies match the geometry that implies them."""
    out = []
    for step in spec.steps:
        if step.pose.layer == 0:
            continue
        supporters = _supporters(step, spec)
        if not supporters:
            out.append(
                Problem("floating", "error", step.id,
                        f"sits on layer {step.pose.layer} with nothing beneath it")
            )
            continue
        # The compiler is meant to record physical support as a hard dependency
        # (FR-CMP-3). A gap here is the single most useful compiler-accuracy
        # signal we have, and it is exactly what EV-CMP-2 scores.
        missing = supporters - set(step.hard_depends_on)
        if missing:
            out.append(
                Problem("missing_hard_dependency", "warning", step.id,
                        f"physically supported by {sorted(missing)}, "
                        f"but they are not in hard_depends_on")
            )
    return out


def _check_soft_order(spec: DagSpec) -> list[Problem]:
    """A hard dependency that is not also a soft one is almost always a slip."""
    return [
        Problem("hard_dep_not_ordered", "warning", step.id,
                f"{sorted(set(step.hard_depends_on) - set(step.soft_depends_on))} "
                f"is a hard dependency but not a stated order")
        for step in spec.steps
        if set(step.hard_depends_on) - set(step.soft_depends_on)
    ]


# --- constraint checks --------------------------------------------------------------

def _check_exprs(spec: ConstraintSpec) -> list[Problem]:
    out = []
    for action in spec.actions:
        for pre in action.preconditions:
            out += [
                Problem("bad_expr", "error", pre.id, err.message)
                for err in check_expr(pre.expr)
            ]
    for term in spec.terminal:
        out += [
            Problem("bad_expr", "error", term.id, err.message)
            for err in check_expr(term.expr)
        ]
    return out


def _check_constraint_ids(spec: ConstraintSpec) -> list[Problem]:
    seen: set[str] = set()
    out = []
    for action in spec.actions:
        if action.id in seen:
            out.append(Problem("duplicate_id", "error", action.id, "action id is used twice"))
        seen.add(action.id)
        pre_ids: set[str] = set()
        for pre in action.preconditions:
            if pre.id in pre_ids:
                out.append(
                    Problem("duplicate_id", "error", pre.id, "precondition id is used twice")
                )
            pre_ids.add(pre.id)
    return out


def _check_satisfiable(spec: ConstraintSpec) -> list[Problem]:
    """Structural satisfiability: at least one action, and a way for a game to end.

    The full check FR-CMP-6 asks for -- that a legal move exists from the initial
    state -- needs the tower lattice to simulate against, so it is completed when
    the Jenga state model lands (FR-STA-7). Until then this catches the specs that
    are unrunnable on their face.
    """
    out = []
    if not spec.actions:
        out.append(Problem("unsatisfiable", "error", "", "spec declares no actions"))
    for action in spec.actions:
        if not action.preconditions:
            out.append(
                Problem("unconstrained_action", "warning", action.id,
                        "action has no preconditions, so nothing about it can be illegal")
            )
    if not spec.terminal:
        out.append(
            Problem("no_terminal", "warning", "",
                    "no terminal condition, so a session can never end on its own")
        )
    return out


# --- entry point --------------------------------------------------------------------

def validate(spec: DagSpec | ConstraintSpec) -> list[Problem]:
    """Every problem with this spec, errors and warnings, in a stable order."""
    if isinstance(spec, DagSpec):
        problems = (
            _check_ids(spec)
            + _check_bounds(spec)
            + _check_collisions(spec)
            + _check_support(spec)
            + _check_soft_order(spec)
        )
        # A cycle makes the traversal meaningless, so only look once ids resolve.
        if not [p for p in problems if p.code in {"unknown_dependency", "self_dependency"}]:
            problems += _check_cycles(spec)
    else:
        problems = _check_constraint_ids(spec) + _check_exprs(spec) + _check_satisfiable(spec)

    order = {"error": 0, "warning": 1}
    return sorted(problems, key=lambda p: (order[p.severity], p.target, p.code))
