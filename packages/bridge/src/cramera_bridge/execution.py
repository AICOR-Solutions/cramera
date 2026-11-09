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

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType

import mujoco
from typing_extensions import Iterator, Optional, Sequence, Type

from coraplex.plans.executors import (
    KinematicallySimulatedPlanExecutor,
    PhysicallySimulatedPlanExecutor,
    PlanExecutor,
)
from cramera_bridge.exceptions import ExecutionNotRunning
from cramera_protocol.robot_profile import ExecutorKind
from cramph.context import StatechartContext
from cramph.executor import ExecutorExtension
from semantic_digital_twin.adapters.multi_sim import MujocoSim
from semantic_digital_twin.datastructures.definitions import StaticJointState
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.semantic_annotations.mixins import HasGraspCandidates
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import Connection6DoF
from semantic_digital_twin.world_description.contact import ContactParameters

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
    ) -> PlanExecutor:
        """
        :param context: The context of the plan the executor runs; it serves one
            executor.
        :param collision_avoidance: Whether every motion avoids collisions with the
            environment.
        :param extensions: Added to the executor.
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
    ) -> PlanExecutor:
        return KinematicallySimulatedPlanExecutor(
            context,
            collision_avoidance=collision_avoidance,
            extensions=list(extensions),
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
        for robot in world.get_semantic_annotations_by_type(AbstractRobot):
            for arm in robot.all_arms:
                if arm.has_joint_state_of_type(self.starting_posture):
                    arm.get_joint_state_by_type(self.starting_posture).apply_to(world)
        world.notify_state_change()
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
        )


EXECUTIONS: MappingProxyType[ExecutorKind, Type[PlanExecution]] = MappingProxyType(
    {
        ExecutorKind.KINEMATIC: KinematicExecution,
        ExecutorKind.PHYSICS: PhysicalExecution,
    }
)
"""
The execution of each executor kind.
"""
