"""
NVIDIA's OmniGlass material mapped onto glTF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Dict

from cramera_usd.materials.channels import ScalarChannel
from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.mapping import RoughnessMetallicPacking, ShaderMapping
from cramera_usd.materials.physically_based import (
    WHITE,
    AlphaMode,
    LinearColor,
    PhysicallyBasedMaterial,
)
from cramera_usd.scene.materials import ShaderInputValue

# %% inputs


class OmniGlassInput(StrEnum):
    """
    The OmniGlass inputs the mapping knows: those it reads, and those glTF cannot
    express that it may leave out at a neutral value.
    """

    COLOR = "glass_color"
    """
    The tint of the glass.
    """

    COLOR_TEXTURE = "glass_color_texture"
    """
    The tint texture.
    """

    USE_COLOR_TEXTURE = "use_glass_color_texture"
    """
    A hidden switch OmniGlass V2 ignores: it uses the tint texture whenever one is set.
    """

    INDEX_OF_REFRACTION = "glass_ior"
    """
    The index of refraction.
    """

    FROSTING = "frosting_roughness"
    """
    The roughness of the glass.
    """

    ROUGHNESS_TEXTURE = "roughness_texture"
    """
    The roughness texture.
    """

    ROUGHNESS_INFLUENCE = "roughness_texture_influence"
    """
    How much the roughness texture replaces the frosting.
    """

    NORMAL_TEXTURE = "normal_map_texture"
    """
    The normal map.
    """

    NORMAL_STRENGTH = "normal_map_strength"
    """
    The strength of the normal map.
    """

    THIN_WALLED = "thin_walled"
    """
    Whether the glass is a thin shell without an inside.
    """

    DEPTH = "depth"
    """
    The absorption coefficient of the glass volume.
    """

    REFLECTION_COLOR = "reflection_color"
    """
    The tint of the reflection.
    """

    ENABLE_OPACITY = "enable_opacity"
    """
    Whether the surface is cut out by its opacity.
    """

    CUTOUT_OPACITY = "cutout_opacity"
    """
    The opacity of the cut out.
    """

    TEXTURE_ROTATE = "texture_rotate"
    """
    Turns the texture coordinates.
    """


# %% mapping


@dataclass
class OmniGlassMapping(ShaderMapping):
    """
    OmniGlass: a fully transmissive, blended, double-sided surface tinted with the glass
    colour, or with the glass colour texture which replaces it; frosting becomes
    roughness.
    """

    index_of_refraction: float = 1.491
    """
    OmniGlass's default ``glass_ior``.
    """

    glass_color: LinearColor = WHITE
    """
    OmniGlass's default ``glass_color``.
    """

    neutral_inputs: Dict[str, ShaderInputValue] = field(
        default_factory=lambda: {
            OmniGlassInput.USE_COLOR_TEXTURE: True,
            OmniGlassInput.THIN_WALLED: False,
            OmniGlassInput.DEPTH: 0.001,
            OmniGlassInput.REFLECTION_COLOR: WHITE,
            OmniGlassInput.ENABLE_OPACITY: False,
            OmniGlassInput.CUTOUT_OPACITY: 1.0,
            OmniGlassInput.TEXTURE_ROTATE: 0.0,
        }
    )
    """
    Inputs the glTF model cannot express but that are harmless at these values.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        input_name = OmniGlassInput
        color = inputs.textured_color(
            input_name.COLOR, input_name.COLOR_TEXTURE, self.glass_color
        )
        return RoughnessMetallicPacking(
            ScalarChannel(
                inputs.number(input_name.FROSTING, 0.0),
                inputs.texture(input_name.ROUGHNESS_TEXTURE),
                inputs.number(input_name.ROUGHNESS_INFLUENCE, 1.0),
            ),
            ScalarChannel(0.0),
        ).apply(
            PhysicallyBasedMaterial(
                name="",
                base_color_factor=(*color.factor, 1.0),
                base_color_texture=color.texture,
                normal_texture=inputs.texture(input_name.NORMAL_TEXTURE),
                normal_scale=inputs.number(input_name.NORMAL_STRENGTH, 1.0),
                transmission=1.0,
                index_of_refraction=inputs.number(
                    input_name.INDEX_OF_REFRACTION, self.index_of_refraction
                ),
                alpha_mode=AlphaMode.BLEND,
                double_sided=True,
            )
        )
