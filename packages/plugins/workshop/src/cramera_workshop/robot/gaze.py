"""
The PR2 looks at the hand it moves: a head task that follows the tool frame while the
native Cartesian tool task runs, and a hold of the base at its station.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import ClassVar

from coraplex.alternative_motion_mapping import AlternativeMotion
from coraplex.datastructures.enums import ExecutionType
from coraplex.robot_plans.motions.gripper import MoveToolCenterPointMotion
from coraplex.view_manager import ViewManager
from giskardpy.motion_statechart.context import MotionStatechartContext
from giskardpy.motion_statechart.data_types import DefaultWeights
from giskardpy.motion_statechart.error_signals import SampledErrorSignal
from giskardpy.motion_statechart.goals.templates import Parallel
from giskardpy.motion_statechart.graph_node import NodeArtifacts
from giskardpy.motion_statechart.tasks.cartesian_tasks import CartesianPose
from giskardpy.motion_statechart.tasks.pointing import Pointing
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.spatial_types import Point3, Pose, Vector3
from semantic_digital_twin.world import World

# %% names


class GazeTask(StrEnum):
    """
    The names of the head and base tasks in recorded statecharts.
    """

    FOLLOW_TOOL = "Follow active gripper"
    """
    The head follows the moving tool frame.
    """

    MOVE_WITH_GAZE = "Move tool with gaze"
    """
    The tool moves while the head follows it.
    """

    HOLD_BASE = "Hold workshop base"
    """
    The base stays at its station.
    """


@dataclass(frozen=True)
class GazeLimits:
    """
    How fast and how precisely the head follows the tool.
    """

    maximum_head_velocity: float = 0.5
    """
    The head's largest angular speed, in radians per second.
    """

    pointing_threshold: float = 0.025
    """
    How far the head may point off the tool and still count as following it, in radians.
    """

    base_threshold: float = 0.0001
    """
    How far the base may drift from its station, in metres and radians.
    """


GAZE_LIMITS = GazeLimits()
"""
The limits every gaze task of the workshop uses.
"""

# %% tasks


@dataclass(eq=False, repr=False)
class FollowingPointing(Pointing):
    """
    A pointing task whose goal frame moves: the goal's transform is read again every
    tick, without the task controlling that frame.
    """

    def on_tick(self, context: MotionStatechartContext) -> None:
        self._forward_kinematics_binding.bind(context.world)

    def build_artifacts(self, context: MotionStatechartContext) -> NodeArtifacts:
        artifacts = super().build_artifacts(context)
        artifacts.error = SampledErrorSignal(artifacts.error.expression)
        return artifacts


@dataclass(eq=False, repr=False)
class ManipulationWithGaze(Parallel):
    """
    A tool task with accompanying tasks that completes when the tool task does, even
    when the head's limits keep it from pointing exactly.
    """

    def build_artifacts(self, context: MotionStatechartContext) -> NodeArtifacts:
        return NodeArtifacts(observation=self.nodes[0].observation_variable)


def follow_tool(robot: AbstractRobot, tool_frame) -> FollowingPointing:
    """
    :param robot: The robot whose camera follows.
    :param tool_frame: The tool frame to follow.
    :return: The head task pointing the default camera at the tool frame.
    """
    camera = robot.get_default_camera().root
    return FollowingPointing(
        name=GazeTask.FOLLOW_TOOL,
        root_link=robot.get_torso().root,
        tip_link=camera,
        goal_point=Point3(reference_frame=tool_frame),
        pointing_axis=Vector3.Z(reference_frame=camera),
        max_velocity=GAZE_LIMITS.maximum_head_velocity,
        threshold=GAZE_LIMITS.pointing_threshold,
        weight=DefaultWeights.WEIGHT_BELOW_COLLISION_AVOIDANCE,
    )


def hold_base(world: World, robot: AbstractRobot) -> CartesianPose:
    """
    :param world: The world the robot is in.
    :param robot: The robot.
    :return: A task keeping the base at its measured station.
    """
    return CartesianPose(
        name=GazeTask.HOLD_BASE,
        root_link=world.root,
        tip_link=robot.root,
        goal_pose=Pose(reference_frame=robot.root),
        translation_threshold=GAZE_LIMITS.base_threshold,
        orientation_threshold=GAZE_LIMITS.base_threshold,
        weight=DefaultWeights.WEIGHT_ABOVE_COLLISION_AVOIDANCE,
    )


# %% motion mappings


@dataclass
class GazeToolCenterPointMotion(MoveToolCenterPointMotion, AlternativeMotion[PR2]):
    """
    The PR2's simulated tool motion: the unchanged native Cartesian tool task, with the
    head following the tool.
    """

    execution_type: ClassVar[ExecutionType] = ExecutionType.SIMULATED
    """
    Simulated execution selects this mapping.
    """

    @property
    def _motion_chart(self) -> ManipulationWithGaze:
        tool = ViewManager().get_end_effector_view(self.arm, self.robot).tool_frame
        return ManipulationWithGaze(
            [super()._motion_chart, follow_tool(self.robot, tool)],
            name=GazeTask.MOVE_WITH_GAZE,
        )


@dataclass
class AnchoredToolCenterPointMotion(GazeToolCenterPointMotion):
    """
    The PR2's simulated tool motion with the head following the tool and the base held
    at its station, so collision avoidance cannot drift the base away from an object
    being grasped.
    """

    @property
    def _motion_chart(self) -> ManipulationWithGaze:
        chart = super()._motion_chart
        chart.nodes.append(hold_base(self.world, self.robot))
        return chart
