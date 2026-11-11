"""
Mirroring where the real robot stands into the plan builder, before and between runs:
the joint positions its arms' drivers publish are written out at a steady rate. Nothing
is commanded; the drivers' topics are only read.

Run as ``python -m cramera_bridge.plans.mirroring``, it writes a
:class:`~cramera_protocol.plan_builder.RobotPosture` as one line of JSON to its standard
output at every interval once the drivers reported, and ends when its standard input
closes, as the plan builder that started it ends.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field

from rclpy.node import Node
from sensor_msgs.msg import JointState
from typing_extensions import Dict, Sequence, TextIO

from cramera.lifeline import Lifeline
from cramera_bridge.real_robot import RealRobotPreflight
from cramera_bridge.ros_node import SpinningNode
from cramera_protocol.plan_builder import RobotPosture

# %% mirror


@dataclass
class PostureMirror:
    """
    Keeps the latest joint positions the arms' drivers report and writes them out at a
    steady rate.
    """

    joint_state_topics: Sequence[str] = RealRobotPreflight.joint_state_topics
    """
    The topics the drivers publish the joint positions on.
    """

    interval: float = 0.1
    """
    How long, in seconds, lies between two postures written.
    """

    node_name: str = "cramera_posture_mirror"
    """
    The name of the node the joint positions are read through.
    """

    positions: Dict[str, float] = field(default_factory=dict, init=False)
    """
    The latest position of every joint reported so far, by its name.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Guards :attr:`positions` between the node's thread and the writing one.
    """

    def keep(self, message: JointState) -> None:
        """
        :param message: Joint positions a driver reported.
        """
        with self.lock:
            self.positions.update(zip(message.name, message.position))

    def subscribe(self, node: Node) -> None:
        """
        :param node: A spinning node that receives the drivers' joint positions for
            :meth:`keep`.
        """
        for topic in self.joint_state_topics:
            node.create_subscription(JointState, topic, self.keep, 1)

    def posture(self) -> RobotPosture:
        """
        :return: The latest joint positions reported.
        """
        with self.lock:
            return RobotPosture(joint_positions=dict(self.positions))

    def write(self, output: TextIO, stopped: threading.Event) -> None:
        """
        Write the latest posture to `output` at every interval, once one was reported,
        until `stopped` is set.

        :param output: Where each posture goes, one line of JSON each.
        :param stopped: Ends the writing.
        """
        while not stopped.wait(self.interval):
            posture = self.posture()
            if posture.joint_positions:
                output.write(json.dumps(posture.to_json()) + "\n")
                output.flush()

    def run(self) -> None:
        """
        Mirror the drivers' joint positions to the standard output until the standard
        input closes.
        """
        stopped = threading.Event()
        Lifeline(sys.stdin.fileno(), end=stopped.set).watch()
        with SpinningNode(self.node_name).running() as node:
            self.subscribe(node)
            self.write(sys.stdout, stopped)


if __name__ == "__main__":
    PostureMirror().run()
