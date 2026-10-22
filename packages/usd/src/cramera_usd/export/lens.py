"""
The vertical field of view of the twin's render camera, which the viewer keeps.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

# %% constants

HORIZONTAL_APERTURE = 36.0
"""
The horizontal aperture of the twin's render camera in millimetres.
"""

DEFAULT_RENDER_WIDTH = 1920
"""
The width of the twin's final renders in pixels.
"""

DEFAULT_RENDER_HEIGHT = 1200
"""
The height of the twin's final renders in pixels.
"""

FIELD_OF_VIEW_DECIMALS = 2
"""
The decimals kept of the field of view.
"""

# %% lens


@dataclass(frozen=True)
class RenderLens:
    """
    The lens of a render view: a focal length on the render camera's aperture, at the
    size the view is rendered.
    """

    focal_length: float
    """
    The focal length in millimetres.
    """

    width: int = DEFAULT_RENDER_WIDTH
    """
    The width the view is rendered at, in pixels.
    """

    height: int = DEFAULT_RENDER_HEIGHT
    """
    The height the view is rendered at, in pixels.
    """

    def vertical_field_of_view(self) -> float:
        """
        :return: The vertical field of view in degrees: the vertical aperture is the
            horizontal one scaled by the render's aspect, ``2 * atan((36 * H / W) / (2
            * focal))``.
        """
        vertical_aperture = HORIZONTAL_APERTURE * self.height / self.width
        return round(
            2.0
            * float(
                numpy.degrees(
                    numpy.arctan(vertical_aperture / (2.0 * self.focal_length))
                )
            ),
            FIELD_OF_VIEW_DECIMALS,
        )
