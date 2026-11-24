"""
Stand-ins for the drivers of the real Tracy: its grippers' parallel gripper command
servers and its arms' joint state publishers, and for RoboKudos answering in odd ways.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from threading import Event, Timer

from control_msgs.action import ParallelGripperCommand
from geometry_msgs.msg import PoseStamped
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from sensor_msgs.msg import Image, JointState
from typing_extensions import Iterator

from coraplex.perception import ROBOKUDO_QUERY_ACTION_NAME
from robokudo_msgs.action import Query
from robokudo_msgs.msg import ObjectDesignator
from semantic_digital_twin.robots.tracy import TracyParallelGripperCommandTopic

# %% grippers


@dataclass
class GripperDriverStandIn:
    """
    Answers every goal of a gripper's parallel gripper command action as reached.
    """

    topic: str
    """
    The name the action is served under.
    """

    commanded_positions: list[float] = field(default_factory=list)
    """
    The finger positions the goals commanded, in the order they arrived.
    """

    def execute(self, goal_handle: ServerGoalHandle) -> ParallelGripperCommand.Result:
        """
        :param goal_handle: A goal that arrived.
        :return: The result reporting it reached.
        """
        self.commanded_positions.extend(goal_handle.request.command.position)
        goal_handle.succeed()
        return ParallelGripperCommand.Result(reached_goal=True)

    def serve(self, node: Node) -> ActionServer:
        """
        :param node: The node serving the action.
        :return: The server, until it is destroyed.
        """
        return ActionServer(
            node, ParallelGripperCommand, self.topic, execute_callback=self.execute
        )


@contextmanager
def tracy_gripper_drivers(node: Node) -> Iterator[dict[str, GripperDriverStandIn]]:
    """
    Serve both of Tracy's gripper actions from `node` while the block runs.

    :param node: A spinning node.
    :return: The stand-in of each gripper by its action's name.
    """
    drivers = {
        topic.value: GripperDriverStandIn(topic.value)
        for topic in TracyParallelGripperCommandTopic
    }
    with ExitStack() as serving:
        for driver in drivers.values():
            serving.callback(driver.serve(node).destroy)
        yield drivers


# %% joint states


@dataclass
class JointStatePublisherStandIn:
    """
    Publishes fixed positions of named joints on a joint state topic, as a driver does.
    """

    topic: str
    """
    The topic the positions are published on.
    """

    positions: dict[str, float]
    """
    The position of each joint by its name.
    """

    period: float = 0.05
    """
    How long, in seconds, lies between two messages.
    """

    velocity: float = 0.0
    """
    The velocity every joint reports.
    """

    @contextmanager
    def publishing(self, node: Node) -> Iterator[None]:
        """
        Publish the positions from `node` while the block runs.

        :param node: A spinning node.
        """
        publisher = node.create_publisher(JointState, self.topic, 10)
        message = JointState(
            name=list(self.positions),
            position=list(self.positions.values()),
            velocity=[self.velocity] * len(self.positions),
        )
        timer = node.create_timer(self.period, lambda: publisher.publish(message))
        with ExitStack() as publishing:
            publishing.callback(node.destroy_publisher, publisher)
            publishing.callback(node.destroy_timer, timer)
            yield


# %% perception


@dataclass
class RoboKudoThatNeverAnswers:
    """
    Takes up every query on RoboKudo's query action and answers none, as a pipeline does
    whose camera data never arrives.
    """

    released: Event = field(default_factory=Event)
    """
    Set once the queries taken up may end, unanswered.
    """

    def execute(self, goal_handle: ServerGoalHandle) -> Query.Result:
        """
        :param goal_handle: A query that arrived, held until :attr:`released` is set.
        :return: An empty result, the query aborted.
        """
        self.released.wait()
        goal_handle.abort()
        return Query.Result()

    @contextmanager
    def serving(self, node: Node) -> Iterator[None]:
        """
        Serve the query action from `node` while the block runs.

        :param node: A node spun by a multi-threaded executor.
        """
        server = ActionServer(
            node,
            Query,
            ROBOKUDO_QUERY_ACTION_NAME,
            execute_callback=self.execute,
            callback_group=ReentrantCallbackGroup(),
        )
        with ExitStack() as serving:
            serving.callback(server.destroy)
            serving.callback(self.released.set)
            yield


@dataclass
class RoboKudoTellingNoColors:
    """
    Answers every query with one object at a fixed place, in no color.
    """

    position: tuple[float, float, float]
    """
    Where the object is reported, in :attr:`frame`.
    """

    frame: str = "map"
    """
    The frame of :attr:`position`, the world's root on tf.
    """

    def execute(self, goal_handle: ServerGoalHandle) -> Query.Result:
        """
        :return: The object, the query succeeded.
        """
        pose = PoseStamped()
        pose.header.frame_id = self.frame
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = self.position
        pose.pose.orientation.w = 1.0
        goal_handle.succeed()
        return Query.Result(res=[ObjectDesignator(pose=[pose])])

    @contextmanager
    def serving(self, node: Node) -> Iterator[None]:
        """
        Serve the query action from `node` while the block runs.

        :param node: A node spun by a multi-threaded executor.
        """
        server = ActionServer(
            node,
            Query,
            ROBOKUDO_QUERY_ACTION_NAME,
            execute_callback=self.execute,
            callback_group=ReentrantCallbackGroup(),
        )
        with ExitStack() as serving:
            serving.callback(server.destroy)
            yield


@dataclass
class RoboKudoSeeingNothing:
    """
    Answers every query with no object, publishing what its cluster extractor drew a
    moment later, as RoboKudo's visualizer does.
    """

    drawn: Image = field(
        default_factory=lambda: Image(
            height=1, width=1, encoding="bgr8", step=3, data=bytes([0, 0, 255])
        )
    )
    """
    The image published :attr:`drawing_time` seconds after every answer.
    """

    topic: str = "/TracyCubesPipeline/PointCloudClusterExtractor/output_image"
    """
    The topic of :attr:`drawn`, named as RoboKudo's visualizer names it.
    """

    drawing_time: float = 0.2
    """
    Seconds after an answer :attr:`drawn` is published, a visualizer tick later.
    """

    @contextmanager
    def serving(self, node: Node) -> Iterator[None]:
        """
        Serve the query action from `node` while the block runs.
        """
        publisher = node.create_publisher(Image, self.topic, 1)
        drawings: list[Timer] = []

        def execute(goal_handle: ServerGoalHandle) -> Query.Result:
            drawing = Timer(self.drawing_time, publisher.publish, [self.drawn])
            drawings.append(drawing)
            drawing.start()
            goal_handle.succeed()
            return Query.Result()

        server = ActionServer(
            node,
            Query,
            ROBOKUDO_QUERY_ACTION_NAME,
            execute_callback=execute,
            callback_group=ReentrantCallbackGroup(),
        )
        with ExitStack() as serving:
            serving.callback(server.destroy)
            serving.callback(node.destroy_publisher, publisher)
            serving.callback(lambda: [drawing.cancel() for drawing in drawings])
            yield
