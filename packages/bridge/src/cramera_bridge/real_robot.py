"""
The real robot a run moves: the Giskard that commands it, the preflight checking that
its drivers are up before a run starts, and reading where it stands.

Run as ``cramera-preflight`` (or ``python -m cramera_bridge.real_robot``), the preflight
prints what a real run would miss and ends with a nonzero status when anything is
missing.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path

from ament_index_python.packages import get_packages_with_prefixes
from control_msgs.action import ParallelGripperCommand
from rclpy.action import ActionClient
from rclpy.action.graph import get_action_names_and_types
from rclpy.node import Node
from sensor_msgs.msg import JointState
from typing_extensions import Callable, Iterator, Mapping, Sequence

from cramera_bridge.exceptions import JointStatesNotReceived
from cramera_bridge.ros_node import SpinningNode
from semantic_digital_twin.robots.tracy import (
    TracyParallelGripperCommandTopic,
    TracyTopic,
)
from semantic_digital_twin.world import World

# %% Giskard


class RealRobotVariable(StrEnum):
    """
    The environment variables a deployment configures its real runs with.
    """

    GISKARD_LAUNCH_FILE = "CRAMERA_GISKARD_LAUNCH_FILE"
    """
    The :class:`GiskardLaunchFile` a real run starts Giskard with; the one commanding
    the real robot when it is not set.
    """


class GiskardLaunchFile(StrEnum):
    """
    The launch files of ``giskardpy_ros`` that bring up a Giskard for Tracy.
    """

    VELOCITY = "giskardpy_tracy_velocity.launch.py"
    """
    A Giskard commanding the velocity controllers of the real Tracy, reading its joint
    states and robot description from its drivers.
    """

    STANDALONE = "giskardpy_tracy_standalone.launch.py"
    """
    A Giskard simulating Tracy's arms instead of commanding them, needing no driver.
    """

    @property
    def commands_the_real_robot(self) -> bool:
        """
        Whether the Giskard it starts moves the real robot, and reads its drivers.
        """
        return self is GiskardLaunchFile.VELOCITY

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> GiskardLaunchFile:
        """
        :param environment: The process environment, which may name the launch file.
        :return: The launch file it names, else :attr:`VELOCITY`.
        """
        return cls(
            environment.get(RealRobotVariable.GISKARD_LAUNCH_FILE, cls.VELOCITY.value)
        )


class ProcessControl(IntEnum):
    """
    The operations of Linux's ``prctl`` a started process is set up with.
    """

    SET_PARENT_DEATH_SIGNAL = 1
    """
    Have the kernel send the process a signal once the process that started it ends.
    """

@dataclass(frozen=True)
class GiskardProcess:
    """
    A Giskard launched as a process group of its own, so that stopping it stops every
    node its launch file started and nothing else; the launch is interrupted as well
    when the process that started it ends without stopping it, such as when killed.
    """

    launch_file: GiskardLaunchFile
    """
    The launch file Giskard is started with.
    """

    package: str = "giskardpy_ros"
    """
    The ROS package holding the launch file.
    """

    stop_timeout: float = 20.0
    """
    How long, in seconds, Giskard may take to end once asked to before it is killed.
    """

    @property
    def is_installed(self) -> bool:
        """
        Whether the ROS workspace holds the launch file.
        """
        prefix = get_packages_with_prefixes().get(self.package)
        return (
            prefix is not None
            and (
                Path(prefix) / "share" / self.package / "launch" / self.launch_file
            ).is_file()
        )

    @contextmanager
    def running(self) -> Iterator[subprocess.Popen]:
        """
        Run Giskard while the block runs, then end it.

        :return: The launch process.
        """
        with ExitStack() as running:
            process = subprocess.Popen(
                ["ros2", "launch", self.package, self.launch_file.value],
                start_new_session=True,
                preexec_fn=self.interruption_with_starting_process(),
            )
            running.callback(self.stop, process)
            yield process

    @staticmethod
    def interruption_with_starting_process() -> Callable[[], None]:
        """
        :return: What the launch process runs before it starts, so that it is
            interrupted once the process starting it ends; looked up beforehand, as
            the forked child must not load libraries while other threads ran.
        """
        process_control = ctypes.CDLL(None).prctl
        return lambda: process_control(
            ProcessControl.SET_PARENT_DEATH_SIGNAL, signal.SIGINT
        )

    def stop(self, process: subprocess.Popen) -> None:
        """
        End the launch's process group, killing it once :attr:`stop_timeout` passed.

        :param process: The launch process.
        """
        if process.poll() is not None:
            return
        os.killpg(process.pid, signal.SIGINT)
        deadline = time.monotonic() + self.stop_timeout
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


# %% preflight


class OrbbecCameraTopic(StrEnum):
    """
    The topics the Orbbec camera's driver publishes the images RoboKudo reads on, as it
    names them by default.
    """

    COLOR = "/camera/color/image_raw"
    DEPTH = "/camera/depth/image_raw"
    COLOR_CAMERA_INFO = "/camera/color/camera_info"


class RequirementKind(StrEnum):
    """
    What a real run needs from the robot's drivers and the ROS workspace.
    """

    GISKARD_LAUNCH_FILE = "Giskard launch file installed"
    """
    The launch file the run starts Giskard with.
    """

    NO_OTHER_GISKARD = "no other Giskard running"
    """
    Nothing serves Giskard's command action yet, as the run's own Giskard is to.
    """

    ROBOT_DESCRIPTION = "robot description published"
    """
    The topic Giskard reads the robot's model from.
    """

    JOINT_STATES = "joint states arriving"
    """
    A topic an arm's driver publishes its joint positions on.
    """

    GRIPPER_ACTION_SERVER = "gripper action server present"
    """
    The action a gripper's driver serves; without it a run waits for it forever.
    """

    CAMERA_TOPIC = "camera topic published"
    """
    A topic RoboKudo reads the camera's images from.
    """

@dataclass(frozen=True)
class PreflightCheck:
    """
    One requirement of a real run, and whether the preflight found it.
    """

    kind: RequirementKind
    """
    What is required.
    """

    name: str
    """
    The topic, action or file required.
    """

    satisfied: bool
    """
    Whether it was found.
    """

    def to_text(self) -> str:
        """
        :return: A line saying whether the requirement was found.
        """
        return f"{'ok' if self.satisfied else 'MISSING'}  {self.kind}: {self.name}"


@dataclass(frozen=True)
class PreflightReport:
    """
    What the preflight found of a real run's requirements.
    """

    checks: list[PreflightCheck]
    """
    Every requirement checked, in the order checked.
    """

    @property
    def missing(self) -> list[PreflightCheck]:
        """
        The requirements not found.
        """
        return [check for check in self.checks if not check.satisfied]

    @property
    def ready(self) -> bool:
        """
        Whether every requirement was found, so a real run can start.
        """
        return not self.missing

    def to_text(self) -> str:
        """
        :return: A line per requirement, then whether a real run can start.
        """
        verdict = (
            "The real robot is ready."
            if self.ready
            else f"The real robot is not ready: {len(self.missing)} missing."
        )
        return "\n".join([*(check.to_text() for check in self.checks), verdict])


@dataclass(frozen=True)
class RealRobotPreflight:
    """
    Checks that the drivers a real run needs are up, before it starts Giskard; the
    defaults are those of Tracy.
    """

    giskard_launch_file: GiskardLaunchFile = field(
        default_factory=lambda: GiskardLaunchFile.from_environment(os.environ)
    )
    """
    The launch file the run starts Giskard with; one simulating the arms needs no arm
    driver and no camera.
    """

    wait_seconds: float = 2.0
    """
    How long, in seconds, each topic or action is waited for.
    """

    giskard_command_action: str = "/giskard/command"
    """
    The action Giskard is commanded through.
    """

    robot_description_topic: str = "/robot_description"
    """
    The topic Giskard reads the robot's model from.
    """

    joint_state_topics: Sequence[str] = (
        TracyTopic.LEFT_ARM_JOINT_STATES,
        TracyTopic.RIGHT_ARM_JOINT_STATES,
    )
    """
    The topics the arms' drivers publish their joint positions on.
    """

    gripper_action_servers: Sequence[str] = tuple(TracyParallelGripperCommandTopic)
    """
    The actions the grippers' drivers serve.
    """

    camera_topics: Sequence[str] = tuple(OrbbecCameraTopic)
    """
    The topics RoboKudo reads the camera's images from.
    """

    def check(self, node: Node) -> PreflightReport:
        """
        :param node: A spinning node the checks look through.
        :return: Which requirements were found.
        """
        checks = [
            PreflightCheck(
                RequirementKind.GISKARD_LAUNCH_FILE,
                self.giskard_launch_file.value,
                GiskardProcess(self.giskard_launch_file).is_installed,
            ),
            PreflightCheck(
                RequirementKind.NO_OTHER_GISKARD,
                self.giskard_command_action,
                self.giskard_command_action
                not in dict(get_action_names_and_types(node)),
            ),
            *(
                PreflightCheck(
                    RequirementKind.GRIPPER_ACTION_SERVER,
                    server,
                    self.is_gripper_action_served(node, server),
                )
                for server in self.gripper_action_servers
            ),
        ]
        if not self.giskard_launch_file.commands_the_real_robot:
            return PreflightReport(checks)
        received = JointStateMessages(self.joint_state_topics).receive(
            node, self.wait_seconds
        )
        return PreflightReport(
            [
                *checks,
                PreflightCheck(
                    RequirementKind.ROBOT_DESCRIPTION,
                    self.robot_description_topic,
                    node.count_publishers(self.robot_description_topic) > 0,
                ),
                *(
                    PreflightCheck(
                        RequirementKind.JOINT_STATES, topic, topic in received
                    )
                    for topic in self.joint_state_topics
                ),
                *(
                    PreflightCheck(
                        RequirementKind.CAMERA_TOPIC,
                        topic,
                        node.count_publishers(topic) > 0,
                    )
                    for topic in self.camera_topics
                ),
            ]
        )

    def is_gripper_action_served(self, node: Node, server: str) -> bool:
        """
        :param node: A spinning node.
        :param server: The name of a gripper's parallel gripper command action.
        :return: Whether a server of it answered within :attr:`wait_seconds`.
        """
        client = ActionClient(node, ParallelGripperCommand, server)
        served = client.wait_for_server(timeout_sec=self.wait_seconds)
        client.destroy()
        return served


# %% joint states


@dataclass(frozen=True)
class JointStateMessages:
    """
    The latest message of each of the topics the real robot's drivers publish its joint
    positions on.
    """

    topics: Sequence[str]
    """
    The topics.
    """

    def receive(self, node: Node, wait_seconds: float) -> dict[str, JointState]:
        """
        :param node: A spinning node.
        :param wait_seconds: How long, in seconds, to wait for every topic's message.
        :return: The first message of each topic that sent one in time, by topic.
        """
        received: dict[str, JointState] = {}
        complete = threading.Event()

        def keep(topic: str, message: JointState) -> None:
            received.setdefault(topic, message)
            if len(received) == len(self.topics):
                complete.set()

        subscriptions = [
            node.create_subscription(
                JointState, topic, lambda message, topic=topic: keep(topic, message), 1
            )
            for topic in self.topics
        ]
        complete.wait(wait_seconds)
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        return dict(received)


@dataclass(frozen=True)
class ReportedPosture:
    """
    Where the real robot stands, as its drivers report its joint positions.
    """

    joint_state_topics: Sequence[str] = RealRobotPreflight.joint_state_topics
    """
    The topics the drivers publish the joint positions on.
    """

    wait_seconds: float = 5.0
    """
    How long, in seconds, the joint positions are waited for.
    """

    node_name: str = "cramera_robot_posture"
    """
    The name of the node the joint positions are read through.
    """

    def apply(self, world: World) -> None:
        """
        :param world: A world holding the real robot, its joints put where the real
            ones stand.
        :raises JointStatesNotReceived: When a topic sends no joint positions in time.
        :raises WorldEntityNotFoundError: When a joint the drivers name is not in the
            world.
        """
        with SpinningNode(self.node_name).running() as node:
            received = JointStateMessages(self.joint_state_topics).receive(
                node, self.wait_seconds
            )
            silent = [
                topic for topic in self.joint_state_topics if topic not in received
            ]
            if silent:
                raise JointStatesNotReceived(silent)
        for message in received.values():
            for name, position in zip(message.name, message.position):
                world.get_connection_by_name(name).position = position
        world.notify_state_change()


# %% command


def main() -> None:
    """
    ``cramera-preflight``: print what a real run would miss of the robot's drivers,
    ending with status 1 when anything is missing; the launch file the run would start
    Giskard with is read from the environment.
    """
    with SpinningNode("cramera_preflight").running() as node:
        report = RealRobotPreflight().check(node)
    print(report.to_text())
    sys.exit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
