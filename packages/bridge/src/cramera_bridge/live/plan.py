"""
The executing plan as the viewer shows it: every node with its native status.

A plan runs as one cramph statechart, whose actions, composites and statements hold the
motions they expand into. The plan shows the plan's own nodes down to each motion; what
a motion is made of is the statechart's to show.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum, StrEnum

from typing_extensions import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple

from cramera_bridge.exceptions import UnknownPlanNode
from cramera_bridge.names import plan_node_kind
from cramera_bridge.live.perception_images import PerceptionImages
from cramera_bridge.live.recording import RunningAction
from cramera_bridge.live.world_model import ObjectKey
from cramera_bridge.robots import RobotRoster
from cramera_protocol.live_messages import ConstraintObservation, LivePlan, LivePlanNode
from coraplex.perception import PerceptionTask
from coraplex.plans.context_extensions import RobotAccess
from coraplex.robot_plans.actions.base import Action
from cramph.composites import StatementNode
from cramph.data_types import LifeCycleValues
from cramph.node import CompositeNode, StatechartNode
from giskardpy.motion_statechart.graph_node import MotionStatechartNode
from krrood.entity_query_language.core.variable import Variable
from krrood.entity_query_language.query.match import Match
from semantic_digital_twin.robots.robot_parts import Arm
from krrood_spatial_math.spatial_types import Pose
from semantic_digital_twin.world_description.world_entity import (
    Body,
    SemanticAnnotation,
)

if TYPE_CHECKING:
    from coraplex.plans.executors import PlanExecutor
    from cramph.statechart import Statechart

PLAN_NODE_PREFIX = "plan_node_"
"""
The start of the identity of every node of the first plan performed; the rest is the
node's index in the plan's statechart.
"""

LATER_PLAN_NODE_PREFIX = "plan_{number}_node_"
"""
The start of the identity of every node of a later plan, naming the plan's number; the
rest is the node's index in the plan's statechart.
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

MATCH_SEPARATOR = ": "
"""
Separates the class a match matches from what it states about the class's fields.
"""

OPEN_VALUE = "any"
"""
Precedes the type of a value a designator leaves open, to be found when it runs.
"""


class PlanNodeStatus(StrEnum):
    """
    The status of a plan node as the viewer and the recorded bundles name it, which
    keeps the names coraplex used before its nodes took the statechart's life cycle
    values.
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


FINISHED_LIFE_CYCLES = (
    LifeCycleValues.SUCCEEDED,
    LifeCycleValues.FAILED,
    LifeCycleValues.INTERRUPTED,
)
"""
The life cycle values of a node that ended.
"""

# %% designators


NODE_BASES = (StatechartNode, CompositeNode, MotionStatechartNode)
"""
The node classes whose fields run a node rather than describe what it does.
"""


@dataclass(frozen=True)
class DesignatorSummary:
    """
    The arm and the body a plan node is described by, and every parameter it holds
    rendered for reading: an action's parameters, what a statement states, and the fields
    a motion or another node is given.
    """

    node: StatechartNode
    """
    The plan node.
    """

    def described_by(self) -> Dict[str, object]:
        """
        :return: The parameters the node is described by, by name: an action's
            designator parameters, the fields a statement states, and else the fields
            its class adds to the node classes.
        """
        if isinstance(self.node, Action):
            return dict(self.node.designator_parameter)
        if isinstance(self.node, StatementNode):
            return dict(self.node.statement._kwargs_)
        running = {each.name for base in NODE_BASES for each in fields(base)}
        return {
            each.name: getattr(self.node, each.name)
            for each in fields(self.node)
            if each.init and each.name not in running and not each.name.startswith("_")
        }

    def values(self) -> List[object]:
        """
        :return: The values of the parameters the node is described by.
        """
        return list(self.described_by().values())

    def arm(self) -> Optional[str]:
        """
        :return: The name of the first arm the node names, on its own or among several
            arms.
        """
        for value in self.values():
            for candidate in value if isinstance(value, (list, tuple)) else [value]:
                if isinstance(candidate, Arm):
                    return str(candidate.name)
        return None

    def target(self, object_keys: Set[str]) -> Optional[str]:
        """
        :param object_keys: The keys of the published objects.
        :return: The key of the first published object the node names, else the name of
            the first body it names.
        """
        bodies = [value for value in self.values() if isinstance(value, Body)]
        for body in bodies:
            if ObjectKey.of(body) in object_keys:
                return ObjectKey.of(body)
        return next((str(body.name) for body in bodies), None)

    def label(self) -> str:
        """
        :return: The class name of the node, or of the action a statement describes.
        """
        if isinstance(self.node, StatementNode):
            return self.node.statement._type_.__name__
        return type(self.node).__name__

    def parameters(self, object_keys: Set[str]) -> Dict[str, str]:
        """
        :param object_keys: The keys of the published objects.
        :return: Every parameter of the node that holds a value, by name, rendered as
            the viewer shows it.
        """
        return {
            name: self.render(value, object_keys)
            for name, value in self.described_by().items()
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
    def render_match(cls, match: Match, object_keys: Set[str], nested: bool) -> str:
        """
        :param match: A description of a designator, such as a sub-action a composite
            action leaves to be found.
        :param object_keys: The keys of the published objects.
        :param nested: Whether the match sits in a description nested in the
            designator; a nested match is named by the class it matches.
        :return: The class the match matches, followed by what it states about each
            field when it sits in the designator itself.
        """
        name = match._type_.__name__
        if nested or not match._kwargs_:
            return name
        stated = PARAMETER_SEPARATOR.join(
            f"{field_name} {cls.render(inner, object_keys, nested=True)}"
            for field_name, inner in match._kwargs_.items()
        )
        return f"{name}{MATCH_SEPARATOR}{stated}"

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
        if isinstance(value, Match):
            return cls.render_match(value, object_keys, nested)
        if isinstance(value, Variable):
            return f"{OPEN_VALUE} {value}"
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


def is_plan_node(node: StatechartNode) -> bool:
    """
    :param node: A node below a plan's top-level nodes.
    :return: Whether the plan shows it: every node not inside a motion, so a motion is
        shown and not what it is made of.
    """
    parent = node.parent_node
    while parent is not None:
        if isinstance(parent, MotionStatechartNode):
            return False
        parent = parent.parent_node
    return True


@dataclass
class PerformedPlan:
    """
    A plan performed while the publisher ran, with the robot that performed it and its
    newest snapshot.
    """

    statechart: Statechart
    """
    The statechart the plan runs as.
    """

    plan_nodes: List[StatechartNode]
    """
    The plan's top-level nodes, without what the executor added to run them, such as the
    end of the plan or its stall detection.
    """

    number: int
    """
    The plan's position among the plans performed, counted from one.
    """

    robot: Optional[str]
    """
    The display name of the robot that performed the plan, or None for a plan whose
    context names no robot.
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
    def of_executor(
        cls, executor: PlanExecutor, number: int, images: PerceptionImages
    ) -> PerformedPlan:
        """
        :param executor: The executor that compiled the plan.
        :param number: The plan's position among the plans performed, counted from one.
        :param images: Takes and keeps the images of its perception steps.
        :return: The plan the executor runs, with the robot its context names.
        """
        access = executor.context.get_extension(RobotAccess)
        return cls(
            statechart=executor.statechart,
            plan_nodes=list(executor.plan_nodes),
            number=number,
            robot=None if access is None else RobotRoster.label(access.robot),
            images=images,
        )

    def identifier(self, node: StatechartNode) -> str:
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

    def nodes(self) -> List[StatechartNode]:
        """
        :return: The nodes the plan shows, each top-level node followed by the nodes
            below it.
        """
        return [
            node
            for top in self.plan_nodes
            for node in [top, *top.descendants]
            if is_plan_node(node)
        ]

    def describe(
        self, object_keys: Set[str], constraints: ConstraintLookup
    ) -> LivePlan:
        """
        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: A snapshot of every node the plan shows with its native status.
        """
        nodes = [
            self.node_description(node, object_keys, constraints)
            for node in self.nodes()
        ]
        return LivePlan(
            signature=SIGNATURE_SEPARATOR.join(node.identifier for node in nodes),
            nodes=nodes,
        )

    def node_description(
        self,
        node: StatechartNode,
        object_keys: Set[str],
        constraints: ConstraintLookup,
    ) -> LivePlanNode:
        """
        :param node: A node of the plan.
        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: The node with its native status; a top-level node has no parent.
        """
        summary = DesignatorSummary(node)
        identifier = self.identifier(node)
        parent = None if node in self.plan_nodes else node.parent_node
        return LivePlanNode(
            identifier=identifier,
            parent=None if parent is None else self.identifier(parent),
            kind=plan_node_kind(node),
            label=summary.label(),
            status=PlanNodeStatus.of(node.life_cycle_state),
            arm=summary.arm(),
            target=summary.target(object_keys),
            constraints=constraints(identifier),
            parameters=summary.parameters(object_keys),
            perceived=(
                list(self.perceived.get(node.index, []))
                if self.is_perception(node)
                else None
            ),
            reason=self.reason(node),
            images=(
                [image.document(image.key) for image in self.images.of_step(identifier)]
                if self.is_perception(node)
                else None
            ),
        )

    @staticmethod
    def reason(node: StatechartNode) -> Optional[str]:
        """
        :param node: A node of the plan.
        :return: Why a node choosing its child gave up on its children: the names of the
            monitors that failed them; None for any other node.
        """
        if not isinstance(node, StatementNode) or not node.failure_reasons:
            return None
        return PARAMETER_SEPARATOR.join(
            str(monitor.name) for monitor in node.failure_reasons
        )

    @staticmethod
    def is_perception(node: StatechartNode) -> bool:
        """
        :param node: A node of the plan.
        :return: Whether it is a perception step: the node that answers a perception
            query.
        """
        return isinstance(node, PerceptionTask)

    def observe_ended(self, node: StatechartNode, object_keys: Set[str]) -> None:
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
        query = node.query
        succeeded = node.life_cycle_state is LifeCycleValues.SUCCEEDED
        reported = query.from_world() if succeeded else []
        if succeeded:
            self.perceived[node.index] = [
                DesignatorSummary.render(body, object_keys) for body in reported
            ]
        self.images.observe_ended(
            self.identifier(node), query.world, query.robot, reported
        )

    def has_ended(self) -> bool:
        """
        :return: Whether every top-level node of the plan ended.
        """
        return all(
            node.life_cycle_state in FINISHED_LIFE_CYCLES for node in self.plan_nodes
        )

    def running(self) -> Optional[RunningAction]:
        """
        :return: The plan's deepest running action, or None between actions.
        """
        running = [
            node
            for node in self.nodes()
            if isinstance(node, Action)
            and node.life_cycle_state is LifeCycleValues.RUNNING
        ]
        if not running:
            return None
        deepest = max(running, key=lambda node: node.depth)
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

    def begin(self, executor: PlanExecutor) -> None:
        """
        :param executor: The executor that compiled the plan which starts performing; a
            plan performed before keeps its number and snapshot.
        """
        with self.lock:
            performed = next(
                (
                    entry
                    for entry in self.performed
                    if entry.statechart is executor.statechart
                ),
                None,
            )
            if performed is None:
                performed = PerformedPlan.of_executor(
                    executor, len(self.performed) + 1, self.images
                )
                self.performed.append(performed)
            self.active_plan = performed

    def observe_started(self, node: StatechartNode) -> None:
        """
        :param node: A plan node that started.
        """
        if PerformedPlan.is_perception(node):
            self.images.observe_started()

    def observe_ended(self, node: StatechartNode, object_keys: Set[str]) -> None:
        """
        :param node: A plan node that ended.
        :param object_keys: The keys of the published objects.
        """
        with self.lock:
            performed = next(
                (
                    entry
                    for entry in self.performed
                    if entry.statechart is node.statechart
                ),
                None,
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
        Read every node's native status into a new snapshot.

        :param object_keys: The keys of the published objects.
        :param constraints: The constraint monitors attached to each node.
        :return: The newest snapshot.
        """
        with self.lock:
            active_plan = self.active_plan
        if active_plan is None:
            return self.current()
        snapshot = active_plan.describe(object_keys, constraints)
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
        :return: Whether a top-level node of the published plan is running or paused.
        """
        return any(
            node.parent is None
            and node.status in (PlanNodeStatus.RUNNING, PlanNodeStatus.PAUSE)
            for node in self.current().nodes
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
