"""
The lights of a converted stage, ``lighting.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.geometry import Vector3

# %% lights


class LightKey(StrEnum):
    """
    The keys of the lights in ``lighting.json``.
    """

    DIRECTION = "direction"
    """
    The direction the light travels.
    """

    INTENSITY = "intensity"
    """
    The light's intensity as the stage authored it.
    """

    COLOR = "color"
    """
    The light's linear RGB colour.
    """

    COLOR_TEMPERATURE = "colorTemperature"
    """
    The light's colour temperature in kelvin.
    """

    CENTER = "center"
    """
    The centre of a rectangle light.
    """

    NORMAL = "normal"
    """
    The direction a rectangle light shines.
    """

    WIDTH = "width"
    """
    The width of a rectangle light.
    """

    HEIGHT = "height"
    """
    The height of a rectangle light.
    """


@dataclass(kw_only=True)
class Sun(JsonDocument):
    """
    The brightest distant light of a stage.
    """

    direction: Vector3 = document_field(LightKey.DIRECTION)
    """
    The direction the light travels, in the bundle frame.
    """

    intensity: float = document_field(LightKey.INTENSITY)
    """
    The light's intensity as the stage authored it.
    """

    color: Vector3 = document_field(LightKey.COLOR)
    """
    The light's linear RGB colour.
    """

    color_temperature: Optional[float] = document_field(
        LightKey.COLOR_TEMPERATURE, default=None
    )
    """
    The light's colour temperature in kelvin, when the stage enables it.
    """


@dataclass(kw_only=True)
class Dome(JsonDocument):
    """
    The brightest dome light of a stage.
    """

    color: Vector3 = document_field(LightKey.COLOR)
    """
    The light's linear RGB colour.
    """

    intensity: float = document_field(LightKey.INTENSITY)
    """
    The light's intensity as the stage authored it.
    """


@dataclass(kw_only=True)
class Panel(JsonDocument):
    """
    One rectangle light of a stage.
    """

    center: Vector3 = document_field(LightKey.CENTER)
    """
    The centre of the rectangle in metres.
    """

    normal: Vector3 = document_field(LightKey.NORMAL)
    """
    The direction the rectangle shines.
    """

    width: float = document_field(LightKey.WIDTH)
    """
    The width of the rectangle in metres.
    """

    height: float = document_field(LightKey.HEIGHT)
    """
    The height of the rectangle in metres.
    """

    intensity: float = document_field(LightKey.INTENSITY)
    """
    The light's intensity as the stage authored it.
    """

    color: Vector3 = document_field(LightKey.COLOR)
    """
    The light's linear RGB colour.
    """

    color_temperature: Optional[float] = document_field(
        LightKey.COLOR_TEMPERATURE, default=None
    )
    """
    The light's colour temperature in kelvin, when the stage enables it.
    """


class LightingKey(StrEnum):
    """
    The keys of ``lighting.json``.
    """

    SUN = "sun"
    """
    The brightest distant light.
    """

    DOME = "dome"
    """
    The brightest dome light.
    """

    PANELS = "panels"
    """
    Every rectangle light.
    """


@dataclass(kw_only=True)
class Lighting(JsonDocument):
    """
    The content of ``lighting.json``.
    """

    sun: Optional[Sun] = document_field(LightingKey.SUN, default=None)
    """
    The brightest distant light, or None for a stage without one.
    """

    dome: Optional[Dome] = document_field(LightingKey.DOME, default=None)
    """
    The brightest dome light, or None for a stage without one.
    """

    panels: List[Panel] = document_field(LightingKey.PANELS, default_factory=list)
    """
    Every rectangle light.
    """
