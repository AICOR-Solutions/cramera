"""
How a plan's motions are executed: kinematically simulated, or against a physics
simulation of the world in MuJoCo.

A generated plan demo runs the same plan whichever way it is executed; only the
execution differs, as the plan builder's run mode and the robot profile choose it by an
:class:`~cramera_protocol.robot_profile.ExecutorKind`. An execution sets the world up
for its kind while the plans run, and gives each plan the executor that runs it.

Executing on the real robot is another kind of execution: a subclass whose
:meth:`PlanExecution.executor` returns coraplex's
:class:`~coraplex.plans.executors.RealRobotPlanExecutor`, registered in
:data:`EXECUTIONS` under the executor kind a robot profile names for its real runs.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from threading import Thread
from types import MappingProxyType

import mujoco
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from typing_extensions import Iterator, Optional, Sequence, Type

from coraplex.plans.executors import (
    KinematicallySimulatedPlanExecutor,
    PhysicallySimulatedPlanExecutor,
    PlanExecutor,
)
from coraplex.robot_plans.plan_transformations import (
    DetectWithRoboKudo,
    LetContactCarryTheBodies,
    MoveStraightNearTheObject,
)
from cramera_bridge.exceptions import ExecutionNotRunning, PerceptionEngineNotNamed
from cramera_protocol.robot_profile import ExecutorKind
from cramph.context import StatechartContext
from cramph.executor import ExecutorExtension
from giskardpy.motion_statechart.monitors.safety_monitors import SafetyEnvelope
from robokudo.defs import PACKAGE_NAME
from robokudo.query_service import QueryService
from robokudo.utils.module_loader import ModuleLoader
from semantic_digital_twin.adapters.multi_sim import MujocoSim
from semantic_digital_twin.datastructures.definitions import StaticJointState
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.semantic_annotations.mixins import HasGraspCandidates
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import Connection6DoF
from semantic_digital_twin.world_description.contact import ContactParameters

PERCEPTION_ENGINE_VARIABLE = "CRAMERA_PERCEPTION_ENGINE"
"""
The environment variable naming the RoboKudo analysis engine a perceiving execution
perceives with.
"""

PERCEIVING_NODE_NAME = "cramera_perception_client"
"""
The name of the node a perceiving execution's plans reach RoboKudo through.
"""

# %% starting posture


@dataclass(frozen=True)
class StartingPosture:
    """
    The posture the arms of every robot of a world start a run in.
    """

    posture: StaticJointState = StaticJointState.PARK
    """
    The posture, applied to every arm that has one.
    """

    def apply(self, world: World) -> None:
        """
        :param world: The world before the run starts, its arms put in :attr:`posture`.
        """
        for robot in world.get_semantic_annotations_by_type(AbstractRobot):
            for arm in robot.all_arms:
                if arm.has_joint_state_of_type(self.posture):
                    arm.get_joint_state_by_type(self.posture).apply_to(world)
        world.notify_state_change()


# %% execution


@dataclass
class PlanExecution(ABC):
    """
    One way of executing the motions of a task's plans.
    """

    @classmethod
    def of_kind(cls, kind: ExecutorKind) -> PlanExecution:
        """
        :param kind: How the plans are to be executed.
        :return: A new execution of that kind with its default settings.
        """
        return EXECUTIONS[kind]()

    @contextmanager
    def running(self, world: World) -> Iterator[None]:
        """
        Set the world up for this execution while the block performs the task's plans.

        :param world: The world the plans are performed in.
        """
        yield

    @abstractmethod
    def executor(
        self,
        context: StatechartContext,
        collision_avoidance: bool,
        extensions: Sequence[ExecutorExtension],
        safety: SafetyEnvelope,
    ) -> PlanExecutor:
        """
        :param context: The context of the plan the executor runs; it serves one
            executor.
        :param collision_avoidance: Whether every motion avoids collisions with the
            environment.
        :param extensions: Added to the executor.
        :param safety: The safety constraints every motion of the plan is held to.
        :return: A new executor running one plan, inside :meth:`running`.
        """


@dataclass
class KinematicExecution(PlanExecution):
    """
    Moves the world kinematically, as fast as the controller computes the motions.
    """

    def executor(
        self,
        context: StatechartContext,
        collision_avoidance: bool,
        extensions: Sequence[ExecutorExtension],
        safety: SafetyEnvelope,
    ) -> PlanExecutor:
        return KinematicallySimulatedPlanExecutor(
            context,
            collision_avoidance=collision_avoidance,
            extensions=list(extensions),
            safety=safety,
        )


@dataclass
class PhysicalExecution(PlanExecution):
    """
    Runs the motions against MuJoCo physics, stepped from the control loop, as the
    MuJoCo runner of coraplex's Tracy demos does: the servos take every command as their
    set point, and an object is held by friction alone.

    The world is published to the viewer rather than shown in a MuJoCo window.
    """

    starting_posture: StaticJointState = StaticJointState.PARK
    """
    The posture every arm starts the run in.

    A robot's description leaves its arms where the servos cannot carry them out of,
    such as stretched through its own table.
    """

    step_size: float = 1e-3
    """
    How long one physics step lasts, in seconds.
    """

    friction_cone: mujoco.mjtCone = mujoco.mjtCone.mjCONE_ELLIPTIC
    """
    The friction cone of the contacts: the exact elliptic one, where the default pyramid
    lets a squeezed object creep between the pads.
    """

    impedance_ratio: float = 10.0
    """
    How much harder sliding is than pressing in, as MuJoCo advises for grasping with an
    elliptic cone.
    """

    no_slip_iterations: int = 10
    """
    Passes spent removing the slip soft contacts leave, so a held object stays where the
    pads hold it.
    """

    settling_duration: timedelta = field(default_factory=lambda: timedelta(seconds=0.5))
    """
    How long the objects are left to come to rest before the first plan runs.
    """

    headless: bool = True
    """
    Whether the physics runs without a MuJoCo window of its own.
    """

    simulation: Optional[MujocoSim] = field(default=None, init=False)
    """
    The running physics while plans are performed, else None.
    """

    @contextmanager
    def running(self, world: World) -> Iterator[None]:
        """
        Put the arms in their starting posture, let the free objects be held by
        friction, start the physics and let the objects settle; stop it when the block
        ends.

        :param world: The world the plans are performed in.
        """
        self.prepare(world)
        simulation = MujocoSim(
            world=world,
            headless=self.headless,
            step_size=self.step_size,
            cone=self.friction_cone,
            impratio=self.impedance_ratio,
            noslip_iterations=self.no_slip_iterations,
        )
        simulation.start_stepped_simulation()
        self.simulation = simulation
        try:
            simulation.step_simulation(self.settling_duration)
            yield
        finally:
            self.simulation = None
            simulation.stop_simulation()

    def prepare(self, world: World) -> None:
        """
        Put every arm of every robot in :attr:`starting_posture`, where it has one, and
        give every free graspable object the contact a gripper holds by friction, unless
        its geometry declares its own.

        :param world: The world before the physics starts.
        """
        StartingPosture(self.starting_posture).apply(world)
        ContactParameters.create_for_grasped_object().apply_to(
            graspable.root
            for graspable in world.get_semantic_annotations_by_type(HasGraspCandidates)
            if isinstance(graspable.root.parent_connection, Connection6DoF)
        )

    def executor(
        self,
        context: StatechartContext,
        collision_avoidance: bool,
        extensions: Sequence[ExecutorExtension],
        safety: SafetyEnvelope,
    ) -> PlanExecutor:
        """
        :raises ExecutionNotRunning: Outside :meth:`running`, where no physics runs.
        """
        if self.simulation is None:
            raise ExecutionNotRunning(ExecutorKind.PHYSICS)
        return PhysicallySimulatedPlanExecutor(
            context,
            simulation=self.simulation,
            collision_avoidance=collision_avoidance,
            extensions=list(extensions),
            safety=safety,
        )


@dataclass
class PerceivingPhysicalExecution(PhysicalExecution):
    """
    Runs the motions in physics as :class:`PhysicalExecution` does, and answers the
    plans' detections the way the real robot does: a RoboKudo analysis engine looks
    through the robot's camera, rendered from the simulated world, over RoboKudo's query
    action.
    """

    analysis_engine: str = field(
        default_factory=lambda: os.environ.get(PERCEPTION_ENGINE_VARIABLE, "")
    )
    """
    The module of RoboKudo's analysis engines that perceives, such as ``tracy_cubes``.
    """

    ros_node: Optional[Node] = field(default=None, init=False)
    """
    The node the plans reach RoboKudo through while plans are performed, else None.
    """

    @contextmanager
    def running(self, world: World) -> Iterator[None]:
        """
        Differs from :meth:`PhysicalExecution.running` in also answering RoboKudo's
        query action from the analysis engine while the block runs.

        :raises PerceptionEngineNotNamed: When no analysis engine is named.
        """
        if not self.analysis_engine:
            raise PerceptionEngineNotNamed(PERCEPTION_ENGINE_VARIABLE)
        with super().running(world), ExitStack() as perceiving:
            if not rclpy.ok():
                rclpy.init()
                perceiving.callback(rclpy.try_shutdown)
            service = QueryService(
                analysis_engine=ModuleLoader().load_ae(
                    ros_pkg_name=PACKAGE_NAME, module_name=self.analysis_engine
                ),
                world=world,
            )
            service.start()
            perceiving.callback(service.stop)
            node = rclpy.create_node(PERCEIVING_NODE_NAME)
            perceiving.callback(node.destroy_node)
            spinner = SingleThreadedExecutor()
            spinner.add_node(node)
            Thread(target=spinner.spin, daemon=True, name=PERCEIVING_NODE_NAME).start()
            perceiving.callback(spinner.shutdown)
            self.ros_node = node
            perceiving.callback(setattr, self, "ros_node", None)
            yield

    def executor(
        self,
        context: StatechartContext,
        collision_avoidance: bool,
        extensions: Sequence[ExecutorExtension],
        safety: SafetyEnvelope,
    ) -> PlanExecutor:
        """
        Differs from :meth:`PhysicalExecution.executor` in answering every detection
        of the plan with RoboKudo.
        """
        if self.simulation is None or self.ros_node is None:
            raise ExecutionNotRunning(ExecutorKind.PERCEIVED_PHYSICS)
        return PhysicallySimulatedPlanExecutor(
            context,
            simulation=self.simulation,
            collision_avoidance=collision_avoidance,
            extensions=list(extensions),
            safety=safety,
            ros_node=self.ros_node,
            plan_adaptations=[
                MoveStraightNearTheObject(),
                LetContactCarryTheBodies(),
                DetectWithRoboKudo(),
            ],
        )


EXECUTIONS: MappingProxyType[ExecutorKind, Type[PlanExecution]] = MappingProxyType(
    {
        ExecutorKind.KINEMATIC: KinematicExecution,
        ExecutorKind.PHYSICS: PhysicalExecution,
        ExecutorKind.PERCEIVED_PHYSICS: PerceivingPhysicalExecution,
    }
)
"""
The execution of each executor kind.
"""
