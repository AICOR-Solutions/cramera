"""
Axis-aligned boxes around points.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from typing_extensions import Self

from cramera_protocol.geometry import Bounds, Vector3
from cramera_usd.geometry.transforms import SPACE_DIMENSIONS

# %% constants

PERCENT = 100.0
"""
A whole, in percent.
"""

# %% bounds


@dataclass(frozen=True, eq=False)
class PointBounds:
    """
    An axis-aligned box in metres.
    """

    minimum: numpy.ndarray
    """
    The corner with the smallest coordinates.
    """

    maximum: numpy.ndarray
    """
    The corner with the largest coordinates.
    """

    @classmethod
    def of_points(cls, points: numpy.ndarray) -> Self:
        """
        :param points: An ``(N, 3)`` array of positions.
        :return: The smallest box holding every point.
        """
        return cls(points.min(axis=0), points.max(axis=0))

    @classmethod
    def central(cls, points: numpy.ndarray, fraction: float) -> Self:
        """
        :param points: An ``(N, 3)`` array of positions.
        :param fraction: The share of points kept per axis, between 0 and 1.
        :return: The box holding the central fraction of the points along every axis,
            which leaves out sparse outliers such as a building shell around a dense
            interior.
        """
        cut = (1.0 - fraction) / 2.0 * PERCENT
        return cls(
            numpy.percentile(points, cut, axis=0),
            numpy.percentile(points, PERCENT - cut, axis=0),
        )

    @classmethod
    def around_origin(cls, half_size: float) -> Self:
        """
        :param half_size: Half the edge length in metres.
        :return: The cube of that size centred on the origin.
        """
        corner = numpy.full(SPACE_DIMENSIONS, half_size)
        return cls(-corner, corner)

    @property
    def center(self) -> numpy.ndarray:
        """
        The middle of the box.
        """
        return (self.minimum + self.maximum) / 2.0

    @property
    def diagonal(self) -> float:
        """
        The length of the box's diagonal.
        """
        return float(numpy.linalg.norm(self.maximum - self.minimum))

    def to_protocol(self, decimals: int) -> Bounds:
        """
        :param decimals: The number of decimals kept of each coordinate.
        :return: The box as the protocol writes it.
        """
        return Bounds(
            Vector3(*(round(float(value), decimals) for value in self.minimum)),
            Vector3(*(round(float(value), decimals) for value in self.maximum)),
        )
