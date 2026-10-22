"""
The lights and cameras authored on a stage, in metres with Z up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy
from typing_extensions import Optional, Tuple

from cramera_usd.geometry.transforms import SPACE_DIMENSIONS, RigidTransform

# %% vocabulary


class LightKind(StrEnum):
    """
    The UsdLux light types the converter reads, named as USD names them.
    """

    DISTANT = "DistantLight"
    """
    A light infinitely far away, such as the sun.
    """

    DOME = "DomeLight"
    """
    Light arriving from every direction of the surrounding sphere.
    """

    RECTANGLE = "RectLight"
    """
    A rectangular area light emitting along its negative Z axis.
    """

    DISK = "DiskLight"
    """
    A disk-shaped area light emitting along its negative Z axis.
    """

    SPHERE = "SphereLight"
    """
    A spherical light.
    """

    CYLINDER = "CylinderLight"
    """
    A cylindrical light.
    """

    @property
    def round(self) -> bool:
        """
        Whether the light's size is a radius.
        """
        return self in (LightKind.DISK, LightKind.SPHERE, LightKind.CYLINDER)


WHITE = (1.0, 1.0, 1.0)
"""
The linear colour of white light.
"""

Z_AXIS_COLUMN = SPACE_DIMENSIONS - 1
"""
The column of a rotation matrix holding the frame's Z axis.
"""


# %% lights


@dataclass(eq=False)
class StageLight:
    """
    A UsdLux light, in metres with Z up.
    """

    path: str
    """
    The USD path of the light prim.
    """

    kind: LightKind
    """
    The light type.
    """

    pose: RigidTransform
    """
    The light frame in the world; area lights emit along its negative Z axis.
    """

    intensity: float
    """
    The authored intensity scaled by two to the power of the authored exposure.
    """

    color: Tuple[float, float, float] = WHITE
    """
    The authored linear light colour.
    """

    color_temperature: Optional[float] = None
    """
    The colour temperature in kelvin, or None when the light does not use one.
    """

    width: float = 0.0
    """
    The width of a rectangle light in metres.
    """

    height: float = 0.0
    """
    The height of a rectangle light in metres.
    """

    radius: float = 0.0
    """
    The radius of a disk, sphere or cylinder light in metres.
    """

    angle: float = 0.0
    """
    The angular diameter of a distant light in degrees.
    """

    @property
    def emission_direction(self) -> numpy.ndarray:
        """
        The direction the light travels in, the negative Z axis of its frame.
        """
        return -self.pose.rotation[:, Z_AXIS_COLUMN]


# %% cameras


@dataclass(eq=False)
class StageCamera:
    """
    A camera authored on the stage.
    """

    path: str
    """
    The USD path of the camera prim.
    """

    pose: RigidTransform
    """
    The camera frame in the world; the camera looks along its negative Z axis with its Y
    axis up.
    """

    vertical_field_of_view: float
    """
    The vertical field of view in degrees, from the focal length and the vertical
    aperture.
    """

    @property
    def forward(self) -> numpy.ndarray:
        """
        The viewing direction.
        """
        return -self.pose.rotation[:, Z_AXIS_COLUMN]
