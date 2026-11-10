"""
A ROS 2 node spun on a thread of its own, so that a run's plans, its perception and its
checks can wait for answers while the node keeps receiving them.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from threading import Thread

import rclpy
from rclpy.executors import Executor, SingleThreadedExecutor
from rclpy.node import Node
from typing_extensions import Iterator

# %% spinning node


@dataclass(frozen=True)
class SpinningNode:
    """
    A node that is spun while a block runs, ROS initialized for it unless it already
    was.
    """

    name: str
    """
    The node's name.
    """

    executor_type: type[Executor] = SingleThreadedExecutor
    """
    Spins the node; a multi-threaded one lets a callback wait for another.
    """

    @contextmanager
    def running(self) -> Iterator[Node]:
        """
        Create and spin the node while the block runs, then destroy it, and shut ROS
        down again if it was initialized for the node.

        :return: The node.
        """
        with ExitStack() as spinning:
            if not rclpy.ok():
                rclpy.init()
                spinning.callback(rclpy.try_shutdown)
            node = rclpy.create_node(self.name)
            spinning.callback(node.destroy_node)
            executor = self.executor_type()
            executor.add_node(node)
            Thread(target=executor.spin, daemon=True, name=self.name).start()
            spinning.callback(executor.shutdown)
            yield node
