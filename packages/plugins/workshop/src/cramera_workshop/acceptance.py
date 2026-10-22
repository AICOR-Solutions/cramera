"""
What the workshop's robot demos measure and must achieve: the measurement names of
``acceptance_metrics.json``, the assembly's stages and the tolerances, shared by the
demos that record and the release check that reads the recording.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# %% stages


class AssemblyStage(StrEnum):
    """
    The stages of the two-handed assembly, one top-level action each.
    """

    RETRIEVE = "Retrieve and place screw box"
    """
    The screw box is fetched from the shelf to the workbench.
    """

    PICK_SCREW = "Pick up screw"
    """
    The left hand picks a screw from the box.
    """

    APPROACH = "Move to assembly station"
    """
    The robot moves sideways to the assembly station.
    """

    PICK_DRIVER = "Pick up screwdriver"
    """
    The right hand picks the screwdriver from its cradle.
    """

    STABILIZE = "Stabilize screw at pilot hole"
    """
    The left hand holds the screw at the pilot hole.
    """

    ALIGN = "Align screwdriver"
    """
    The blade is seated in the screw's slot.
    """

    ENGAGE = "Engage screwdriver"
    """
    The thread is engaged with a first turn.
    """

    RELEASE = "Release supporting hand"
    """
    The left hand lets go and withdraws.
    """

    DRIVE = "Drive screw"
    """
    The screw is driven home.
    """

    RETURN = "Put screwdriver down"
    """
    The screwdriver goes back to its cradle.
    """


# %% measurements


class DemoMeasurement(StrEnum):
    """
    The names of what the demos measure, in ``acceptance_metrics.json``.
    """

    ACTION_STATUSES = "actionStatuses"
    """
    The name of each top-level action's life-cycle value when the plan ended.
    """

    BOX_POSITION_ERROR = "boxPositionError"
    """
    How far the set-down box is from its bench pose, in metres.
    """

    SCREW_POSITION_ERROR = "screwPositionError"
    """
    How far the inserted screw's tip is from the pilot hole's entrance, in metres.
    """

    SCREW_DEPTH = "screwDepth"
    """
    How far the driven screw's tip is below the entrance, in metres.
    """

    REQUIRED_DEPTH = "requiredDepth"
    """
    How far it must be, in metres.
    """

    DRIVER_RELEASED = "driverReleased"
    """
    Whether the screwdriver was put down free of the hand.
    """

    SUPPORT_RELEASED = "supportReleased"
    """
    Whether the supporting hand withdrew from the screw.
    """

    MINIMUM_COLLISION_DISTANCE = "minimumCollisionDistance"
    """
    The smallest collision distance the plan reached, in metres; absent when no contact
    was within reach.
    """

    CONTROL_TICKS = "controlTicks"
    """
    How many control periods the plan ran.
    """

    CONTENTS = "contentsPhysics"
    """
    What the contact world measured of the box's contents.
    """


class ContentsMeasurement(StrEnum):
    """
    The names of what the contact world measured of the box's contents.
    """

    MODEL = "model"
    """
    The coupling.
    """

    TICKS = "ticks"
    """
    How many control periods the contact world followed.
    """

    SIMULATED_SECONDS = "simulated_seconds"
    """
    The contact world's simulated time.
    """

    MAXIMUM_BOX_POSITION_LAG = "maximum_box_position_lag"
    """
    The largest distance between the native and the simulated box.
    """

    MAXIMUM_BOX_ANGULAR_LAG = "maximum_box_angular_lag"
    """
    The largest angle between the native and the simulated box.
    """

    MAXIMUM_RELATIVE_DISPLACEMENT = "maximum_relative_displacement"
    """
    The largest distance a screw slid in the box.
    """

    MAXIMUM_PROJECTION_CORRECTION = "maximum_projection_correction"
    """
    The largest distance between a screw's projected and simulated positions.
    """

    RETAINED_CONTENTS = "retained_contents"
    """
    Whether every screw ended in the box.
    """

    ESCAPED_CONTENTS = "escaped_contents"
    """
    The screws that ended outside it.
    """

    CONTENTS_COUNT = "contents_count"
    """
    How many screws were simulated.
    """


class ContentsModel(StrEnum):
    """
    The physical model a recording's box contents were simulated with.
    """

    RELATIVE_CONTACT = "one-way-relative-contact-contents"
    """
    Separately simulated contents put into the native box's frame, without feedback.
    """


ACTION_SUCCEEDED = "SUCCEEDED"
"""
The name of the native life-cycle value of an action that succeeded.
"""

# %% requirements


class Requirement(StrEnum):
    """
    What a demo's outcome must show; a failed run names the requirements it missed.
    """

    ACTIONS_SUCCEEDED = "every action succeeded"
    """
    Every top-level action ended successfully.
    """

    BOX_ON_BENCH = "the box is on its bench pose"
    """
    The screw box was set down where it belongs.
    """

    NO_PENETRATION = "nothing penetrated"
    """
    No bodies overlapped beyond the tolerance.
    """

    CONTENTS_RETAINED = "the screws stayed in the box"
    """
    Every screw ended inside the box's cavity.
    """

    SCREW_AT_PILOT = "the screw's tip is at the pilot hole"
    """
    The inserted screw's tip is at the entrance.
    """

    ALL_STAGES = "every stage ran"
    """
    The plan has every stage of the assembly.
    """

    SCREW_DRIVEN = "the screw is driven home"
    """
    The screw reached its required depth.
    """

    DRIVER_PUT_DOWN = "the screwdriver was put down"
    """
    The screwdriver is free of the hand.
    """

    SUPPORT_WITHDRAWN = "the supporting hand withdrew"
    """
    The left hand is clear of the screw.
    """


@dataclass(frozen=True)
class AssemblyTolerances:
    """
    How closely the demos must achieve their outcome.
    """

    box_position: float = 0.003
    """
    How far the box may end from its bench pose, in metres.
    """

    screw_position: float = 0.002
    """
    How far the inserted screw's tip may end from the entrance, in metres.
    """

    depth: float = 0.002
    """
    How far the screw's depth may end from the required depth, in metres.
    """

    penetration: float = 0.0005
    """
    How deep bodies may overlap at most, in metres.
    """

    support_clearance: float = 0.14
    """
    How far the supporting hand must withdraw from the screw, in metres.
    """


ASSEMBLY_TOLERANCES = AssemblyTolerances()
"""
The tolerances every demo is measured against.
"""
