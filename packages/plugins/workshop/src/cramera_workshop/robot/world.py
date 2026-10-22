"""
The workshop bundle as a CRAM world: the environment with its drawers, every loose body
on its own free connection at its spawn pose, and the handles a hand grasps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List

from cramera_cram.scenes.bundle_world import PoseText
from cramera_cram.scenes.environment import SceneEnvironment
from cramera_protocol.geometry import Pose as ProtocolPose
from cramera_workshop.bundle import WorkshopBundle
from semantic_digital_twin.adapters.urdf import URDFParser
from semantic_digital_twin.api import RobotSpecification
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Handle
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix, Pose
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

KEEP_URDF_NAMES = ""
"""
The prefix that keeps the names a URDF gives its links and joints.
"""

# %% names


class WorkshopBody(StrEnum):
    """
    The workshop's bodies the robot demos name.
    """

    SCREW = "screw_1"
    """
    The screw the demos pick up and drive.
    """

    SCREW_BOX = "screw_box"
    """
    The box of screws on the right shelf.
    """

    SCREW_BOX_HANDLE = "screw_box_handle"
    """
    The screw box's carry bar.
    """

    DRIVER = "driver"
    """
    The screwdriver in its cradle.
    """

    ASSEMBLY = "workshop_assembly"
    """
    The workpiece with the pilot hole.
    """

    FLOOR = "workshop_floor"
    """
    The floor.
    """


# %% robot start


@dataclass(frozen=True)
class RobotStart:
    """
    Where a robot starts in the workshop: on the floor, facing the workbench.
    """

    x: float = 0.16
    """
    The base's x position, in metres.
    """

    y: float = -0.76
    """
    The base's y position, clear of the workbench's front edge, in metres.
    """

    yaw: float = math.pi / 2
    """
    The base's heading, towards the workbench, in radians.
    """

    def pose(self) -> HomogeneousTransformationMatrix:
        """
        :return: The base's pose in the world.
        """
        return HomogeneousTransformationMatrix.from_xyz_rpy(
            x=self.x, y=self.y, yaw=self.yaw
        )

    def world_pose(self, world: World) -> Pose:
        """
        :param world: The world the base stands in.
        :return: The base's pose in the world's root frame.
        """
        return Pose.from_xyz_rpy(
            x=self.x, y=self.y, yaw=self.yaw, reference_frame=world.root
        )

    def pr2(self) -> RobotSpecification:
        """
        :return: A PR2 starting here.
        """
        return RobotSpecification(
            semantic_annotation_type=PR2, odom_T_robot_start=self.pose()
        )


# %% environment


@dataclass
class WorkshopEnvironment(SceneEnvironment):
    """
    Builds CRAM worlds holding a workshop bundle.
    """

    bundle: WorkshopBundle = field(default_factory=WorkshopBundle.packaged)
    """
    The workshop bundle.
    """

    def populate(self, world: World) -> None:
        """
        Add the environment models, the loose bodies at their spawn poses and the
        handles.

        :param world: The world receiving the workshop below its root.
        """
        for model in self.bundle.scene.models:
            if model.robot:
                continue
            self.merge_model(world, self.bundle.file(model.urdf), KEEP_URDF_NAMES)
        for item in self.bundle.movable_objects():
            body = URDFParser.from_file(
                str(self.bundle.file(item.urdf)), prefix=KEEP_URDF_NAMES
            ).parse()
            world.merge_world_at_pose(body, PoseText(item.spawn).native(world.root))
        with world.modify_world():
            for handle in self.bundle.semantics().handles:
                world.add_semantic_annotation(
                    Handle(root=world.get_body_by_name(handle))
                )

    def pose_of(self, world: World, pose: ProtocolPose) -> Pose:
        """
        :param world: A world holding the workshop.
        :param pose: A pose of the workshop description.
        :return: The pose in the world's root frame.
        """
        return PoseText(pose).native(world.root).to_pose()

    def pilot_mouth(self, world: World) -> Pose:
        """
        :param world: A world holding the workshop.
        :return: The pilot hole's entrance, its z axis out of the hole, in the world's
            root frame.
        """
        assembly = self.bundle.workshop.assembly
        workpiece = world.get_body_by_name(assembly.key)
        mouth = assembly.local_mouth
        pose = (
            workpiece.global_pose.to_homogeneous_matrix()
            @ HomogeneousTransformationMatrix.from_xyz_rpy(mouth.x, mouth.y, mouth.z)
        ).to_pose()
        pose.reference_frame = world.root
        return pose

    def screws(self, world: World) -> List[Body]:
        """
        :param world: A world holding the workshop.
        :return: The screws, in the description's order.
        """
        return [world.get_body_by_name(key) for key in self.bundle.workshop.screws()]
