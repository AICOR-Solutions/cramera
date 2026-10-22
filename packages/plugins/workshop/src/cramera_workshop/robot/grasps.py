"""
How the PR2 grasps the workshop's screws, screwdriver and screw box: the tool poses
before, at and after each grasp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from typing_extensions import List, Optional, Sequence

from coraplex.datastructures.grasp import GraspDescription
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix, Pose
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

# %% poses


@dataclass(frozen=True)
class GraspPoses:
    """
    The tool poses of one grasp, in the world's root frame.
    """

    world: World
    """
    The world the poses are in.
    """

    before: HomogeneousTransformationMatrix
    """
    Where the tool waits before the grasp.
    """

    at: HomogeneousTransformationMatrix
    """
    Where the tool closes.
    """

    after: HomogeneousTransformationMatrix
    """
    Where the tool goes with the grasped body.
    """

    def sequence(self, reverse: bool) -> List[Pose]:
        """
        :param reverse: Whether to put the poses in reverse, as placing does.
        :return: The poses in the world's root frame, in order.
        """
        poses = [matrix.to_pose() for matrix in (self.before, self.at, self.after)]
        for pose in poses:
            pose.reference_frame = self.world.root
        return poses[::-1] if reverse else poses


def world_of(description: GraspDescription) -> World:
    """
    :param description: A grasp description.
    :return: The world of its end effector.
    """
    return description.end_effector._world


# %% screws

DOWN = np.array([0.0, 0.0, -1.0])
"""
The world's downward direction.
"""

UPRIGHT_ALIGNMENT = 0.99
"""
How closely a shaft must point along the vertical to count as standing upright.
"""


@dataclass(frozen=True)
class ShaftFrame:
    """
    A screw's frame with its roll about the shaft removed: z along the measured shaft, x
    pointing down as far as the shaft allows.

    A screw lying in a box may have rolled; grasping it does not depend on how far.
    """

    world_T_screw: np.ndarray
    """
    The screw's measured pose in the world.
    """

    def matrix(self) -> np.ndarray:
        """
        :return: The frame in the world; the screw's own frame for an upright screw,
            whose roll the downward direction cannot fix.
        """
        shaft = self.world_T_screw[:3, 2]
        if abs(float(np.dot(shaft, DOWN))) > UPRIGHT_ALIGNMENT:
            return self.world_T_screw
        down = DOWN - np.dot(DOWN, shaft) * shaft
        down /= np.linalg.norm(down)
        frame = np.eye(4)
        frame[:3, 0] = down
        frame[:3, 1] = np.cross(shaft, down)
        frame[:3, 2] = shaft
        frame[:3, 3] = self.world_T_screw[:3, 3]
        return frame


@dataclass
class ScrewGrasp(GraspDescription):
    """
    Grasps a screw's shaft from above and lifts it straight up, for screws lying in a
    box, rolled or not, and screws standing upright alike.
    """

    shaft_offset: float = 0.070
    """
    How far along the screw's shaft from its tip the fingers close, in metres.
    """

    def pose_sequence(
        self,
        target_T_grasp_pose: Pose,
        body: Optional[Body] = None,
        reverse: bool = False,
    ) -> List[Pose]:
        world = world_of(self)
        world_T_screw = world.transform(
            target_T_grasp_pose.to_homogeneous_matrix(), world.root
        )
        world_T_shaft = HomogeneousTransformationMatrix(
            ShaftFrame(world_T_screw.to_np()).matrix(), reference_frame=world.root
        )
        world_T_tool = world_T_shaft @ HomogeneousTransformationMatrix.from_xyz_rpy(
            z=self.shaft_offset
        )
        world_T_clear = (
            HomogeneousTransformationMatrix.from_xyz_rpy(z=self.manipulation_offset)
            @ world_T_tool
        )
        return GraspPoses(world, world_T_clear, world_T_tool, world_T_clear).sequence(
            reverse
        )


# %% screwdriver


@dataclass
class DriverGrasp(ScrewGrasp):
    """
    Grasps the screwdriver's handle along its axis, so turning the wrist turns the
    shaft, and lifts it out of its cradle.
    """

    shaft_offset: float = 0.195
    """
    How far from the driver's tip the handle's middle is, in metres.
    """

    approach_clearance: float = 0.025
    """
    How far behind the handle along its axis the tool waits, in metres.
    """

    lift: float = 0.20
    """
    How high the driver is lifted out of its cradle, in metres.
    """

    def pose_sequence(
        self,
        target_T_grasp_pose: Pose,
        body: Optional[Body] = None,
        reverse: bool = False,
    ) -> List[Pose]:
        world = world_of(self)
        target = world.transform(
            target_T_grasp_pose.to_homogeneous_matrix(), world.root
        ) @ HomogeneousTransformationMatrix.from_xyz_rpy(
            z=self.shaft_offset, pitch=math.pi / 2
        )
        before = target @ HomogeneousTransformationMatrix.from_xyz_rpy(
            x=-self.approach_clearance
        )
        after = HomogeneousTransformationMatrix.from_xyz_rpy(z=self.lift) @ target
        return GraspPoses(world, before, target, after).sequence(reverse)


# %% screw box


@dataclass
class BoxHandleGrasp(GraspDescription):
    """
    Grasps the screw box's front carry bar from the aisle and withdraws towards it
    before any sideways movement near the shelf posts.
    """

    handle_offset: Sequence[float] = field(default=(0.0, -0.204, 0.055))
    """
    The carry bar's middle in the box's frame, in metres.
    """

    withdrawal: float = 0.05
    """
    How far towards the aisle the tool waits before the grasp, in metres.
    """

    lift: float = 0.09
    """
    How high the box is lifted off the shelf, in metres.
    """

    def pose_sequence(
        self,
        target_T_grasp_pose: Pose,
        body: Optional[Body] = None,
        reverse: bool = False,
    ) -> List[Pose]:
        world = world_of(self)
        world_T_box = world.transform(
            target_T_grasp_pose.to_homogeneous_matrix(), world.root
        )
        target = world_T_box @ HomogeneousTransformationMatrix.from_xyz_rpy(
            *self.handle_offset, yaw=math.pi / 2
        )
        before = (
            HomogeneousTransformationMatrix.from_xyz_rpy(y=-self.withdrawal) @ target
        )
        after = HomogeneousTransformationMatrix.from_xyz_rpy(z=self.lift) @ target
        return GraspPoses(world, before, target, after).sequence(reverse)
