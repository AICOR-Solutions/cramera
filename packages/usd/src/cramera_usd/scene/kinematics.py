"""
Links and the joints between them, in URDF terms, with the joint values that explain the
poses of a joint's bodies.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

import numpy
from scipy.spatial.transform import Rotation
from typing_extensions import List, Optional

from cramera_usd.geometry.meshes import TriangleMesh
from cramera_usd.geometry.transforms import (
    FULL_TURN,
    SPACE_DIMENSIONS,
    RigidTransform,
    TransformTrack,
)

# %% joint types


class JointKind(StrEnum):
    """
    How a joint lets its child link move, named as URDF names its joint types.
    """

    FIXED = "fixed"
    """
    The child link does not move relative to its parent.
    """

    REVOLUTE = "revolute"
    """
    The child link rotates about the joint axis within limits.
    """

    CONTINUOUS = "continuous"
    """
    The child link rotates about the joint axis without limits.
    """

    PRISMATIC = "prismatic"
    """
    The child link slides along the joint axis within limits.
    """

    @property
    def movable(self) -> bool:
        """
        Whether a joint of this kind has a value that can change.
        """
        return self is not JointKind.FIXED

    @property
    def rotates(self) -> bool:
        """
        Whether the joint value is an angle in radians rather than a distance in metres.
        """
        return self in (JointKind.REVOLUTE, JointKind.CONTINUOUS)


X_AXIS = (1.0, 0.0, 0.0)
"""
The unit X axis, the motion axis of a joint that names none.
"""


# %% motion


@dataclass(frozen=True, eq=False)
class AllowedMotion:
    """
    How a joint lets its child link move: the kind of motion, its axis and its limits.
    """

    kind: JointKind
    """
    The kind of motion.
    """

    axis: numpy.ndarray = field(default_factory=lambda: numpy.array(X_AXIS))
    """
    The unit motion axis in the joint frame.
    """

    lower: Optional[float] = None
    """
    The lowest joint value (radians or metres), or None when unlimited.
    """

    upper: Optional[float] = None
    """
    The highest joint value (radians or metres), or None when unlimited.
    """

    def reversed(self) -> AllowedMotion:
        """
        :return: The same motion about the opposite axis: measuring the first joint
            frame relative to the second along it gives the values, and so keeps the
            limits, of measuring the second relative to the first along this axis.
        """
        return replace(self, axis=-self.axis)

    def wraps(self) -> bool:
        """
        :return: Whether angles are taken free of jumps between frames rather than
            within the limits: for a continuous joint, or limits spanning a full turn.
        """
        return (
            self.kind is JointKind.CONTINUOUS
            or self.lower is None
            or self.upper is None
            or self.upper - self.lower >= FULL_TURN
        )

    def values_of(self, relative: TransformTrack) -> numpy.ndarray:
        """
        :param relative: The child joint frame in the parent joint frame per frame.
        :return: The joint values best explaining the relative frames: the distance
            along, or the angle about, the axis. An angle is taken within the limits
            when they span less than a full turn, else without jumps between frames; a
            fixed joint stays at zero.
        """
        if not self.kind.movable:
            return numpy.zeros(relative.frame_count)
        if not self.kind.rotates:
            return relative.translations @ self.axis
        perpendicular = numpy.cross(
            self.axis, numpy.eye(SPACE_DIMENSIONS)[numpy.argmin(abs(self.axis))]
        )
        perpendicular /= numpy.linalg.norm(perpendicular)
        turned = relative.rotations @ perpendicular
        angles = numpy.arctan2(
            numpy.cross(perpendicular, turned) @ self.axis, turned @ perpendicular
        )
        if self.wraps():
            return numpy.unwrap(angles)
        middle = (self.lower + self.upper) / 2.0
        return angles - FULL_TURN * numpy.round((angles - middle) / FULL_TURN)

    def transforms(self, values: numpy.ndarray) -> TransformTrack:
        """
        :param values: The joint value per frame, in radians or metres.
        :return: The child joint frame relative to the parent joint frame per frame.
        """
        frame_count = len(values)
        if not self.kind.movable:
            return TransformTrack.constant(RigidTransform(), frame_count)
        if self.kind.rotates:
            return TransformTrack.of_parts(
                Rotation.from_rotvec(numpy.outer(values, self.axis)).as_matrix(),
                numpy.zeros((frame_count, SPACE_DIMENSIONS)),
            )
        return TransformTrack.of_parts(
            numpy.broadcast_to(
                numpy.eye(SPACE_DIMENSIONS),
                (frame_count, SPACE_DIMENSIONS, SPACE_DIMENSIONS),
            ),
            numpy.outer(values, self.axis),
        )

    def transform(self, value: float) -> RigidTransform:
        """
        :param value: A joint value in radians or metres.
        :return: The child joint frame relative to the parent joint frame at the value.
        """
        return self.transforms(numpy.array([value], dtype=float)).at_frame(0)


# %% joints


@dataclass(eq=False)
class Joint:
    """
    A joint between two links, in URDF terms: the child link frame is the parent link
    frame, then :attr:`origin`, then the joint motion.
    """

    name: str
    """
    The unique joint name, derived from the joint prim's path.
    """

    path: str
    """
    The USD path of the joint prim, or of the attached link for generated joints.
    """

    motion: AllowedMotion
    """
    How the child link moves.
    """

    parent: str = ""
    """
    The name of the parent link, empty until the joint is placed in the link tree.
    """

    child: str = ""
    """
    The name of the child link, empty until the joint is placed in the link tree.
    """

    origin: RigidTransform = field(default_factory=RigidTransform)
    """
    The joint frame in the parent link frame, at joint value zero.
    """

    initial_value: float = 0.0
    """
    The joint value recovered from the authored body poses.
    """

    enabled: bool = True
    """
    Whether the joint takes part in the simulation (``physics:jointEnabled``); a
    disabled joint still describes the mechanism but yields to an enabled joint of the
    same child body.
    """

    parent_body: Optional[str] = None
    """
    The USD path of the body the child body moves relative to (``physics:body0``), or
    None for the world.
    """

    child_body: Optional[str] = None
    """
    The USD path of the body the joint moves (``physics:body1``, or ``physics:body0``
    when the joint names no other body), or None for generated joints.
    """

    parent_body_to_joint: RigidTransform = field(default_factory=RigidTransform)
    """
    The joint frame relative to the rigid frame of the parent body (or the world).
    """

    child_body_to_joint: RigidTransform = field(default_factory=RigidTransform)
    """
    The joint frame relative to the rigid frame of the child body.
    """

    @property
    def movable(self) -> bool:
        """
        Whether the joint's value can change.
        """
        return self.motion.kind.movable

    @property
    def generated(self) -> bool:
        """
        Whether the converter made the joint up to attach a link without an authored
        joint.
        """
        return self.child_body is None

    def relative_motion(
        self, parent_body: TransformTrack, child_body: TransformTrack
    ) -> TransformTrack:
        """
        :param parent_body: The world poses of the parent body (identity for the world).
        :param child_body: The world poses of the child body.
        :return: The child joint frame relative to the parent joint frame, per frame.
        """
        return (parent_body @ self.parent_body_to_joint).inverse() @ (
            child_body @ self.child_body_to_joint
        )

    def value_between(
        self, parent_body_pose: RigidTransform, child_body_pose: RigidTransform
    ) -> float:
        """
        :param parent_body_pose: The world pose of the parent body (identity for the
            world).
        :param child_body_pose: The world pose of the child body.
        :return: The joint value that best explains the two poses, as
            :meth:`AllowedMotion.values_of` takes it.
        """
        relative = self.relative_motion(
            TransformTrack.constant(parent_body_pose, 1),
            TransformTrack.constant(child_body_pose, 1),
        )
        return float(self.motion.values_of(relative)[0])


# %% links


@dataclass(eq=False)
class LinkMesh:
    """
    The triangles of one geometry prim, or of one material subset of it, in the frame of
    the link it belongs to.
    """

    path: str
    """
    The USD path of the geometry prim.
    """

    geometry: TriangleMesh
    """
    The float32 positions, uint32 triangles and optional normals and texture coordinates
    (as USD authors them, origin bottom left) in the link frame.
    """

    material: str
    """
    The name of the material in :attr:`ConvertedStage.materials`.
    """

    double_sided: bool = False
    """
    Whether both sides of every triangle are visible.
    """


@dataclass(eq=False)
class Link:
    """
    One rigid part of the converted scene: a rigid body, a jointed part, or the static
    geometry of one asset.
    """

    name: str
    """
    The unique link name, derived from :attr:`path`.
    """

    path: str
    """
    The USD path of the prim the link stands for.
    """

    pose: RigidTransform
    """
    The link frame in the world at the stage's initial time.
    """

    prim_to_link: RigidTransform = field(default_factory=RigidTransform)
    """
    The link frame relative to the rigid part of the prim's own frame, which maps a
    world pose of the prim (from a recorded trace, for example) to the link pose.
    """

    meshes: List[LinkMesh] = field(default_factory=list)
    """
    The visual geometry, in the link frame.
    """

    free: bool = False
    """
    Whether the link moves with a rigid body that no joint connects to the world; it is
    attached at its authored pose by a fixed joint.
    """

    @property
    def triangle_count(self) -> int:
        """
        The number of triangles over all meshes of the link.
        """
        return sum(len(mesh.geometry.triangles) for mesh in self.meshes)

    @property
    def prim_pose(self) -> RigidTransform:
        """
        The rigid world pose of the prim the link stands for.
        """
        return self.pose @ self.prim_to_link.inverse()
