"""
How far one pose track strays from another, and how far it may.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from scipy.spatial.transform import Rotation
from typing_extensions import Self

from cramera_usd.geometry.transforms import TransformTrack

# %% tolerance


@dataclass(frozen=True)
class ResidualTolerance:
    """
    How far a replayed pose may stray from a recorded one.
    """

    distance: float = 0.001
    """
    The largest position error in metres.
    """

    angle: float = float(numpy.radians(0.1))
    """
    The largest orientation error in radians.
    """


# %% deviation


@dataclass(frozen=True, eq=False)
class PoseDeviation:
    """
    How far one pose track is from another, frame by frame.
    """

    distances: numpy.ndarray
    """
    The distance between the two origins per frame, in metres.
    """

    angles: numpy.ndarray
    """
    The angle of the rotation between the two orientations per frame, in radians.
    """

    @classmethod
    def between(cls, expected: TransformTrack, actual: TransformTrack) -> Self:
        """
        :param expected: The reference poses.
        :param actual: The poses compared with them.
        :return: The deviation of the poses from the reference.
        """
        relative = expected.inverse() @ actual
        return cls(
            numpy.linalg.norm(relative.translations, axis=1),
            Rotation.from_matrix(relative.rotations).magnitude(),
        )

    @property
    def largest_distance(self) -> float:
        """
        The largest distance over all frames.
        """
        return float(self.distances.max(initial=0.0))

    @property
    def largest_angle(self) -> float:
        """
        The largest angle over all frames.
        """
        return float(self.angles.max(initial=0.0))

    def worst_frame(self, tolerance: ResidualTolerance) -> int:
        """
        :param tolerance: The tolerance scaling distances and angles.
        :return: The frame deviating most, distances and angles each measured in units
            of their tolerance.
        """
        return int(
            numpy.argmax(
                numpy.maximum(
                    self.distances / tolerance.distance, self.angles / tolerance.angle
                )
            )
        )

    def within(self, tolerance: ResidualTolerance) -> bool:
        """
        :param tolerance: A tolerance.
        :return: Whether every frame lies within it.
        """
        return (
            self.largest_distance <= tolerance.distance
            and self.largest_angle <= tolerance.angle
        )
