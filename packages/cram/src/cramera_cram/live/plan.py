"""
The executing plan as the viewer shows it: every node with its native status.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace

from typing_extensions import TYPE_CHECKING, Callable, List, Optional, Set

from cramera_cram.exceptions import UnknownPlanNode
from cramera_cram.live.recording import RunningAction
from cramera_cram.live.world_model import ObjectKey
from cramera_cram.robots import RobotRoster
from cramera_protocol.live_messages import ConstraintObservation, LivePlan, LivePlanNode
from coraplex.datastructures.enums import Arms, TaskStatus
from coraplex.plans.plan_node import ActionNode, DesignatorNode, PlanNode
from semantic_digital_twin.world_description.world_entity import Body

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

# %% designators


@dataclass(frozen=True)
class DesignatorSummary:
    """
    The arm and the body a node's designator names.
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
        :return: The name of the first arm the designator names.
        """
        return next(
            (value.name for value in self.values() if isinstance(value, Arms)), None
        )

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

    @classmethod
    def of_plan(cls, plan: Plan, number: int) -> PerformedPlan:
        """
        :param plan: A plan that starts performing.
        :param number: Its position among the plans performed, counted from one.
        :return: The plan with the robot its context names.
        """
        robot = None if plan.context is None else plan.context.robot
        return cls(
            plan=plan,
            number=number,
            robot=None if robot is None else RobotRoster.label(robot),
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
            status=node.status.name,
            arm=summary.arm(),
            target=summary.target(object_keys),
            constraints=constraints(identifier),
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
            if isinstance(node, ActionNode) and node.status is TaskStatus.RUNNING
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
                performed = PerformedPlan.of_plan(plan, len(self.performed) + 1)
                self.performed.append(performed)
            self.active_plan = performed

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
            TaskStatus.RUNNING.name,
            TaskStatus.PAUSE.name,
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
