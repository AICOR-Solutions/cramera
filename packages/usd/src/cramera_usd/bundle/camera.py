"""
The view a converted scene opens with.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy
from typing_extensions import Optional, Self, Tuple

from cramera_protocol.bundle.scene import Camera
from cramera_protocol.geometry import Vector3
from cramera_usd.bundle.layout import Decimals
from cramera_usd.geometry.bounds import PointBounds
from cramera_usd.scene.lights import StageCamera

# %% constants

DEFAULT_FIELD_OF_VIEW = 50.0
"""
The vertical field of view in degrees of a camera that names none.
"""

VIEW_DIRECTION = (-0.55, -0.75, 0.45)
"""
The direction from the target towards a framing camera: from the front left and above.
"""

MINIMUM_FAR = 50.0
"""
The smallest far clipping distance of a framing camera, in metres.
"""

MINIMUM_TARGET_DISTANCE = 1.0
"""
The smallest distance in metres from an authored camera to the point it looks at.
"""

SCENE_DEPTH_FACTOR = 2.0
"""
How many scene diagonals the far plane lies away.
"""

# %% camera


@dataclass
class SceneCamera:
    """
    The viewer's initial camera.
    """

    position: numpy.ndarray
    """
    Where the camera stands, in metres.
    """

    target: numpy.ndarray
    """
    The point the camera looks at, in metres.
    """

    field_of_view: float = DEFAULT_FIELD_OF_VIEW
    """
    The vertical field of view in degrees.
    """

    far: Optional[float] = None
    """
    The far clipping distance in metres, or None for the framing's.
    """

    @classmethod
    def framing(
        cls,
        focus: PointBounds,
        scene: PointBounds,
        view_from: Tuple[float, float, float] = VIEW_DIRECTION,
    ) -> Self:
        """
        :param focus: The box to frame.
        :param scene: The box holding all geometry.
        :param view_from: The direction from the target towards the camera.
        :return: A camera seeing the whole focus box, with a far plane beyond the whole
            scene.
        """
        direction = numpy.asarray(view_from) / numpy.linalg.norm(view_from)
        half_angle = numpy.radians(DEFAULT_FIELD_OF_VIEW) / 2.0
        return cls(
            position=focus.center
            + direction * (focus.diagonal / 2.0) / numpy.tan(half_angle),
            target=focus.center,
            far=max(SCENE_DEPTH_FACTOR * scene.diagonal, MINIMUM_FAR),
        )

    @classmethod
    def of_camera(cls, camera: StageCamera, focus: PointBounds) -> Self:
        """
        :param camera: A camera authored on the stage.
        :param focus: The box the scene's geometry is densest in.
        :return: The camera's view, looking at the point of its viewing ray closest to
            the centre of the focus box.
        """
        position = camera.pose.translation
        distance = max(
            float((focus.center - position) @ camera.forward), MINIMUM_TARGET_DISTANCE
        )
        return cls(
            position,
            position + camera.forward * distance,
            camera.vertical_field_of_view,
        )

    def with_far(self, far: float) -> SceneCamera:
        """
        :param far: A far clipping distance in metres.
        :return: This camera, with that far plane unless it has its own.
        """
        if self.far is not None:
            return self
        return replace(self, far=far)

    def to_protocol(self) -> Camera:
        """
        :return: The ``camera`` entry of ``scene.json``.
        """
        return Camera(
            position=self.rounded(self.position),
            target=self.rounded(self.target),
            field_of_view=round(float(self.field_of_view), Decimals.FIELD_OF_VIEW),
            far=round(float(self.far), Decimals.CLIP_DISTANCE),
        )

    @staticmethod
    def rounded(point: numpy.ndarray) -> Vector3:
        """
        :param point: A point in metres.
        :return: The point rounded to a tenth of a millimetre.
        """
        return Vector3(*(round(float(value), Decimals.POSITION) for value in point))
