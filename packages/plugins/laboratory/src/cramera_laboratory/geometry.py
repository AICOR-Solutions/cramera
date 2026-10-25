"""
Rigid poses as the laboratory computes with them: a position and a rotation matrix, read
from the protocol's ``[x, y, z, qx, qy, qz, qw]`` or from a simulator's state.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from cramera_protocol.geometry import Pose, Vector3

# %% poses


@dataclass(frozen=True)
class RigidPose:
    """
    Where a body is: a position in metres and a rotation into the laboratory's frame.
    """

    position: np.ndarray
    """
    The body origin's position.
    """

    rotation: np.ndarray
    """
    The 3×3 matrix rotating the body's axes into the laboratory's frame.
    """

    @classmethod
    def of_pose(cls, pose: Pose) -> RigidPose:
        """
        :param pose: A protocol pose.
        :return: The same pose.
        """
        return cls(
            position=np.array([pose.x, pose.y, pose.z]),
            rotation=Rotation.from_quat(
                [pose.qx, pose.qy, pose.qz, pose.qw]
            ).as_matrix(),
        )

    @classmethod
    def of_scalar_first(cls, position: np.ndarray, quaternion: np.ndarray) -> RigidPose:
        """
        :param position: A position.
        :param quaternion: A unit quaternion with its scalar first, as MuJoCo writes it.
        :return: The pose.
        """
        return cls(
            position=np.array(position, dtype=float),
            rotation=Rotation.from_quat(quaternion, scalar_first=True).as_matrix(),
        )

    def point_in_world(self, local: np.ndarray) -> np.ndarray:
        """
        :param local: A point in the body's frame.
        :return: The point in the laboratory's frame.
        """
        return self.rotation @ local + self.position

    def point_in_body(self, world: np.ndarray) -> np.ndarray:
        """
        :param world: A point in the laboratory's frame.
        :return: The point in the body's frame.
        """
        return self.rotation.T @ (world - self.position)

    def moved_to(self, position: np.ndarray) -> RigidPose:
        """
        :param position: Another position.
        :return: This pose's rotation at that position.
        """
        return RigidPose(
            position=np.array(position, dtype=float), rotation=self.rotation
        )

    @property
    def axis(self) -> np.ndarray:
        """
        The body's z axis in the laboratory's frame.
        """
        return self.rotation[:, 2]

    def pose(self) -> Pose:
        """
        :return: The pose as the protocol writes it.
        """
        quaternion = Rotation.from_matrix(self.rotation).as_quat()
        return Pose(*(float(value) for value in (*self.position, *quaternion)))


def vector_of(values: np.ndarray) -> Vector3:
    """
    :param values: Three numbers.
    :return: The protocol vector of them.
    """
    return Vector3(*(float(value) for value in values))
