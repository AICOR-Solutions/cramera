"""
Geometry without a material, and shaders no mapping understands.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.mapping import ShaderMapping
from cramera_usd.materials.physically_based import (
    DEFAULT_ROUGHNESS,
    AlphaMode,
    LinearColor,
    PhysicallyBasedMaterial,
)
from cramera_usd.scene.materials import AuthoredMaterial

# %% display colour


class DisplayColorInput(StrEnum):
    """
    The geometry primvars that shade a prim without a bound material.
    """

    COLOR = "displayColor"
    """
    The colour primvar.
    """

    OPACITY = "displayOpacity"
    """
    The opacity primvar.
    """


@dataclass
class DisplayColorMapping(ShaderMapping):
    """
    Geometry without a material: its display colour, or USD's fallback grey.
    """

    fallback_color: LinearColor = (0.5, 0.5, 0.5)
    """
    The colour Hydra draws geometry with that has neither material nor display colour.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        opacity = inputs.number(DisplayColorInput.OPACITY, 1.0)
        return PhysicallyBasedMaterial(
            name="",
            base_color_factor=(
                *inputs.color(DisplayColorInput.COLOR, self.fallback_color),
                opacity,
            ),
            alpha_mode=AlphaMode.BLEND if opacity < 1.0 else AlphaMode.OPAQUE,
        )


# %% unknown shaders


@dataclass
class UnknownShaderMapping(ShaderMapping):
    """
    A shader no mapping understands: drawn in a colour nobody would author, so it is
    noticed, with every input reported.
    """

    warning_color: LinearColor = (1.0, 0.0, 1.0)
    """
    Magenta.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        return PhysicallyBasedMaterial(
            name="",
            base_color_factor=(*self.warning_color, 1.0),
            roughness_factor=DEFAULT_ROUGHNESS,
        )

    def map(self, material: AuthoredMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: An authored material.
        :return: The warning material, listing the shader's identifier first among the
            unmapped inputs.
        """
        mapped = super().map(material)
        return replace(
            mapped,
            unmapped_inputs=(material.shader_identifier, *mapped.unmapped_inputs),
        )
