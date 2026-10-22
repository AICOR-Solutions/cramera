"""
Emitted light as glTF describes it: a colour within the unit range and a strength.
"""

from __future__ import annotations

from dataclasses import dataclass

from cramera_usd.materials.physically_based import LinearColor

# %% constants

SMALLEST_BRIGHTNESS = 1e-9
"""
The brightest component assumed for a black emission colour, which avoids dividing by
zero.
"""

# %% emission


@dataclass(frozen=True)
class Emission:
    """
    Emitted light as a glTF material describes it.
    """

    factor: LinearColor
    """
    The linear emissive colour, each component at most one.
    """

    strength: float
    """
    The factor scaling the emissive colour, ``KHR_materials_emissive_strength``.
    """


@dataclass
class EmissionScale:
    """
    Converts an MDL emission intensity (in nits) into glTF's emissive factor and
    ``KHR_materials_emissive_strength``: the emitted colour is the authored colour times
    ``intensity / reference``, with the part above one moved into the strength.
    """

    reference_intensity: float = 1000.0
    """
    The MDL emission intensity shown as the plain emissive colour.
    """

    def emission(self, color: LinearColor, intensity: float) -> Emission:
        """
        :param color: The authored linear emission colour.
        :param intensity: The authored emission intensity.
        :return: The glTF emission.
        """
        ratio = max(intensity, 0.0) / self.reference_intensity
        brightest = max(max(color), SMALLEST_BRIGHTNESS)
        scale = min(ratio, 1.0 / brightest)
        return Emission(
            tuple(min(component * scale, 1.0) for component in color),
            max(ratio / scale, 1.0) if scale > 0.0 else 1.0,
        )
