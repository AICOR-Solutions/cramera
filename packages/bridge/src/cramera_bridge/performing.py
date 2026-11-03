"""
Performing a plan: the world and the robot a task is performed with, and running one
plan node in a statechart of its own.

coraplex runs a plan as the top-level node of a cramph statechart, compiled and executed
by a plan executor whose context gives the nodes the robot and how statements are
grounded. A context serves one executor, so every plan performed gets a context of its
own, made from the :class:`TaskContext` it was built with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import List, Optional, Sequence, Type

from coraplex.plans.context_extensions import RobotAccess, StatementGrounding
from coraplex.plans.executors import (
    KinematicallySimulatedPlanExecutor,
    PlanExecutor,
)
from cramph.context import ContextExtension, StatechartContext
from cramph.executor import ExecutorExtension
from cramph.node import StatechartNode
from cramph.statechart import Statechart
from krrood.entity_query_language.backends import (
    EntityQueryLanguageGenerativeBackend,
    QueryBackend,
)
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.world import World

# %% context


@dataclass
class TaskContext:
    """
    The world and the robot a task is performed with, and the backend grounding the
    parts its plans leave open.
    """

    world: World
    """
    The world the task is performed in.
    """

    robot: AbstractRobot
    """
    The robot performing the task.
    """

    query_backend: QueryBackend = field(
        default_factory=EntityQueryLanguageGenerativeBackend
    )
    """
    Grounds the statements of the task's plans, as coraplex does by default.
    """

    extensions: List[ContextExtension] = field(default_factory=list)
    """
    Further context extensions every plan of the task runs with.
    """

    def statechart_context(self) -> StatechartContext:
        """
        :return: A new context of a statechart performing one plan of the task: its
            robot, how its statements are grounded and :attr:`extensions`.
        """
        return StatechartContext.with_extensions(
            self.world,
            [
                RobotAccess(self.robot),
                StatementGrounding(query_backend=self.query_backend),
                *self.extensions,
            ],
        )


# %% performing


@dataclass
class PlanPerformance:
    """
    How the plans of a task are performed: by which executor, with which settings and
    which further executor extensions.
    """

    executor_type: Type[PlanExecutor] = KinematicallySimulatedPlanExecutor
    """
    The executor running each plan, which decides how its motions are executed.
    """

    collision_avoidance: bool = False
    """
    Whether every motion avoids collisions with the environment.
    """

    extensions: Sequence[ExecutorExtension] = ()
    """
    Added to every executor, such as the extension publishing its plan.
    """

    def executor(
        self,
        context: TaskContext,
        extensions: Sequence[ExecutorExtension] = (),
    ) -> PlanExecutor:
        """
        :param context: The world and the robot the plan is performed with.
        :param extensions: Added to the executor after :attr:`extensions`.
        :return: A new executor with a context of its own.
        """
        return self.executor_type(
            context.statechart_context(),
            collision_avoidance=self.collision_avoidance,
            extensions=[*self.extensions, *extensions],
        )

    def perform(
        self,
        plan: StatechartNode,
        context: TaskContext,
        extensions: Sequence[ExecutorExtension] = (),
    ) -> PlanExecutor:
        """
        Perform a plan in a statechart of its own until it ended.

        :param plan: The plan's top-level node.
        :param context: The world and the robot the plan is performed with.
        :param extensions: Added to the executor after :attr:`extensions`.
        :return: The executor that ran the plan, holding its statechart.
        :raises MotionDidNotFinish: If the plan did not succeed, or another
            :class:`~coraplex.plans.failures.PlanFailure`.
        """
        executor = self.executor(context, extensions)
        statechart = Statechart(context=executor.context)
        statechart.add_node(plan)
        try:
            executor.compile(statechart)
            executor.execute()
        finally:
            executor.close()
        return executor


def perform(
    plan: StatechartNode,
    context: TaskContext,
    performance: Optional[PlanPerformance] = None,
) -> PlanExecutor:
    """
    Perform a plan kinematically simulated, or as a performance says.

    :param plan: The plan's top-level node.
    :param context: The world and the robot the plan is performed with.
    :param performance: How the plan is performed; kinematically simulated without
        collision avoidance when None.
    :return: The executor that ran the plan.
    """
    return (performance or PlanPerformance()).perform(plan, context)
