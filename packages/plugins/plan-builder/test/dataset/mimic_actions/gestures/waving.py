"""
Actions whose fields cover what the action discovery reads: every kind of field, a field
typed only while type checking, a derived grasp and abstract classes.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto

from typing_extensions import TYPE_CHECKING, Optional

from coraplex.datastructures.enums import Arms
from coraplex.datastructures.grasp import GraspDescription
from coraplex.robot_plans.actions.base import ActionDescription
from semantic_digital_twin.robots.robot_parts import EndEffector
from semantic_digital_twin.semantic_annotations.semantic_annotations import Tool
from semantic_digital_twin.spatial_types import Pose
from semantic_digital_twin.world_description.world_entity import Body

if TYPE_CHECKING:
    from cramera_plan_builder.cram.missing_module import TypeCheckingOnly


class Speed(IntEnum):
    """
    How fast a gesture is.
    """

    SLOW = 1
    """
    Slowly.
    """

    FAST = 2
    """
    Quickly.
    """


class Mood(Enum):
    """
    How a gesture feels.
    """

    HAPPY = auto()
    """
    Happily.
    """

    SAD = auto()
    """
    Sadly.
    """


@dataclass(kw_only=True)
class Gesture(ActionDescription, ABC):
    """
    A gesture, abstract by deriving from ABC directly.
    """

    note: TypeCheckingOnly = None
    """
    A field typed with a class importable only while type checking.
    """

    def _action_plan(self) -> None:
        return None


@dataclass
class WaveAction(Gesture):
    """
    Wave with an arm.

    The second paragraph is not part of the documentation.
    """

    arm: Arms
    """
    The arm that waves.
    """

    speed: Speed = Speed.SLOW
    """
    How fast it waves.
    """

    mood: Optional[Mood] = None
    """
    How it feels.
    """

    times: int = 3
    """
    How often it waves.
    """

    height: float = 1.5
    """
    How high it waves.
    """

    shout: bool = False
    """
    Whether it shouts.
    """

    words: Optional[str] = None
    """
    What it says.
    """

    toward: Optional[Pose] = None
    """
    Where it waves to.
    """

    effector: Optional[EndEffector] = None
    """
    A robot part, which a person does not pick.
    """

    rhythm: list = field(default_factory=list)
    """
    A field of a type without a form control, with a default.
    """


@dataclass
class HandOverAction(ActionDescription):
    """
    Hand an object over with a tool.
    """

    target_location: Pose | Iterable[Pose]
    """
    Where the object goes.
    """

    object_designator: Body
    """
    The object handed over.
    """

    arm: Arms
    """
    The arm handing it over.
    """

    grasp_description: GraspDescription
    """
    How the object is held.
    """

    tool: Tool
    """
    The tool used.
    """

    def _action_plan(self) -> None:
        return None


@dataclass
class PointAction(ActionDescription):
    """
    Point somewhere with a held grasp but without an object.
    """

    target_location: Pose
    """
    Where to point.
    """

    grasp_description: GraspDescription
    """
    A grasp that cannot be derived without an object.
    """

    def _action_plan(self) -> None:
        return None


@dataclass
class ShrugAction(ActionDescription):
    """
    Shrug while thinking of something only type checking knows.
    """

    thought: TypeCheckingOnly
    """
    A required field whose type cannot be resolved.
    """

    def _action_plan(self) -> None:
        return None
