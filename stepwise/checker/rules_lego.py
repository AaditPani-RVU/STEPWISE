"""Matching and alert text for the stud grid (FR-CHK-3..6).

The error taxonomy of plan 2.6, made precise enough to implement:

    a pending step wants this cell, part differs   -> wrong brick    (FR-CHK-5)
    a pending step wants this cell, only rot differs -> wrong rotation (FR-CHK-6)
    this part is wanted, but somewhere else        -> wrong position  (FR-CHK-6)
    nothing wants it                               -> extra part     (FR-CHK-6)
    a completed step's brick is gone               -> removed part    (FR-CHK-6)

Out-of-order and missed-step are not here: they come from the generic
precondition loop and the session-end sweep in the engine, because they are
properties of the dependency graph rather than of the grid.
"""

from __future__ import annotations

from typing import NamedTuple

from stepwise.compiler.schema import LoweredAction, PartRef, Pose, Precondition
from stepwise.events import COMPLETED, OPEN, Alert, Event, Status

WRONG_BRICK = "wrong_brick"
WRONG_POSITION = "wrong_position"
WRONG_ROTATION = "wrong_rotation"
EXTRA_PART = "extra_part"
REMOVED_PART = "removed_part"

def rotations_indistinguishable(part: PartRef, a: int, b: int) -> bool:
    """Would these two rotations of this part look identical on the plate?

    A 2x4 brick at 0 and at 180 degrees covers the same studs and presents the
    same face, and a 2x2 is the same at all four. Alerting on a difference no
    camera can see would be a false alert by construction, and NFR-REL-2 puts a
    budget of one per build on those.
    """
    w, h = part.dims
    if w == h:
        return True
    return a % 180 == b % 180


def pose_matches(observed: Pose, expected: Pose, part: PartRef) -> bool:
    return (
        observed.x == expected.x
        and observed.y == expected.y
        and observed.layer == expected.layer
        and rotations_indistinguishable(part, observed.rot, expected.rot)
    )


def _cells_match(a: Pose, b: Pose) -> bool:
    return a.x == b.x and a.y == b.y and a.layer == b.layer


def _pose_str(p: Pose) -> str:
    return f"({p.x},{p.y}) on layer {p.layer}"


class _Placement(NamedTuple):
    """An action that puts a known part at a known pose.

    A `LoweredAction` has optional `part` and `pose` because Jenga's actions have
    neither. Filtering for the ones that do, into a type that says so, keeps
    every use below free of None-handling that the filter has already settled.
    """

    action: LoweredAction
    part: PartRef
    pose: Pose


class StudGridPolicy:
    """The LEGO half of the checker."""

    def match(
        self, ev: Event, actions: list[LoweredAction], status: dict[str, Status]
    ) -> LoweredAction | None:
        if ev.part is None or ev.pose is None:
            return None
        for cand in self._open(actions, status):
            if cand.part == ev.part and pose_matches(ev.pose, cand.pose, cand.part):
                return cand.action
        return None

    def unmatched(
        self, ev: Event, actions: list[LoweredAction], status: dict[str, Status]
    ) -> list[Alert]:
        part, pose = ev.part, ev.pose
        if part is None or pose is None:
            return []
        open_actions = self._open(actions, status)

        # Something is wanted at exactly this cell, so the cell is not the
        # problem -- the brick or its rotation is.
        at_cell = [c for c in open_actions if _cells_match(pose, c.pose)]
        if at_cell:
            same_part = next((c for c in at_cell if c.part == part), None)
            if same_part is not None:
                return [
                    Alert(
                        t=ev.t,
                        code=WRONG_ROTATION,
                        rule="lego.wrong_rotation",
                        target=same_part.action.id,
                        text=(
                            f"The {part} at {_pose_str(pose)} is turned "
                            f"{pose.rot} degrees, but step {same_part.action.id} needs it "
                            f"at {same_part.pose.rot}: \"{same_part.action.instruction}\""
                        ),
                    )
                ]
            wanted = at_cell[0]
            return [
                Alert(
                    t=ev.t,
                    code=WRONG_BRICK,
                    rule="lego.wrong_brick",
                    target=wanted.action.id,
                    text=(
                        f"That is a {part} at {_pose_str(pose)}, but step "
                        f"{wanted.action.id} needs a {wanted.part} there: "
                        f"\"{wanted.action.instruction}\""
                    ),
                )
            ]

        # The brick is one the model uses, just not here.
        wants_part = [c for c in open_actions if c.part == part]
        if wants_part:
            nearest = min(wants_part, key=lambda c: self._distance(pose, c.pose))
            off = self._distance(pose, nearest.pose)
            return [
                Alert(
                    t=ev.t,
                    code=WRONG_POSITION,
                    rule="lego.wrong_position",
                    target=nearest.action.id,
                    text=(
                        f"The {part} is at {_pose_str(pose)}, {off} stud(s) from where "
                        f"step {nearest.action.id} needs it, {_pose_str(nearest.pose)}: "
                        f"\"{nearest.action.instruction}\""
                    ),
                )
            ]

        return [
            Alert(
                t=ev.t,
                code=EXTRA_PART,
                rule="lego.extra_part",
                text=(
                    f"A {part} is on the plate at {_pose_str(pose)}, but no remaining "
                    f"step in this model uses it there."
                ),
            )
        ]

    def on_remove(
        self, ev: Event, actions: list[LoweredAction], status: dict[str, Status]
    ) -> list[Alert]:
        """A brick leaving a completed step's cell undoes that step.

        The status goes back to `pending` rather than to `error`: the user may
        be correcting themselves, and if they never replace it the session-end
        sweep reports it as a missed step anyway.
        """
        if ev.pose is None:
            return []
        for action in actions:
            if action.pose is None or not _cells_match(ev.pose, action.pose):
                continue
            if status.get(action.id) not in COMPLETED:
                continue
            status[action.id] = "pending"
            return [
                Alert(
                    t=ev.t,
                    code=REMOVED_PART,
                    rule="lego.removed_part",
                    target=action.id,
                    text=(
                        f"The {action.part} from step {action.id} has been taken off "
                        f"{_pose_str(action.pose)}; that step is no longer done."
                    ),
                )
            ]
        return []

    def matches_hint(self, ev: Event, action: LoweredAction) -> bool:
        """A hint is credible only if it names the part; pose is not observable
        during occlusion, which is when hints matter (plan 2.5)."""
        return ev.part is not None and action.part == ev.part

    def explain(self, pre: Precondition, action: LoweredAction, ev: Event) -> str:
        return f"{pre.text.capitalize()}. Step {action.id} is \"{action.instruction}\"."

    def missed_text(self, action: LoweredAction | None, action_id: str) -> str:
        part = None if action is None else action.part
        pose = None if action is None else action.pose
        if action is None or part is None or pose is None:
            return f"Step {action_id} was never completed."
        return (
            f"Step {action_id} was never done: the {part} is missing from "
            f"{_pose_str(pose)} -- \"{action.instruction}\""
        )

    @staticmethod
    def _open(actions: list[LoweredAction], status: dict[str, Status]) -> list[_Placement]:
        """Placements still open to being matched.

        `active` counts as open: a temporal hint may have moved a step there
        before the state diff confirmed it (plan 2.5).
        """
        return [
            _Placement(a, a.part, a.pose)
            for a in actions
            if a.part is not None and a.pose is not None and status.get(a.id) in OPEN
        ]

    @staticmethod
    def _distance(a: Pose, b: Pose) -> int:
        return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.layer - b.layer)
