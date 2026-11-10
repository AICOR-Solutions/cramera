"""
The safety limits of a robot profile as the constraints every motion of a run is held
to: a workspace box per arm, written in the frame of the pose the plan stands the robot
at, and the speed no tool may exceed; and the velocity no arm joint may exceed, which
the robot's description sets.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from typing_extensions import List, Optional

from cramera_bridge.names import ENUM_NAMES
from cramera_bridge.performing import TaskContext
from cramera_bridge.plans.arms import Arms, RobotArms
from cramera_bridge.plans.site import RobotSite
from cramera_protocol.robot_profile import ArmWorkspace, SafetyLimits
from giskardpy.motion_statechart.monitors.safety_monitors import (
    MaximumJointVelocity,
    MaximumToolVelocity,
    SafetyConstraint,
    SafetyEnvelope,
    WorkspaceBox,
)
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix, Point3
from semantic_digital_twin.world_description.connections import ActiveConnection1DOF


@dataclass(frozen=True)
class RobotSafety:
    """
    The safety limits a robot profile holds the performing robot of a plan to.
    """

    limits: SafetyLimits
    """
    The profile's safety limits.
    """

    site: RobotSite = field(default_factory=RobotSite)
    """
    Where the plan stands the robot, whose frame the workspaces are written in.
    """

    on_the_real_robot: bool = False
    """
    Whether the run moves the real robot, which holds its tools to the limits' speed for
    the real robot where they set one.
    """

    def envelope(self, context: TaskContext) -> SafetyEnvelope:
        """
        :param context: The world and the performing robot.
        :return: The constraints of every workspace and, for every arm, of the joint
            and tool velocities.
        """
        return SafetyEnvelope(
            constraints=[
                *[self.workspace_box(context, each) for each in self.limits.workspaces],
                *self.velocity_limits(context),
            ]
        )

    def workspace_box(
        self, context: TaskContext, workspace: ArmWorkspace
    ) -> WorkspaceBox:
        """
        :param context: The world and the performing robot.
        :param workspace: The workspace of one of its arms.
        :return: The box the arm's tool stays inside: the smallest box in the frame of
            the robot's root holding the workspace, exactly it when both frames share
            their axes.
        """
        world, robot = context.world, context.robot
        [arm] = RobotArms(robot).arms(ENUM_NAMES.member(Arms, workspace.arm))
        pose = self.site.pose
        world_T_plan = HomogeneousTransformationMatrix.from_xyz_quaternion(
            pose.x, pose.y, pose.z, pose.qx, pose.qy, pose.qz, pose.qw
        ).to_np()
        root_T_plan = (
            np.linalg.inv(world.compute_forward_kinematics_np(world.root, robot.root))
            @ world_T_plan
        )
        box = workspace.box
        corners = np.array(
            [
                (root_T_plan @ [x, y, z, 1.0])[:3]
                for x, y, z in itertools.product(
                    (box.min_x, box.max_x),
                    (box.min_y, box.max_y),
                    (box.min_z, box.max_z),
                )
            ]
        )
        return WorkspaceBox(
            constraint=workspace.label,
            tool=arm.end_effector.tool_frame,
            minimum=Point3(*corners.min(axis=0), reference_frame=robot.root),
            maximum=Point3(*corners.max(axis=0), reference_frame=robot.root),
        )

    @property
    def maximum_tool_velocity(self) -> Optional[float]:
        """
        The speed, in metres per second, no tool of the run may exceed; None sets none.
        """
        if (
            self.on_the_real_robot
            and self.limits.maximum_real_robot_tool_velocity is not None
        ):
            return self.limits.maximum_real_robot_tool_velocity
        return self.limits.maximum_tool_velocity

    def velocity_limits(self, context: TaskContext) -> List[SafetyConstraint]:
        """
        :param context: The world and the performing robot.
        :return: For every arm, the velocity its joints may not exceed, as the robot's
            description sets it, and the speed its tool may not exceed, as far as they
            are set.
        """
        robot = context.robot
        arms = RobotArms(robot)
        joint_velocity = robot.maximum_safe_joint_velocity
        tool_velocity = self.maximum_tool_velocity
        constraints: List[SafetyConstraint] = []
        for arm in robot.all_arms:
            side = ENUM_NAMES.member_identifier(Arms, arms.find_side(arm))
            if joint_velocity is not None:
                constraints.append(
                    MaximumJointVelocity(
                        constraint=f"{side} arm joint velocity ({joint_velocity} rad/s)",
                        connections=[
                            connection
                            for connection in arm.connections
                            if isinstance(connection, ActiveConnection1DOF)
                        ],
                        maximum_velocity=joint_velocity,
                    )
                )
            if tool_velocity is not None:
                constraints.append(
                    MaximumToolVelocity(
                        constraint=f"{side} tool velocity ({tool_velocity} m/s)",
                        root_link=robot.root,
                        tool=arm.end_effector.tool_frame,
                        maximum_velocity=tool_velocity,
                    )
                )
        return constraints
