"""
The executing plan as the viewer shows it: every node with its native status.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum, StrEnum

from typing_extensions import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple

from cramera_bridge.exceptions import UnknownPlanNode
from cramera_bridge.live.perception_images import PerceptionImages
from cramera_bridge.live.recording import RunningAction
from cramera_bridge.live.world_model import ObjectKey
from cramera_bridge.robots import RobotRoster
from cramera_protocol.live_messages import ConstraintObservation, LivePlan, LivePlanNode
from coraplex.plans.plan_node import ActionNode, DesignatorNode, MotionNode, PlanNode
from coraplex.robot_plans.motions.misc import DetectingMotion
from giskardpy.motion_statechart.data_types import LifeCycleValues
from semantic_digital_twin.robots.robot_parts import Arm
from semantic_digital_twin.spatial_types.spatial_types import Pose
from semantic_digital_twin.world_description.world_entity import (
    Body,
    SemanticAnnotation,
)

if TYPE_CHECKING:
    from coraplex.plans.plan import Plan

PLAN_NODE_PREFIX = "plan_node_"
"""
The start of the identity of every node of the first plan performed; the rest is the
node's index in the plan graph.
"""

LATER_PLAN_NODE_PREFIX = "plan_{number}_node_"
"""
The start of the identity of every node of a later plan, naming the plan's number; the
rest is the node's index in the plan graph.
"""

FIRST_PLAN_NUMBER = 1
"""
The number of the first plan performed.
"""

SIGNATURE_SEPARATOR = "|"
"""
Separates the node identities of a plan's signature.
"""

ConstraintLookup = Callable[[str], List[ConstraintObservation]]
"""
Answers the constraint monitors attached to a plan node, by the node's identity.
"""

PARAMETER_SEPARATOR = ", "
"""
Joins the parts of a rendered parameter that has several, such as a pose's coordinates
or the fields of a nested description.
"""

COORDINATE_FORMAT = "{:.3f}"
"""
How a coordinate of a pose is rendered: to the millimetre.
"""

NUMBER_FORMAT = "{:g}"
"""
How a number is rendered: as short as it reads back exactly enough.
"""

SWITCH_VALUES = {True: "on", False: "off"}
"""
How a boolean is rendered.
"""


class PlanNodeStatus(StrEnum):
    """
    The status of a plan node as the viewer and the recorded bundles name it, which
    keeps the names coraplex used before its nodes took the motion statechart's life
    cycle values.
    """

    CREATED = "CREATED"
    """
    The node has not run yet.
    """

    RUNNING = "RUNNING"
    """
    The node is running.
    """

    PAUSE = "PAUSE"
    """
    The node was running and is paused.
    """

    SUCCEEDED = "SUCCEEDED"
    """
    The node ended having reached its goal.
    """

    FAILED = "FAILED"
    """
    The node ended without reaching its goal.
    """

    INTERRUPTED = "INTERRUPTED"
    """
    The node was stopped before it ended.
    """

    @classmethod
    def of(cls, value: LifeCycleValues) -> PlanNodeStatus:
        """
        :param value: A node's native life cycle value.
        :return: The status it stands for.
        """
        return {
            LifeCycleValues.NOT_STARTED: cls.CREATED,
            LifeCycleValues.RUNNING: cls.RUNNING,
            LifeCycleValues.PAUSED: cls.PAUSE,
            LifeCycleValues.SUCCEEDED: cls.SUCCEEDED,
            LifeCycleValues.FAILED: cls.FAILED,
            LifeCycleValues.INTERRUPTED: cls.INTERRUPTED,
        }[value]


# %% designators


@dataclass(frozen=True)
class DesignatorSummary:
    """
    The arm and the body a node's designator names, and every field it holds rendered
    for reading.
    """

    node: PlanNode
    """
    The plan node.
    """

    def values(self) -> List[object]:
        """
        :return: The values of the node's designator's fields, or none for a node
            without a designator.
        """
        if not isinstance(self.node, DesignatorNode):
            return []
        return list(vars(self.node.designator).values())

    def arm(self) -> Optional[str]:
        """
        :return: The name of the first arm the designator names, on its own or among
            several arms.
        """
        for value in self.values():
            for candidate in value if isinstance(value, (list, tuple)) else [value]:
                if isinstance(candidate, Arm):
                    return str(candidate.name)
        return None

    def target(self, object_keys: Set[str]) -> Optional[str]:
        """
        :param object_keys: The keys of the published objects.
        :return: The key of the first published object the designator names, else the
            name of the first body it names.
        """
        bodies = [value for value in self.values() if isinstance(value, Body)]
        for body in bodies:
            if ObjectKey.of(body) in object_keys:
                return ObjectKey.of(body)
        return next((str(body.name) for body in bodies), None)

    def label(self) -> str:
        """
        :return: The class name of the designator, or of the node without one.
        """
        if isinstance(self.node, DesignatorNode):
            return type(self.node.designator).__name__
        return type(self.node).__name__

    def parameters(self, object_keys: Set[str]) -> Dict[str, str]:
        """
        :param object_keys: The keys of the published objects.
        :return: Every field of the designator that holds a value, by name, rendered
            as the viewer shows it; empty for a node without a designator.
        """
        if not isinstance(self.node, DesignatorNode):
            return {}
        return {
            name: self.render(value, object_keys)
            for name, value in self.fields_of(self.node.designator)
            if value is not None
        }

    @staticmethod
    def fields_of(value: object) -> List[Tuple[str, object]]:
        """
        :param value: A designator or a description nested in one.
        :return: Its fields by name: those a dataclass declares, else its attributes.
        """
        attributes = vars(value)
        if is_dataclass(value):
            return [
                (each.name, attributes[each.name])
                for each in fields(value)
                if each.init and each.name in attributes
            ]
        return list(attributes.items())

    @classmethod
    def render(cls, value: object, object_keys: Set[str], nested: bool = False) -> str:
        """
        :param value: A field's value.
        :param object_keys: The keys of the published objects.
        :param nested: Whether the value sits in a description nested in the
            designator; a description nested deeper is named by its class.
        :return: The value as the viewer shows it: a class by its name, an enumeration
            member by its name, a body by its published key else its name, an annotation
            by its name, a pose by its position, a boolean as on or off, a list by its
            items, a nested description by its fields, and anything else by its text.
        """
        if isinstance(value, type):
            return value.__name__
        if isinstance(value, Enum):
            return value.name
        if isinstance(value, Body):
            key = ObjectKey.of(value)
            return key if key in object_keys else str(value.name)
        if isinstance(value, SemanticAnnotation):
            return str(value.name)
        if isinstance(value, Pose):
            return PARAMETER_SEPARATOR.join(
                COORDINATE_FORMAT.format(float(coordinate))
                for coordinate in value.position.to_np()[:3]
            )
        if isinstance(value, bool):
            return SWITCH_VALUES[value]
        if isinstance(value, (int, float)):
            return NUMBER_FORMAT.format(value)
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return PARAMETER_SEPARATOR.join(
                cls.render(each, object_keys, nested) for each in value
            )
        if is_dataclass(value) and not nested:
            return PARAMETER_SEPARATOR.join(
                f"{name} {cls.render(inner, object_keys, nested=True)}"
                for name, inner in cls.fields_of(value)
                if inner is not None
            )
        if is_dataclass(value):
            return type(value).__name__
        return str(value)


# %% plan


@dataclass
class PerformedPlan:
    """
    A plan performed while the publisher ran, with the robot that performed it and its
    newest snapshot.
    """

    plan: Plan
    """
    The plan.
    """

    number: int
    """
    The plan's position among the plans performed, counted from one.
    """

    robot: Optional[str]
    """
    The display name of the robot that performed the plan, or None for a plan without a
    context.
    """

    latest: LivePlan = field(default_factory=LivePlan)
    """
    The plan's newest snapshot.
    """

    perceived: Dict[int, List[str]] = field(default_factory=dict)
    """
    What each perception step of the plan reported when it ended, by the step's index.
    """

    images: PerceptionImages = field(default_factory=PerceptionImages)
    """
    The images of what each perception step saw.
    """

    @classmethod
    def of_plan(
        cls, plan: Plan, number: int, images: PerceptionImages
    ) -> PerformedPlan:
        """
        :param plan: A plan that starts performing.
        :param number: Its position among the plans performed, counted from one.
        :param images: Takes and keeps the images of its perception steps.
        :return: The plan with the robot its context names.
        """
        robot = None if plan.context is None else plan.context.robot
        return cls(
            plan=plan,
            number=number,
            robot=None if robot is None else RobotRoster.label(robot),
            images=images,
        )

    def identifier(self, node: PlanNode) -> str:
        """
        :param node: A node of the plan.
        :return: The node's identity, which no node of another plan performed shares;
            the first plan's nodes keep the identity a recording of one plan gives them.
        """
        prefix = (
            PLAN_NODE_PREFIX
            if self.number == FIRST_PLAN_NUMBER
            else LATER_PLAN_NODE_PREFIX.format(number=self.number)
        )
        return f"{prefix}{node.index}"

    def root(self) -> Optional[PlanNode]:
        """
        :return: The plan's root, or None while its graph is no tree.
        """
        roots = [node for node in self.plan.all_nodes if node.parent is None]
        if len(roots) != 1:
            return None
        return roots[0]

    def describe(
        self, object_keys: Set[str], constraints: ConstraintLookup
    ) -> Optional[LivePlan]:
        """
        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: A snapshot of every node with its native status, or None while the
            plan's graph is being rebuilt.
        """
        root = self.root()
        if root is None:
            return None
        nodes = [
            self.node_description(node, object_keys, constraints)
            for node in [root] + root.descendants
        ]
        return LivePlan(
            signature=SIGNATURE_SEPARATOR.join(node.identifier for node in nodes),
            nodes=nodes,
        )

    def node_description(
        self,
        node: PlanNode,
        object_keys: Set[str],
        constraints: ConstraintLookup,
    ) -> LivePlanNode:
        """
        :param node: A node of the plan.
        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: The node with its native status.
        """
        summary = DesignatorSummary(node)
        identifier = self.identifier(node)
        parent = node.parent
        return LivePlanNode(
            identifier=identifier,
            parent=None if parent is None else self.identifier(parent),
            kind=type(node).__name__,
            label=summary.label(),
            status=PlanNodeStatus.of(node.status),
            arm=summary.arm(),
            target=summary.target(object_keys),
            constraints=constraints(identifier),
            parameters=summary.parameters(object_keys),
            perceived=(
                list(self.perceived.get(node.index, []))
                if self.is_perception(node)
                else None
            ),
            reason=None if node.reason is None else str(node.reason),
            images=(
                [image.document(image.key) for image in self.images.of_step(identifier)]
                if self.is_perception(node)
                else None
            ),
        )

    @staticmethod
    def is_perception(node: PlanNode) -> bool:
        """
        :param node: A node of the plan.
        :return: Whether it is a perception step: the motion that answers a perception
            query.
        """
        return isinstance(node, MotionNode) and isinstance(
            node.designator, DetectingMotion
        )

    def observe_ended(self, node: PlanNode, object_keys: Set[str]) -> None:
        """
        Keep what a perception step reported when it ends: the objects of the queried
        kind in the queried region that the robot's camera sees, once the detection was
        applied to the world, and the images of what it saw; a step that failed reported
        nothing, but its images show what it saw instead.

        :param node: A node of the plan that ended.
        :param object_keys: The keys of the published objects.
        """
        if not self.is_perception(node):
            return
        query = node.designator.query
        reported = (
            query.from_world() if node.status is LifeCycleValues.SUCCEEDED else []
        )
        if node.status is LifeCycleValues.SUCCEEDED:
            self.perceived[node.index] = [
                DesignatorSummary.render(body, object_keys) for body in reported
            ]
        self.images.observe_ended(
            self.identifier(node), query.world, query.robot, reported
        )

    def running(self) -> Optional[RunningAction]:
        """
        :return: The plan's deepest running action, or None between actions.
        """
        root = self.root()
        if root is None:
            return None
        running = [
            node
            for node in [root] + root.descendants
            if isinstance(node, ActionNode) and node.status is LifeCycleValues.RUNNING
        ]
        if not running:
            return None
        deepest = max(running, key=lambda node: len(node.path))
        return RunningAction(
            identifier=self.identifier(deepest),
            label=DesignatorSummary(deepest).label(),
        )


@dataclass
class PlanPublisher:
    """
    Publishes the plan being performed, reading each node's status where coraplex keeps
    it, and keeps every plan performed before it.
    """

    performed: List[PerformedPlan] = field(default_factory=list)
    """
    Every plan performed, in the order each first began.
    """

    active_plan: Optional[PerformedPlan] = None
    """
    The plan being performed, the one that began last; None before any began.
    """

    lock: threading.RLock = field(default_factory=threading.RLock)
    """
    Guards :attr:`performed`, :attr:`active_plan` and the snapshots of the plans.
    """

    images: PerceptionImages = field(default_factory=PerceptionImages)
    """
    Takes and keeps the images of every plan's perception steps.
    """

    def begin(self, plan: Plan) -> None:
        """
        :param plan: The plan that starts performing; a plan performed before keeps its
            number and snapshot.
        """
        with self.lock:
            performed = next(
                (entry for entry in self.performed if entry.plan is plan), None
            )
            if performed is None:
                performed = PerformedPlan.of_plan(
                    plan, len(self.performed) + 1, self.images
                )
                self.performed.append(performed)
            self.active_plan = performed

    def observe_started(self, node: PlanNode) -> None:
        """
        :param node: A plan node that started.
        """
        if PerformedPlan.is_perception(node):
            self.images.observe_started()

    def observe_ended(self, node: PlanNode, object_keys: Set[str]) -> None:
        """
        :param node: A plan node that ended.
        :param object_keys: The keys of the published objects.
        """
        with self.lock:
            performed = next(
                (entry for entry in self.performed if entry.plan is node.plan), None
            )
        if performed is not None:
            performed.observe_ended(node, object_keys)

    def performed_plans(self) -> List[PerformedPlan]:
        """
        :return: Every plan performed, in the order each first began.
        """
        with self.lock:
            return list(self.performed)

    def refresh(self, object_keys: Set[str], constraints: ConstraintLookup) -> LivePlan:
        """
        Read every node's native status into a new snapshot; a plan whose graph is being
        rebuilt keeps its last snapshot.

        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: The newest snapshot.
        """
        with self.lock:
            active_plan = self.active_plan
        if active_plan is None:
            return self.current()
        snapshot = active_plan.describe(object_keys, constraints)
        if snapshot is None:
            return self.current()
        with self.lock:
            active_plan.latest = snapshot
        return snapshot

    def current(self) -> LivePlan:
        """
        :return: The newest snapshot of the plan being performed.
        """
        with self.lock:
            if self.active_plan is None:
                return LivePlan()
            return self.active_plan.latest

    def published_node(self, identifier: str) -> LivePlanNode:
        """
        :param identifier: The identity of a node of the published plan.
        :return: The node as last published.
        :raises UnknownPlanNode: When the published plan holds no such node.
        """
        for node in self.current().nodes:
            if node.identifier == identifier:
                return node
        raise UnknownPlanNode(identifier)

    def is_executing(self) -> bool:
        """
        :return: Whether the published plan's root is running or paused.
        """
        roots = [node for node in self.current().nodes if node.parent is None]
        return bool(roots) and roots[0].status in (
            PlanNodeStatus.RUNNING,
            PlanNodeStatus.PAUSE,
        )

    def with_constraints(self, constraints: ConstraintLookup) -> LivePlan:
        """
        Publish the last snapshot again with the current constraint monitors, without
        reading the plan, which the thread performing it changes.

        :param constraints: The constraint monitors attached to each node.
        :return: The newest snapshot.
        """
        with self.lock:
            if self.active_plan is None:
                return LivePlan()
            self.active_plan.latest = replace(
                self.active_plan.latest,
                nodes=[
                    replace(node, constraints=constraints(node.identifier))
                    for node in self.active_plan.latest.nodes
                ],
            )
            return self.active_plan.latest

    def running_action(self) -> Optional[str]:
        """
        :return: The label of the deepest running action, or None between actions.
        """
        running = self.running()
        return None if running is None else running.label

    def running(self) -> Optional[RunningAction]:
        """
        :return: The deepest running action of the plan being performed, or None between
            actions.
        """
        with self.lock:
            active_plan = self.active_plan
        return None if active_plan is None else active_plan.running()
