"""
NVIDIA's OmniSurface material mapped onto glTF.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from typing_extensions import Dict

from cramera_usd.materials.channels import ScalarChannel
from cramera_usd.materials.emission import EmissionScale
from cramera_usd.materials.inputs import ShaderInputs, TexturedColor
from cramera_usd.materials.mapping import RoughnessMetallicPacking, ShaderMapping
from cramera_usd.materials.physically_based import (
    DEFAULT_INDEX_OF_REFRACTION,
    WHITE,
    AlphaMode,
    LinearColor,
    PhysicallyBasedMaterial,
)
from cramera_usd.scene.materials import ShaderInputValue

# %% inputs


class OmniSurfaceInput(StrEnum):
    """
    The OmniSurface inputs the mapping knows: those it reads, and those glTF cannot
    express that it may leave out at a neutral value.
    """

    DIFFUSE_WEIGHT = "diffuse_reflection_weight"
    """
    Scales the diffuse colour.
    """

    DIFFUSE_COLOR = "diffuse_reflection_color"
    """
    The diffuse colour.
    """

    DIFFUSE_IMAGE = "diffuse_reflection_color_image"
    """
    The diffuse colour texture.
    """

    METALNESS = "metalness"
    """
    The metalness.
    """

    METALNESS_IMAGE = "metalness_image"
    """
    The metalness texture.
    """

    ROUGHNESS = "specular_reflection_roughness"
    """
    The specular roughness.
    """

    ROUGHNESS_IMAGE = "specular_reflection_roughness_image"
    """
    The specular roughness texture.
    """

    ANISOTROPY = "specular_reflection_anisotropy"
    """
    The anisotropy of the specular reflection.
    """

    INDEX_OF_REFRACTION = "specular_reflection_ior"
    """
    The index of refraction of the specular layer.
    """

    COAT_WEIGHT = "coat_weight"
    """
    The strength of the coat layer.
    """

    COAT_ROUGHNESS = "coat_roughness"
    """
    The roughness of the coat layer.
    """

    ENABLE_TRANSMISSION = "enable_specular_transmission"
    """
    Whether light passes through the surface.
    """

    TRANSMISSION_WEIGHT = "specular_transmission_weight"
    """
    The share of light passing through.
    """

    TRANSMISSION_COLOR = "specular_transmission_color"
    """
    The tint of the light passing through.
    """

    TRANSMISSION_COLOR_IMAGE = "specular_transmission_color_image"
    """
    The tint texture of the light passing through.
    """

    EMISSION_WEIGHT = "emission_weight"
    """
    The strength of the emission.
    """

    EMISSION_COLOR = "emission_color"
    """
    The emitted colour.
    """

    EMISSION_INTENSITY = "emission_intensity"
    """
    The emitted luminance.
    """

    NORMAL_IMAGE = "geometry_normal_image"
    """
    The normal map.
    """

    ENABLE_OPACITY = "enable_opacity"
    """
    Whether the surface is partly transparent.
    """

    OPACITY = "geometry_opacity"
    """
    The opacity.
    """

    DIFFUSE_ROUGHNESS = "diffuse_reflection_roughness"
    """
    The roughness of the diffuse reflection.
    """

    SPECULAR_WEIGHT = "specular_reflection_weight"
    """
    The strength of the specular reflection.
    """

    SPECULAR_COLOR = "specular_reflection_color"
    """
    The tint of the specular reflection.
    """

    ANISOTROPY_ROTATION = "specular_reflection_anisotropy_rotation"
    """
    Turns the direction of the anisotropic reflection.
    """

    SUBSURFACE_WEIGHT = "subsurface_weight"
    """
    The share of light scattered below the surface.
    """

    COAT_COLOR = "coat_color"
    """
    The tint of the coat layer.
    """

    COAT_INDEX_OF_REFRACTION = "coat_ior"
    """
    The index of refraction of the coat layer.
    """

    THIN_WALLED = "thin_walled"
    """
    Whether the surface is a thin shell without an inside.
    """


# %% mapping


@dataclass
class OmniSurfaceMapping(ShaderMapping):
    """
    OmniSurface: the base colour is the diffuse colour (or image) times the diffuse
    weight, mixed with the transmission colour (or image) by the transmission weight;
    images replace their constants, and of two images the one with the larger weight is
    kept.
    """

    diffuse_weight: float = 0.8
    """
    OmniSurface's default ``diffuse_reflection_weight``.
    """

    diffuse_color: LinearColor = WHITE
    """
    OmniSurface's default ``diffuse_reflection_color``.
    """

    transmission_color: LinearColor = WHITE
    """
    OmniSurface's default ``specular_transmission_color``.
    """

    roughness: float = 0.2
    """
    OmniSurface's default ``specular_reflection_roughness``.
    """

    coat_roughness: float = 0.1
    """
    OmniSurface's default ``coat_roughness``.
    """

    emission: EmissionScale = field(default_factory=EmissionScale)
    """
    The conversion of emission intensities.
    """

    neutral_inputs: Dict[str, ShaderInputValue] = field(
        default_factory=lambda: {
            OmniSurfaceInput.DIFFUSE_ROUGHNESS: 0.0,
            OmniSurfaceInput.SPECULAR_WEIGHT: 1.0,
            OmniSurfaceInput.SPECULAR_COLOR: WHITE,
            OmniSurfaceInput.ANISOTROPY_ROTATION: 0.0,
            OmniSurfaceInput.SUBSURFACE_WEIGHT: 0.0,
            OmniSurfaceInput.COAT_COLOR: WHITE,
            OmniSurfaceInput.COAT_INDEX_OF_REFRACTION: DEFAULT_INDEX_OF_REFRACTION,
            OmniSurfaceInput.THIN_WALLED: False,
        }
    )
    """
    Inputs the glTF model cannot express but that are harmless at these values.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        input_name = OmniSurfaceInput
        transmission = (
            inputs.number(input_name.TRANSMISSION_WEIGHT, 0.0)
            if inputs.flag(input_name.ENABLE_TRANSMISSION, False)
            else 0.0
        )
        color = self.base_color(inputs, transmission)
        opacity = (
            inputs.number(input_name.OPACITY, 1.0)
            if inputs.flag(input_name.ENABLE_OPACITY, False)
            else 1.0
        )
        material = PhysicallyBasedMaterial(
            name="",
            base_color_factor=(*color.factor, opacity),
            base_color_texture=color.texture,
            normal_texture=inputs.texture(input_name.NORMAL_IMAGE),
            index_of_refraction=inputs.number(
                input_name.INDEX_OF_REFRACTION, DEFAULT_INDEX_OF_REFRACTION
            ),
            clearcoat=inputs.number(input_name.COAT_WEIGHT, 0.0),
            clearcoat_roughness=inputs.number(
                input_name.COAT_ROUGHNESS, self.coat_roughness
            ),
            anisotropy=inputs.number(input_name.ANISOTROPY, 0.0),
            transmission=transmission,
            alpha_mode=(
                AlphaMode.BLEND
                if transmission > 0.0 or opacity < 1.0
                else AlphaMode.OPAQUE
            ),
        )
        material = RoughnessMetallicPacking(
            ScalarChannel(
                inputs.number(input_name.ROUGHNESS, self.roughness),
                inputs.texture(input_name.ROUGHNESS_IMAGE),
            ),
            ScalarChannel(
                inputs.number(input_name.METALNESS, 0.0),
                inputs.texture(input_name.METALNESS_IMAGE),
            ),
        ).apply(material)
        return self.with_emission(material, inputs)

    def base_color(self, inputs: ShaderInputs, transmission: float) -> TexturedColor:
        """
        :param inputs: The authored inputs.
        :param transmission: The share of light passing through.
        :return: The weighted diffuse colour, mixed with the transmission colour by
            the transmitted share.
        """
        input_name = OmniSurfaceInput
        diffuse = inputs.textured_color(
            input_name.DIFFUSE_COLOR, input_name.DIFFUSE_IMAGE, self.diffuse_color
        ).scaled(inputs.number(input_name.DIFFUSE_WEIGHT, self.diffuse_weight))
        if transmission <= 0.0:
            return diffuse
        return diffuse.mixed_with(
            inputs.textured_color(
                input_name.TRANSMISSION_COLOR,
                input_name.TRANSMISSION_COLOR_IMAGE,
                self.transmission_color,
            ),
            transmission,
        )

    def with_emission(
        self, material: PhysicallyBasedMaterial, inputs: ShaderInputs
    ) -> PhysicallyBasedMaterial:
        """
        :param material: The material without emission.
        :param inputs: The authored inputs.
        :return: The material with OmniSurface's emission.
        """
        input_name = OmniSurfaceInput
        weight = inputs.number(input_name.EMISSION_WEIGHT, 0.0)
        if weight <= 0.0:
            return material
        color = inputs.color(input_name.EMISSION_COLOR, WHITE)
        emitted = self.emission.emission(
            tuple(component * weight for component in color),
            inputs.number(input_name.EMISSION_INTENSITY, 1.0),
        )
        return replace(
            material,
            emissive_factor=emitted.factor,
            emissive_strength=emitted.strength,
        )
