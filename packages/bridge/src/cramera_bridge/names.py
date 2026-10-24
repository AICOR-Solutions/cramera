"""
The one table between CRAM's names and the protocol's: every CRAM class whose name a
saved plan, a recording or a check relies on is pinned here to an identifier of the
protocol's own, so renaming the class in CRAM changes this table and nothing else.

A class is pinned by its dotted path. When CRAM renames or moves it, the path is updated
here and its identifier stays; :attr:`PinnedClass.saved_as` keeps the names files saved
before the protocol had its own names, so they are read once through this table. A class
the workspace offers that is not pinned yet still works under an identifier derived from
its name, and the bridge's tests fail until it is pinned.
"""

from __future__ import annotations

import functools
import importlib
import re
from dataclasses import dataclass

from typing_extensions import List, Optional, Tuple

from cramera_protocol.bundle.scene import PlanNodeKind

# %% pinned classes


@dataclass(frozen=True)
class PinnedClass:
    """
    A CRAM class pinned to a protocol identifier.
    """

    identifier: str
    """
    The protocol's name of the class, which never changes.
    """

    path: str
    """
    Where the class is defined: its module and name, ``module.Class``.
    """

    saved_as: Tuple[str, ...] = ()
    """
    The names files saved for the class before the protocol named it.
    """

    def resolve(self) -> type:
        """
        :return: The class.
        :raises ImportError: When its module is gone.
        :raises AttributeError: When its module defines no such class.
        """
        module, _, name = self.path.rpartition(".")
        return getattr(importlib.import_module(module), name)


ACTIONS = (
    PinnedClass(
        "close",
        "coraplex.robot_plans.actions.core.container.CloseAction",
        ("CloseAction",),
    ),
    PinnedClass(
        "container",
        "coraplex.robot_plans.actions.core.container.ContainerAction",
        ("ContainerAction",),
    ),
    PinnedClass(
        "detect",
        "coraplex.robot_plans.actions.core.misc.DetectAction",
        ("DetectAction",),
    ),
    PinnedClass(
        "elevator_navigation",
        "coraplex.robot_plans.actions.core.navigation.ElevatorNavigation",
        ("ElevatorNavigation",),
    ),
    PinnedClass(
        "face_at",
        "coraplex.robot_plans.actions.core.navigation.FaceAtAction",
        ("FaceAtAction",),
    ),
    PinnedClass(
        "follow_tool_center_point_path",
        "coraplex.robot_plans.actions.core.robot_body.FollowToolCenterPointPathAction",
        ("FollowToolCenterPointPathAction",),
    ),
    PinnedClass(
        "grasping",
        "coraplex.robot_plans.actions.core.pick_up.GraspingAction",
        ("GraspingAction",),
    ),
    PinnedClass(
        "look_at",
        "coraplex.robot_plans.actions.core.navigation.LookAtAction",
        ("LookAtAction",),
    ),
    PinnedClass(
        "move_manipulator",
        "coraplex.robot_plans.actions.core.robot_body.MoveManipulatorAction",
        ("MoveManipulatorAction",),
    ),
    PinnedClass(
        "move_to_reach",
        "coraplex.robot_plans.actions.core.misc.MoveToReach",
        ("MoveToReach",),
    ),
    PinnedClass(
        "move_torso",
        "coraplex.robot_plans.actions.core.robot_body.MoveTorsoAction",
        ("MoveTorsoAction",),
    ),
    PinnedClass(
        "navigate",
        "coraplex.robot_plans.actions.core.navigation.NavigateAction",
        ("NavigateAction",),
    ),
    PinnedClass(
        "open",
        "coraplex.robot_plans.actions.core.container.OpenAction",
        ("OpenAction",),
    ),
    PinnedClass(
        "park_arms",
        "coraplex.robot_plans.actions.core.robot_body.ParkArmsAction",
        ("ParkArmsAction",),
    ),
    PinnedClass(
        "path_planning_navigate",
        "coraplex.robot_plans.actions.core.navigation.PathPlanningNavigateAction",
        ("PathPlanningNavigateAction",),
    ),
    PinnedClass(
        "pick_up",
        "coraplex.robot_plans.actions.core.pick_up.PickUpAction",
        ("PickUpAction",),
    ),
    PinnedClass(
        "place",
        "coraplex.robot_plans.actions.core.placing.PlaceAction",
        ("PlaceAction",),
    ),
    PinnedClass(
        "reach",
        "coraplex.robot_plans.actions.core.pick_up.ReachAction",
        ("ReachAction",),
    ),
    PinnedClass(
        "set_gripper",
        "coraplex.robot_plans.actions.core.robot_body.SetGripperAction",
        ("SetGripperAction",),
    ),
    PinnedClass(
        "cutting",
        "coraplex.robot_plans.actions.composite.tool_based.CuttingAction",
        ("CuttingAction",),
    ),
    PinnedClass(
        "face_and_look_at",
        "coraplex.robot_plans.actions.composite.facing.FaceAndLookAtAction",
        ("FaceAndLookAtAction",),
    ),
    PinnedClass(
        "mixing",
        "coraplex.robot_plans.actions.composite.tool_based.MixingAction",
        ("MixingAction",),
    ),
    PinnedClass(
        "move_and_open",
        "coraplex.robot_plans.actions.composite.transporting.MoveAndOpenAction",
        ("MoveAndOpenAction",),
    ),
    PinnedClass(
        "move_and_pick_up",
        "coraplex.robot_plans.actions.composite.transporting.MoveAndPickUpAction",
        ("MoveAndPickUpAction",),
    ),
    PinnedClass(
        "move_and_place",
        "coraplex.robot_plans.actions.composite.transporting.MoveAndPlaceAction",
        ("MoveAndPlaceAction",),
    ),
    PinnedClass(
        "pick_and_place",
        "coraplex.robot_plans.actions.composite.transporting.PickAndPlaceAction",
        ("PickAndPlaceAction",),
    ),
    PinnedClass(
        "pouring",
        "coraplex.robot_plans.actions.composite.tool_based.PouringAction",
        ("PouringAction",),
    ),
    PinnedClass(
        "transport",
        "coraplex.robot_plans.actions.composite.transporting.TransportAction",
        ("TransportAction",),
    ),
    PinnedClass(
        "wiping",
        "coraplex.robot_plans.actions.composite.tool_based.WipingAction",
        ("WipingAction",),
    ),
)
"""
The native actions a plan step names.
"""

ROBOTS = (
    PinnedClass("armar7", "semantic_digital_twin.robots.armar7.Armar7", ("Armar7",)),
    PinnedClass("daisy", "semantic_digital_twin.robots.daisy.DAiSy", ("DAiSy",)),
    PinnedClass("garmi", "semantic_digital_twin.robots.garmi.Garmi", ("Garmi",)),
    PinnedClass("hsrb", "semantic_digital_twin.robots.hsrb.HSRB", ("HSRB",)),
    PinnedClass("icub3", "semantic_digital_twin.robots.icub3.ICub3", ("ICub3",)),
    PinnedClass("justin", "semantic_digital_twin.robots.justin.Justin", ("Justin",)),
    PinnedClass(
        "mmp_dresden",
        "semantic_digital_twin.robots.mmp_dresden.MMPDresden",
        ("MMPDresden",),
    ),
    PinnedClass("pr2", "semantic_digital_twin.robots.pr2.PR2", ("PR2",)),
    PinnedClass(
        "stretch", "semantic_digital_twin.robots.stretch.Stretch", ("Stretch",)
    ),
    PinnedClass("tiago", "semantic_digital_twin.robots.tiago.Tiago", ("Tiago",)),
    PinnedClass(
        "tiago_mujoco",
        "semantic_digital_twin.robots.tiago.TiagoMujoco",
        ("TiagoMujoco",),
    ),
    PinnedClass("tracy", "semantic_digital_twin.robots.tracy.Tracy", ("Tracy",)),
    PinnedClass(
        "unitree_g1",
        "semantic_digital_twin.robots.unitree_g1.UnitreeG1",
        ("UnitreeG1",),
    ),
)
"""
The robot annotations a plan's robot names as its model.
"""

PLAN_NODE_KINDS = (
    ("coraplex.plans.plan_node.ActionNode", PlanNodeKind.ACTION),
    ("coraplex.plans.plan_node.MotionNode", PlanNodeKind.MOTION),
    ("coraplex.plans.condition_nodes.ConditionNode", PlanNodeKind.CONDITION),
    ("coraplex.language.ExecutesSequentially", PlanNodeKind.SEQUENCE),
    ("coraplex.language.ExecutesInParallel", PlanNodeKind.PARALLEL),
    ("coraplex.language.MonitorNode", PlanNodeKind.MONITOR),
    ("coraplex.language.CodeNode", PlanNodeKind.CODE),
    ("coraplex.plans.attachment_nodes.ReAttachNode", PlanNodeKind.ATTACHMENT),
    ("coraplex.plans.underspecified.UnderspecifiedNode", PlanNodeKind.UNDERSPECIFIED),
)
"""
The plan node classes by the kind the protocol names them, tried in order; a node is of
the kind of the first class it is an instance of, else :attr:`PlanNodeKind.OTHER`.
"""

# %% identifiers of classes not pinned yet

WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
"""
Where a class name's words meet.
"""

ACTION_SUFFIX = "Action"
"""
The ending of most action class names, left out of their identifiers.
"""


def derived_identifier(class_name: str, suffix: str = "") -> str:
    """
    :param class_name: A class name, such as ``PickUpAction``.
    :param suffix: An ending left out, such as ``Action``.
    :return: Its words in lower case joined by underscores, such as ``pick_up``.
    """
    words = class_name.removesuffix(suffix) or class_name
    return WORD_BOUNDARY.sub("_", words).lower()


# %% tables


@dataclass(frozen=True)
class ClassNames:
    """
    Translates between the classes of one table and their protocol identifiers.
    """

    pinned: Tuple[PinnedClass, ...]
    """
    The pinned classes.
    """

    suffix: str = ""
    """
    The ending derived identifiers leave out.
    """

    def entry_of(self, cls: type) -> Optional[PinnedClass]:
        """
        :param cls: A CRAM class.
        :return: Its pinned entry, or None when it is not pinned.
        """
        path = f"{cls.__module__}.{cls.__name__}"
        return next((entry for entry in self.pinned if entry.path == path), None)

    def identifier_of(self, cls: type) -> str:
        """
        :param cls: A CRAM class.
        :return: Its pinned identifier, else one derived from its name.
        """
        entry = self.entry_of(cls)
        if entry is None:
            return derived_identifier(cls.__name__, self.suffix)
        return entry.identifier

    def saved_as(self, cls: type) -> List[str]:
        """
        :param cls: A CRAM class.
        :return: The names files saved for it before the protocol named it; for a class
            not pinned yet, its class name.
        """
        entry = self.entry_of(cls)
        return [cls.__name__] if entry is None else list(entry.saved_as)

    def matches(self, cls: type, name: str) -> bool:
        """
        :param cls: A CRAM class.
        :param name: A name a plan or a file uses for a class.
        :return: Whether the name is the class's identifier or a name it was saved as.
        """
        return name == self.identifier_of(cls) or name in self.saved_as(cls)


ACTION_NAMES = ClassNames(ACTIONS, ACTION_SUFFIX)
"""
The identifiers of the native actions.
"""

ROBOT_NAMES = ClassNames(ROBOTS)
"""
The identifiers of the robot annotations.
"""


@functools.cache
def plan_node_classes() -> Tuple[Tuple[type, PlanNodeKind], ...]:
    """
    :return: The classes of :data:`PLAN_NODE_KINDS` with their kinds, imported once.
    """
    return tuple(
        (PinnedClass(kind, path).resolve(), kind) for path, kind in PLAN_NODE_KINDS
    )


def plan_node_kind(node: object) -> PlanNodeKind:
    """
    :param node: A plan node.
    :return: The kind the protocol names it.
    """
    for cls, kind in plan_node_classes():
        if isinstance(node, cls):
            return kind
    return PlanNodeKind.OTHER
