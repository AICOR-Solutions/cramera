"""
Rigid transforms (rotation and translation, no scale) as homogeneous 4x4 matrices acting
on column vectors, alone or one per frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy
from scipy.spatial.transform import Rotation
from typing_extensions import List, Optional, Self, Union

from cramera_protocol.geometry import Pose

# %% constants

HOMOGENEOUS_SIZE = 4
"""
The size of a homogeneous transform matrix.
"""

SPACE_DIMENSIONS = 3
"""
The number of spatial dimensions.
"""

CLOSENESS_TOLERANCE = 1e-6
"""
The largest difference of a matrix entry for two transforms to count as equal.
"""

EULER_AXES = "xyz"
"""
The fixed axes of URDF's roll, pitch and yaw, in the order they turn.
"""

FULL_TURN = 2.0 * numpy.pi
"""
One full turn in radians.
"""

NEGATIVE_ZERO_REMOVAL = 0.0
"""
Added to values written out, which turns ``-0.0`` into ``0.0``.
"""

# %% single transforms


@dataclass(frozen=True, eq=False)
class RigidTransform:
    """
    A rigid transform as a homogeneous 4x4 matrix acting on column vectors.
    """

    matrix: numpy.ndarray = field(default_factory=lambda: numpy.eye(HOMOGENEOUS_SIZE))
    """
    The homogeneous 4x4 matrix.
    """

    @classmethod
    def rigid_part(cls, matrix: numpy.ndarray) -> Self:
        """
        :param matrix: A homogeneous 4x4 affine matrix acting on column vectors.
        :return: Its rotation and translation, with scale and shear removed.
        """
        return cls(
            TransformTrack.rigid_part(
                numpy.asarray(matrix, dtype=float)[None]
            ).matrices[0]
        )

    @classmethod
    def from_translation_quaternion(
        cls, translation: numpy.ndarray, quaternion: numpy.ndarray
    ) -> Self:
        """
        :param translation: The translation in metres.
        :param quaternion: The rotation as ``[x, y, z, w]``.
        :return: The transform.
        """
        return cls.from_parts(Rotation.from_quat(quaternion).as_matrix(), translation)

    @classmethod
    def from_rotation(cls, rotation: numpy.ndarray) -> Self:
        """
        :param rotation: A 3x3 rotation matrix.
        :return: The pure rotation.
        """
        return cls.from_parts(rotation, numpy.zeros(SPACE_DIMENSIONS))

    @classmethod
    def from_translation(cls, translation: numpy.ndarray) -> Self:
        """
        :param translation: The translation in metres.
        :return: The pure translation.
        """
        return cls.from_parts(numpy.eye(SPACE_DIMENSIONS), translation)

    @classmethod
    def from_parts(cls, rotation: numpy.ndarray, translation: numpy.ndarray) -> Self:
        """
        :param rotation: A 3x3 rotation matrix.
        :param translation: The translation in metres.
        :return: The transform rotating, then translating.
        """
        result = numpy.eye(HOMOGENEOUS_SIZE)
        result[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = rotation
        result[:SPACE_DIMENSIONS, SPACE_DIMENSIONS] = translation
        return cls(result)

    @property
    def translation(self) -> numpy.ndarray:
        """
        The translation in metres.
        """
        return self.matrix[:SPACE_DIMENSIONS, SPACE_DIMENSIONS].copy()

    @property
    def rotation(self) -> numpy.ndarray:
        """
        The 3x3 rotation matrix.
        """
        return self.matrix[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS].copy()

    @property
    def roll_pitch_yaw(self) -> numpy.ndarray:
        """
        The rotation as fixed-axis roll, pitch and yaw in radians, as URDF origins use.
        """
        return Rotation.from_matrix(self.rotation).as_euler(EULER_AXES)

    def inverse(self) -> RigidTransform:
        """
        :return: The transform undoing this one.
        """
        return TransformTrack.constant(self, 1).inverse().at_frame(0)

    def to_protocol(self) -> Pose:
        """
        :return: The transform as the protocol writes a pose.
        """
        return TransformTrack.constant(self, 1).poses()[0]

    def __matmul__(self, other: RigidTransform) -> RigidTransform:
        """
        :param other: A transform relative to this transform's frame.
        :return: ``other`` relative to the frame this transform is relative to.
        """
        return RigidTransform(self.matrix @ other.matrix)

    def is_close(
        self, other: RigidTransform, tolerance: float = CLOSENESS_TOLERANCE
    ) -> bool:
        """
        :param other: The transform to compare with.
        :param tolerance: The largest allowed difference of a matrix entry.
        :return: Whether both transforms agree up to the tolerance.
        """
        return bool(numpy.allclose(self.matrix, other.matrix, atol=tolerance))


# %% one transform per frame


@dataclass(frozen=True, eq=False)
class TransformTrack:
    """
    One rigid transform per frame, as ``(frames, 4, 4)`` matrices acting on column
    vectors.
    """

    matrices: numpy.ndarray
    """
    The homogeneous matrix of every frame.
    """

    @classmethod
    def constant(cls, transform: RigidTransform, frame_count: int) -> Self:
        """
        :param transform: The transform.
        :param frame_count: The number of frames.
        :return: The same transform at every frame.
        """
        return cls(
            numpy.broadcast_to(
                transform.matrix, (frame_count, HOMOGENEOUS_SIZE, HOMOGENEOUS_SIZE)
            )
        )

    @classmethod
    def of_parts(cls, rotations: numpy.ndarray, translations: numpy.ndarray) -> Self:
        """
        :param rotations: ``(frames, 3, 3)`` rotation matrices.
        :param translations: ``(frames, 3)`` translations in metres.
        :return: The transforms made of a rotation and a translation per frame.
        """
        matrices = numpy.zeros((len(translations), HOMOGENEOUS_SIZE, HOMOGENEOUS_SIZE))
        matrices[:, :SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = rotations
        matrices[:, :SPACE_DIMENSIONS, SPACE_DIMENSIONS] = translations
        matrices[:, SPACE_DIMENSIONS, SPACE_DIMENSIONS] = 1.0
        return cls(matrices)

    @classmethod
    def of_positions(cls, positions: numpy.ndarray, quaternions: numpy.ndarray) -> Self:
        """
        :param positions: ``(frames, 3)`` positions in metres.
        :param quaternions: ``(frames, 4)`` orientations as ``[x, y, z, w]``, which
            need not be exactly unit length.
        :return: The transforms to those positions and orientations.
        """
        return cls.of_parts(Rotation.from_quat(quaternions).as_matrix(), positions)

    @classmethod
    def rigid_part(cls, matrices: numpy.ndarray) -> Self:
        """
        :param matrices: ``(frames, 4, 4)`` affine matrices acting on column vectors.
        :return: Their rotations and translations, with scale and shear removed; a
            mirroring matrix keeps the proper rotation nearest to it.
        """
        left, _, right = numpy.linalg.svd(
            matrices[:, :SPACE_DIMENSIONS, :SPACE_DIMENSIONS]
        )
        mirrored = numpy.linalg.det(left @ right) < 0
        left[mirrored, :, -1] *= -1
        return cls.of_parts(
            left @ right, matrices[:, :SPACE_DIMENSIONS, SPACE_DIMENSIONS]
        )

    def __matmul__(
        self, other: Union[TransformTrack, RigidTransform]
    ) -> TransformTrack:
        """
        :param other: A track of as many frames, or one transform for every frame,
            relative to this track's frame.
        :return: ``other`` per frame, relative to the frame this track is relative
            to.
        """
        if isinstance(other, TransformTrack):
            return TransformTrack(self.matrices @ other.matrices)
        return TransformTrack(self.matrices @ other.matrix)

    @property
    def frame_count(self) -> int:
        """
        The number of frames.
        """
        return len(self.matrices)

    @property
    def rotations(self) -> numpy.ndarray:
        """
        The ``(frames, 3, 3)`` rotation matrices.
        """
        return self.matrices[:, :SPACE_DIMENSIONS, :SPACE_DIMENSIONS]

    @property
    def translations(self) -> numpy.ndarray:
        """
        The ``(frames, 3)`` translations in metres.
        """
        return self.matrices[:, :SPACE_DIMENSIONS, SPACE_DIMENSIONS]

    def inverse(self) -> TransformTrack:
        """
        :return: The transforms undoing these, frame by frame.
        """
        rotations = numpy.swapaxes(self.rotations, 1, 2)
        return TransformTrack.of_parts(
            rotations, -(rotations @ self.translations[:, :, None])[:, :, 0]
        )

    def at(self, frames: numpy.ndarray) -> TransformTrack:
        """
        :param frames: Frame indices.
        :return: The transforms of those frames.
        """
        return TransformTrack(self.matrices[frames])

    def at_frame(self, frame: int) -> RigidTransform:
        """
        :param frame: A frame index.
        :return: The transform of that frame.
        """
        return RigidTransform(numpy.array(self.matrices[frame]))

    def translation_quaternions(
        self, decimals: Optional[int] = None
    ) -> List[List[float]]:
        """
        :param decimals: The number of decimals kept, or None to keep them all.
        :return: Every transform as ``[x, y, z, qx, qy, qz, qw]``.
        """
        quaternions = Rotation.from_matrix(self.rotations).as_quat()
        values = numpy.concatenate([self.translations, quaternions], axis=1)
        if decimals is not None:
            values = numpy.round(values, decimals)
        return (values + NEGATIVE_ZERO_REMOVAL).tolist()

    def poses(self, decimals: Optional[int] = None) -> List[Pose]:
        """
        :param decimals: The number of decimals kept, or None to keep them all.
        :return: Every transform as the protocol writes a pose.
        """
        return [Pose(*values) for values in self.translation_quaternions(decimals)]
