"""
The coordinate axes, named as USD names them.
"""

from __future__ import annotations

from enum import StrEnum

import numpy

from cramera_usd.geometry.transforms import SPACE_DIMENSIONS

# %% axes


class Axis(StrEnum):
    """
    The axis a round implicit shape is built around, named as USD names it.
    """

    X = "X"
    """
    The X axis.
    """

    Y = "Y"
    """
    The Y axis.
    """

    Z = "Z"
    """
    The Z axis.
    """

    def rotation_from_z(self) -> numpy.ndarray:
        """
        :return: The proper rotation taking the Z axis onto this axis.
        """
        return {
            Axis.X: numpy.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
            Axis.Y: numpy.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]),
            Axis.Z: numpy.eye(SPACE_DIMENSIONS),
        }[self]

    @property
    def index(self) -> int:
        """
        The index of the axis among the coordinates.
        """
        return list(Axis).index(self)

    @property
    def direction(self) -> numpy.ndarray:
        """
        The unit vector along the axis.
        """
        return numpy.eye(SPACE_DIMENSIONS)[self.index]
