"""
Moving a robot's hand from the viewer while no plan moves the robot.

A driver thread servos each commanded arm's tool frame towards its target: every tick it
moves the target a bounded step from where the tool is, solves the inverse kinematics of
that near pose and writes the joint values. A target the arm cannot reach leaves the arm
where it is for that tick.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy
from typing_extensions import TYPE_CHECKING, Dict, List, Optional, Tuple

from cramera_cram.exceptions import (
    TeleoperationStillRunning,
    TeleoperationUnavailable,
)
from cramera_cram.geometry import NumericPose
from cramera_cram.live.activity import SimulationActivity
from cramera_cram.robots import RobotParts
from cramera_protocol.live_messages import TeleoperationRequest
from semantic_digital_twin.datastructures.definitions import GripperState
from semantic_digital_twin.spatial_computations.ik_solver import IKSolverException
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix

if TYPE_CHECKING:
    from semantic_digital_twin.robots.robot_parts import AbstractRobot, Arm
    from semantic_digital_twin.world import World
    from semantic_digital_twin.world_description.connections import (
        ActiveConnection1DOF,
    )

TICKS_PER_SECOND = 30.0
"""
How often the driver servos the arms.
"""

MAXIMUM_STEP_METRES = 0.03
"""
How far a tool frame moves per tick: near enough for each solve to converge, about one
metre per second at :data:`TICKS_PER_SECOND`.
"""

WORKSPACE_HALF_EXTENT_METRES = 0.2
"""
How far a target may lie from where the tool frame stood when hand control started,
along each axis of the arm's root frame; the request's coordinates from -1 to 1 span
this box.
"""

INVERSE_KINEMATICS_ITERATIONS = 60
"""
The iterations one solve may take; a near step converges in far fewer.
"""

STOP_TIMEOUT_SECONDS = 2.0
"""
How long stopping waits for the driver thread.
"""

# %% one arm


@dataclass
class ServoedArm:
    """
    One arm under hand control: its chain, the box its targets span and its gripper.
    """

    world: World
    """
    The world.
    """

    arm: Arm
    """
    The arm's annotation.
    """

    centre: numpy.ndarray = field(init=False)
    """
    Where the tool frame stood in the arm's root frame when hand control started.
    """

    orientation: Tuple[float, float, float, float] = field(init=False)
    """
    The tool frame's orientation then, held while the hand moves.
    """

    def __post_init__(self) -> None:
        pose = self.tool_pose()
        self.centre = numpy.asarray(pose.position)
        self.orientation = pose.quaternion

    def tool_pose(self) -> NumericPose:
        """
        :return: The tool frame's pose in the arm's root frame.
        """
        return NumericPose.of_matrix(
            self.world.compute_forward_kinematics_np(
                self.arm.root, self.arm.end_effector.tool_frame
            )
        )

    def step_towards(self, request: TeleoperationRequest) -> bool:
        """
        Move the tool frame one bounded step towards the request's target.

        :param request: The newest target of the arm.
        :return: Whether joint values were written.
        """
        goal = self.centre + numpy.asarray(request.position.to_json()) * (
            WORKSPACE_HALF_EXTENT_METRES
        )
        current = numpy.asarray(self.tool_pose().position)
        step = goal - current
        distance = float(numpy.linalg.norm(step))
        if distance > MAXIMUM_STEP_METRES:
            step = step / distance * MAXIMUM_STEP_METRES
        stepped = current + step
        target = HomogeneousTransformationMatrix.from_xyz_quaternion(
            *stepped, *self.orientation, reference_frame=self.arm.root
        )
        # an unreachable step is an expected outcome of hand control, which the solver
        # reports only by raising; the arm then keeps its pose for this tick
        try:
            solution = self.world.compute_inverse_kinematics(
                self.arm.root,
                self.arm.end_effector.tool_frame,
                target,
                max_iterations=INVERSE_KINEMATICS_ITERATIONS,
            )
        except IKSolverException:
            return False
        for degree_of_freedom, value in solution.items():
            self.world.state[degree_of_freedom.id].position = value
        return True

    def open_gripper(self, opening: float) -> bool:
        """
        :param opening: How far the gripper opens, from 0 closed to 1 open.
        :return: Whether the end effector defines open and closed joint states, and so
            whether joint values were written.
        """
        end_effector = self.arm.end_effector
        if not (
            end_effector.has_joint_state_of_type(GripperState.OPEN)
            and end_effector.has_joint_state_of_type(GripperState.CLOSE)
        ):
            return False
        opened = end_effector.get_joint_state_by_type(GripperState.OPEN)
        closed = end_effector.get_joint_state_by_type(GripperState.CLOSE)
        closed_values = self.values_by_connection(
            closed.connections, closed.target_values
        )
        for connection, open_value in zip(opened.connections, opened.target_values):
            closed_value = closed_values.get(str(connection.name), open_value)
            connection.position = closed_value + opening * (open_value - closed_value)
        return True

    @staticmethod
    def values_by_connection(
        connections: List[ActiveConnection1DOF], values: List[float]
    ) -> Dict[str, float]:
        """
        :param connections: The connections of a joint state.
        :param values: Their target values.
        :return: The target values by connection name.
        """
        return {
            str(connection.name): value
            for connection, value in zip(connections, values)
        }


# %% driver


@dataclass
class TeleoperationDriver:
    """
    Servos the arms of one robot towards the newest targets on a thread it owns.
    """

    world: World
    """
    The world.
    """

    robot: AbstractRobot
    """
    The robot whose arms are moved.
    """

    activity: SimulationActivity
    """
    Tells whether a plan moves the robot, in which case the driver stands aside.
    """

    targets: Dict[str, TeleoperationRequest] = field(default_factory=dict, init=False)
    """
    The newest target per arm name.
    """

    arms: Dict[str, ServoedArm] = field(default_factory=dict, init=False)
    """
    The arms under hand control by name.
    """

    thread: Optional[threading.Thread] = field(default=None, init=False)
    """
    The driver thread while it runs.
    """

    stopping: threading.Event = field(default_factory=threading.Event, init=False)
    """
    Set when the driver thread is to end.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Guards :attr:`targets`, :attr:`arms` and :attr:`thread`.
    """

    def submit(self, request: TeleoperationRequest) -> None:
        """
        Take the newest target of an arm and run the driver.

        :param request: The target.
        :raises UnknownArm: When the robot has no arm of the request's name.
        :raises TeleoperationUnavailable: While a plan moves the robot.
        """
        if self.activity.is_busy():
            raise TeleoperationUnavailable("a plan is moving the robot")
        arm = RobotParts(self.world, self.robot).arm_named(request.arm)
        with self.lock:
            if request.arm not in self.arms:
                self.arms[request.arm] = ServoedArm(self.world, arm)
            self.targets[request.arm] = request
            if self.thread is None:
                self.stopping.clear()
                self.thread = threading.Thread(
                    target=self.run, name="cramera-teleoperation", daemon=True
                )
                self.thread.start()

    def run(self) -> None:
        """
        Servo the arms until the driver stops.
        """
        period = 1.0 / TICKS_PER_SECOND
        while not self.stopping.wait(period):
            if not self.activity.is_busy():
                self.servo()

    def servo(self) -> bool:
        """
        Step every commanded arm towards its target and announce the new state once.

        :return: Whether joint values were written.
        """
        with self.lock:
            commanded = [
                (self.arms[name], request) for name, request in self.targets.items()
            ]
        written = False
        for arm, request in commanded:
            if request.gripper is not None:
                written = arm.open_gripper(request.gripper) or written
            written = arm.step_towards(request) or written
        if written:
            self.world.notify_state_change()
        return written

    def stop(self) -> None:
        """
        Stop the driver; the arms keep their poses.

        :raises TeleoperationStillRunning: When the thread does not end in time.
        """
        self.stopping.set()
        with self.lock:
            thread, self.thread = self.thread, None
            self.targets.clear()
            self.arms.clear()
        if thread is None or thread is threading.current_thread():
            return
        thread.join(timeout=STOP_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise TeleoperationStillRunning()
