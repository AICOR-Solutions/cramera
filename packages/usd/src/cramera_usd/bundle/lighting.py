"""
The lights of a converted stage as ``lighting.json`` describes them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from typing_extensions import List, Optional

from cramera_protocol.bundle.lighting import Dome, Lighting, Panel, Sun
from cramera_protocol.geometry import Vector3
from cramera_usd.bundle.layout import Decimals
from cramera_usd.geometry.transforms import NEGATIVE_ZERO_REMOVAL
from cramera_usd.scene.lights import LightKind, StageLight

# %% lighting


@dataclass
class LightingSummary:
    """
    The brightest sun, the brightest dome and every rectangle light of a stage, with
    directions the way the light travels in the bundle frame.
    """

    lights: List[StageLight]
    """
    The stage's lights.
    """

    def brightest(self, kind: LightKind) -> Optional[StageLight]:
        """
        :param kind: A light kind.
        :return: The brightest light of that kind, or None.
        """
        candidates = [light for light in self.lights if light.kind is kind]
        return max(candidates, key=lambda light: light.intensity, default=None)

    def to_protocol(self) -> Lighting:
        """
        :return: The content of ``lighting.json``.
        """
        sun = self.brightest(LightKind.DISTANT)
        dome = self.brightest(LightKind.DOME)
        return Lighting(
            sun=None if sun is None else self.sun(sun),
            dome=(
                None
                if dome is None
                else Dome(color=Vector3(*dome.color), intensity=dome.intensity)
            ),
            panels=[
                self.panel(light)
                for light in self.lights
                if light.kind is LightKind.RECTANGLE
            ],
        )

    def sun(self, light: StageLight) -> Sun:
        """
        :param light: A distant light.
        :return: It as the sun.
        """
        return Sun(
            direction=self.rounded(light.emission_direction),
            intensity=light.intensity,
            color=Vector3(*light.color),
            color_temperature=light.color_temperature,
        )

    def panel(self, light: StageLight) -> Panel:
        """
        :param light: A rectangle light.
        :return: It as a ceiling panel.
        """
        return Panel(
            center=self.rounded(light.pose.translation),
            normal=self.rounded(light.emission_direction),
            width=round(light.width, Decimals.POSITION),
            height=round(light.height, Decimals.POSITION),
            intensity=light.intensity,
            color=Vector3(*light.color),
            color_temperature=light.color_temperature,
        )

    @staticmethod
    def rounded(vector: numpy.ndarray) -> Vector3:
        """
        :param vector: A position or direction.
        :return: The vector rounded to a tenth of a millimetre, without negative zeros.
        """
        return Vector3(
            *(
                round(float(value), Decimals.POSITION) + NEGATIVE_ZERO_REMOVAL
                for value in vector
            )
        )
