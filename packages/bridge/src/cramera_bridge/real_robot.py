"""
The real robot a run moves: the Giskard that commands it, the preflight checking that
its drivers are up before a run starts, and reading where it stands.

Run as ``cramera-preflight`` (or ``python -m cramera_bridge.real_robot``), the preflight
prints what a real run would miss and ends with a nonzero status when anything is
missing.
"""

from __future__ import annotations

import ctypes
import importlib.util
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from control_msgs.action import ParallelGripperCommand
from rclpy.action import ActionClient
from rclpy.action.graph import get_action_names_and_types
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.publisher import Publisher
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from typing_extensions import Callable, Iterator, Mapping, Sequence

from cramera_bridge.exceptions import JointStatesNotReceived
from cramera_bridge.ros_node import SpinningNode
from semantic_digital_twin.robots.tracy import (
    TracyParallelGripperCommandTopic,
    TracyTopic,
    TracyVelocityCommandTopic,
)
from semantic_digital_twin.world import World

# %% Giskard


class RealRobotVariable(StrEnum):
    """
    The environment variables a deployment configures its real runs with.
    """

    GISKARD_SCRIPT = "CRAMERA_GISKARD_SCRIPT"
    """
    The :class:`GiskardScript` a real run starts Giskard with; the one commanding the
    real robot when it is not set.
    """


class GiskardScript(StrEnum):
    """
    The scripts of giskardpy that run a Giskard for Tracy as a ROS node, started as a
    process of their own; no launch file, so nothing else, such as RViz or an
    interactive marker sending goals, starts with them.
    """

    VELOCITY = "tracy_velocity"
    """
    A Giskard commanding the velocity controllers of the real Tracy, reading its joint
    states and its robot description (``/robot_description``) from its drivers.
    """

    STANDALONE = "tracy_standalone"
    """
    A Giskard simulating Tracy's arms instead of commanding them, needing no driver.
    """

    @property
    def module(self) -> str:
        """
        The module running the Giskard as its main module.
        """
        return f"giskardpy.middleware.ros2.scripts.iai_robots.tracy.{self.value}"

    @property
    def commands_the_real_robot(self) -> bool:
        """
        Whether the Giskard it starts moves the real robot, and reads its drivers.
        """
        return self is GiskardScript.VELOCITY

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> GiskardScript:
        """
        :param environment: The process environment, which may name the script.
        :return: The script it names, else :attr:`VELOCITY`.
        """
        return cls(
            environment.get(RealRobotVariable.GISKARD_SCRIPT, cls.VELOCITY.value)
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
    A Giskard run as a process group of its own, so that stopping it stops Giskard and
    nothing else; it is interrupted as well when the process that started it ends
    without stopping it, such as when killed.

    Interrupted, Giskard commands the robot's controllers zero velocities and ends.
    """

    script: GiskardScript
    """
    The script Giskard is started with.
    """

    stop_timeout: float = 3.0
    """
    How long, in seconds, Giskard may take to end once interrupted before it is killed.
    """

    @property
    def is_installed(self) -> bool:
        """
        Whether this interpreter finds the script's module.
        """
        return importlib.util.find_spec(self.script.module) is not None

    @contextmanager
    def running(self) -> Iterator[subprocess.Popen]:
        """
        Run Giskard while the block runs, then end it.

        :return: Giskard's process.
        """
        with ExitStack() as running:
            process = subprocess.Popen(
                [sys.executable, "-m", self.script.module],
                start_new_session=True,
                preexec_fn=self.interruption_with_starting_process(),
            )
            running.callback(self.stop, process)
            yield process

    @staticmethod
    def interruption_with_starting_process() -> Callable[[], None]:
        """
        :return: What Giskard's process runs before it starts, so that it is
            interrupted once the process starting it ends; looked up beforehand, as
            the forked child must not load libraries while other threads ran.
        """
        process_control = ctypes.CDLL(None).prctl
        return lambda: process_control(
            ProcessControl.SET_PARENT_DEATH_SIGNAL, signal.SIGINT
        )

    def stop(self, process: subprocess.Popen) -> None:
        """
        Interrupt Giskard's process group, killing it once :attr:`stop_timeout` passed.

        :param process: Giskard's process.
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


# %% halting the arms


@dataclass
class ArmHalt:
    """
    Commands every arm's velocity controller zero velocities, as Giskard does when it
    ends; sent once Giskard ended, so the controllers hold still even when Giskard was
    killed before it could.
    """

    command_topics: Sequence[str] = tuple(TracyVelocityCommandTopic)
    """
    The topics the arms' velocity controllers take their commands on.
    """

    joints_per_arm: int = 6
    """
    How many joints each controller commands; it refuses a command of another length.
    """

    acknowledgement_timeout: float = 1.0
    """
    How long, in seconds, each controller may take to acknowledge the command.
    """

    publishers: list[Publisher] = field(default_factory=list, init=False)
    """
    The publishers of the commands while :meth:`ready`.
    """

    @contextmanager
    def ready(self, node: Node) -> Iterator[ArmHalt]:
        """
        Keep a publisher on every command topic while the block runs, so the
        controllers have discovered it once :meth:`command` is called.

        :param node: A spinning node.
        :return: This halt.
        """
        with ExitStack() as ready:
            for topic in self.command_topics:
                publisher = node.create_publisher(Float64MultiArray, topic, 10)
                ready.callback(node.destroy_publisher, publisher)
                self.publishers.append(publisher)
            ready.callback(self.publishers.clear)
            yield self

    def command(self) -> None:
        """
        Command zero velocities on every topic and wait until they were acknowledged.
        """
        for publisher in self.publishers:
            publisher.publish(Float64MultiArray(data=[0.0] * self.joints_per_arm))
        for publisher in self.publishers:
            publisher.wait_for_all_acked(Duration(seconds=self.acknowledgement_timeout))


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

    GISKARD_SCRIPT = "Giskard script installed"
    """
    The script the run starts Giskard with.
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

    giskard_script: GiskardScript = field(
        default_factory=lambda: GiskardScript.from_environment(os.environ)
    )
    """
    The script the run starts Giskard with; one simulating the arms needs no arm driver
    and no camera.
    """

    wait_seconds: float = 15.0
    """
    How long, in seconds, the preflight waits in all for the requirements to be
    discovered; a requirement found earlier ends its own wait at once.
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
        :return: Which requirements were found; another Giskard is looked for once the
            drivers were waited for, so it had as long to be discovered.
        """
        deadline = time.monotonic() + self.wait_seconds
        checks = [
            PreflightCheck(
                RequirementKind.GISKARD_SCRIPT,
                self.giskard_script.value,
                GiskardProcess(self.giskard_script).is_installed,
            ),
            *(
                PreflightCheck(
                    RequirementKind.GRIPPER_ACTION_SERVER,
                    server,
                    self.is_gripper_action_served(node, server, deadline),
                )
                for server in self.gripper_action_servers
            ),
        ]
        if self.giskard_script.commands_the_real_robot:
            checks.extend(self.driver_checks(node, deadline))
        checks.append(
            PreflightCheck(
                RequirementKind.NO_OTHER_GISKARD,
                self.giskard_command_action,
                self.giskard_command_action
                not in dict(get_action_names_and_types(node)),
            )
        )
        return PreflightReport(checks)

    def driver_checks(self, node: Node, deadline: float) -> list[PreflightCheck]:
        """
        :param node: A spinning node.
        :param deadline: The :func:`time.monotonic` time the waits end at.
        :return: Whether the robot's description, the arms' joint states and the
            camera's topics were found.
        """
        received = JointStateMessages(self.joint_state_topics).receive(
            node, seconds_left_until(deadline)
        )
        return [
            PreflightCheck(
                RequirementKind.ROBOT_DESCRIPTION,
                self.robot_description_topic,
                is_published(node, self.robot_description_topic, deadline),
            ),
            *(
                PreflightCheck(RequirementKind.JOINT_STATES, topic, topic in received)
                for topic in self.joint_state_topics
            ),
            *(
                PreflightCheck(
                    RequirementKind.CAMERA_TOPIC,
                    topic,
                    is_published(node, topic, deadline),
                )
                for topic in self.camera_topics
            ),
        ]

    @staticmethod
    def is_gripper_action_served(node: Node, server: str, deadline: float) -> bool:
        """
        :param node: A spinning node.
        :param server: The name of a gripper's parallel gripper command action.
        :param deadline: The :func:`time.monotonic` time the wait ends at.
        :return: Whether a server of it was discovered before the deadline.
        """
        client = ActionClient(node, ParallelGripperCommand, server)
        served = client.wait_for_server(timeout_sec=seconds_left_until(deadline))
        client.destroy()
        return served


def seconds_left_until(deadline: float) -> float:
    """
    :param deadline: A :func:`time.monotonic` time.
    :return: The seconds until it, none once it passed.
    """
    return max(0.0, deadline - time.monotonic())


def is_published(
    node: Node, topic: str, deadline: float, polling_seconds: float = 0.1
) -> bool:
    """
    :param node: A spinning node.
    :param topic: The topic.
    :param deadline: The :func:`time.monotonic` time the wait ends at.
    :param polling_seconds: How often, in seconds, the publishers are counted.
    :return: Whether a publisher of the topic was discovered before the deadline.
    """
    while node.count_publishers(topic) == 0:
        if time.monotonic() >= deadline:
            return False
        time.sleep(polling_seconds)
    return True


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
    ending with status 1 when anything is missing; the script the run would start
    Giskard with is read from the environment.
    """
    with SpinningNode("cramera_preflight").running() as node:
        report = RealRobotPreflight().check(node)
    print(report.to_text())
    sys.exit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
