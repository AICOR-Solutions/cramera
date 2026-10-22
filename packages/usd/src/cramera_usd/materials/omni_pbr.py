"""
NVIDIA's OmniPBR material mapped onto glTF.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from typing_extensions import Dict, Optional

from cramera_usd.materials.channels import ScalarChannel
from cramera_usd.materials.emission import EmissionScale
from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.mapping import RoughnessMetallicPacking, ShaderMapping
from cramera_usd.materials.physically_based import (
    DEFAULT_ALPHA_CUTOFF,
    WHITE,
    AlphaMode,
    LinearColor,
    PhysicallyBasedMaterial,
    TextureTransform,
)
from cramera_usd.scene.materials import ShaderInputValue, TextureChannel

# %% inputs


class OmniPhysicallyBasedInput(StrEnum):
    """
    The OmniPBR inputs the mapping knows: those it reads, and those glTF cannot express
    that it may leave out at a neutral value.
    """

    DIFFUSE_COLOR = "diffuse_color_constant"
    """
    The albedo without a texture.
    """

    DIFFUSE_TEXTURE = "diffuse_texture"
    """
    The albedo texture.
    """

    DIFFUSE_TINT = "diffuse_tint"
    """
    Multiplies the albedo.
    """

    ROUGHNESS = "reflection_roughness_constant"
    """
    The roughness without a texture.
    """

    ROUGHNESS_TEXTURE = "reflectionroughness_texture"
    """
    The roughness texture.
    """

    ROUGHNESS_INFLUENCE = "reflection_roughness_texture_influence"
    """
    How much the roughness texture replaces the constant.
    """

    METALLIC = "metallic_constant"
    """
    The metalness without a texture.
    """

    METALLIC_TEXTURE = "metallic_texture"
    """
    The metalness texture.
    """

    METALLIC_INFLUENCE = "metallic_texture_influence"
    """
    How much the metalness texture replaces the constant.
    """

    ENABLE_PACKED_TEXTURE = "enable_ORM_texture"
    """
    Whether occlusion, roughness and metalness come from one packed texture.
    """

    PACKED_TEXTURE = "ORM_texture"
    """
    The packed occlusion, roughness and metalness texture.
    """

    NORMAL_TEXTURE = "normalmap_texture"
    """
    The normal map.
    """

    BUMP_FACTOR = "bump_factor"
    """
    The strength of the normal map.
    """

    ENABLE_EMISSION = "enable_emission"
    """
    Whether the surface emits light.
    """

    EMISSIVE_COLOR = "emissive_color"
    """
    The emitted colour without a texture.
    """

    EMISSIVE_TEXTURE = "emissive_color_texture"
    """
    The emitted colour texture.
    """

    EMISSIVE_INTENSITY = "emissive_intensity"
    """
    The emitted luminance in nits.
    """

    ENABLE_OPACITY = "enable_opacity"
    """
    Whether the surface is partly transparent.
    """

    OPACITY = "opacity_constant"
    """
    The opacity without a texture.
    """

    OPACITY_THRESHOLD = "opacity_threshold"
    """
    The opacity below which the surface is cut out.
    """

    TEXTURE_TRANSLATE = "texture_translate"
    """
    Shifts the texture coordinates.
    """

    TEXTURE_SCALE = "texture_scale"
    """
    Repeats the texture.
    """

    SPECULAR_LEVEL = "specular_level"
    """
    The strength of the specular reflection.
    """

    PROJECT_COORDINATES = "project_uvw"
    """
    Whether texture coordinates are projected instead of read from the mesh.
    """

    WORLD_OR_OBJECT = "world_or_object"
    """
    Whether projected coordinates are in world rather than object space.
    """

    ALBEDO_DESATURATION = "albedo_desaturation"
    """
    How much the albedo is desaturated.
    """

    ALBEDO_ADD = "albedo_add"
    """
    A value added to the albedo.
    """

    ALBEDO_BRIGHTNESS = "albedo_brightness"
    """
    Scales the albedo.
    """

    TEXTURE_ROTATE = "texture_rotate"
    """
    Turns the texture coordinates.
    """

    EXCLUDE_FROM_WHITE_MODE = "excludeFromWhiteMode"
    """
    Whether the material keeps its look in the renderer's white mode.
    """


NO_TRANSLATION = (0.0, 0.0)
"""
Texture coordinates left in place.
"""

NO_SCALING = (1.0, 1.0)
"""
Texture coordinates left at their size.
"""

# %% mapping


@dataclass
class OmniPhysicallyBasedMapping(ShaderMapping):
    """
    OmniPBR: the base colour is the diffuse texture (or constant) times the tint;
    roughness and metalness blend constant and texture by their influence.
    """

    diffuse_color: LinearColor = (0.2, 0.2, 0.2)
    """
    OmniPBR's default ``diffuse_color_constant``.
    """

    roughness: float = 0.5
    """
    OmniPBR's default ``reflection_roughness_constant``.
    """

    emissive_color: LinearColor = (1.0, 0.1, 0.1)
    """
    OmniPBR's default ``emissive_color``.
    """

    emissive_intensity: float = 40.0
    """
    OmniPBR's default ``emissive_intensity``.
    """

    emission: EmissionScale = field(default_factory=EmissionScale)
    """
    The conversion of emission intensities.
    """

    neutral_inputs: Dict[str, ShaderInputValue] = field(
        default_factory=lambda: {
            OmniPhysicallyBasedInput.SPECULAR_LEVEL: 0.5,
            OmniPhysicallyBasedInput.PROJECT_COORDINATES: False,
            OmniPhysicallyBasedInput.WORLD_OR_OBJECT: False,
            OmniPhysicallyBasedInput.ALBEDO_DESATURATION: 0.0,
            OmniPhysicallyBasedInput.ALBEDO_ADD: 0.0,
            OmniPhysicallyBasedInput.ALBEDO_BRIGHTNESS: 1.0,
            OmniPhysicallyBasedInput.TEXTURE_ROTATE: 0.0,
            OmniPhysicallyBasedInput.EXCLUDE_FROM_WHITE_MODE: False,
        }
    )
    """
    Inputs the glTF model cannot express but that are harmless at these values.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        input_name = OmniPhysicallyBasedInput
        tint = inputs.color(input_name.DIFFUSE_TINT, WHITE)
        diffuse_texture = inputs.texture(input_name.DIFFUSE_TEXTURE)
        diffuse = (
            WHITE
            if diffuse_texture is not None
            else inputs.color(input_name.DIFFUSE_COLOR, self.diffuse_color)
        )
        enable_opacity = inputs.flag(input_name.ENABLE_OPACITY, False)
        opacity = inputs.number(input_name.OPACITY, 1.0) if enable_opacity else 1.0
        threshold = inputs.number(input_name.OPACITY_THRESHOLD, 0.0)
        material = PhysicallyBasedMaterial(
            name="",
            base_color_factor=(
                *(
                    diffuse_channel * tint_channel
                    for diffuse_channel, tint_channel in zip(diffuse, tint)
                ),
                opacity,
            ),
            base_color_texture=diffuse_texture,
            normal_texture=inputs.texture(input_name.NORMAL_TEXTURE),
            normal_scale=inputs.number(input_name.BUMP_FACTOR, 1.0),
            alpha_mode=self.alpha_mode(enable_opacity, threshold),
            alpha_cutoff=threshold if threshold > 0.0 else DEFAULT_ALPHA_CUTOFF,
            texture_transform=self.texture_transform(inputs),
        )
        material = self.roughness_metallic(inputs).apply(material)
        return self.with_emission(material, inputs)

    @staticmethod
    def alpha_mode(enable_opacity: bool, threshold: float) -> AlphaMode:
        """
        :param enable_opacity: Whether the material enables its opacity.
        :param threshold: The opacity below which the surface is cut out.
        :return: Opaque without opacity, else cut out with a threshold, else blended.
        """
        if not enable_opacity:
            return AlphaMode.OPAQUE
        return AlphaMode.MASK if threshold > 0.0 else AlphaMode.BLEND

    def roughness_metallic(self, inputs: ShaderInputs) -> RoughnessMetallicPacking:
        """
        :param inputs: The authored inputs.
        :return: Roughness and metalness, each from its own texture or from the packed
            occlusion, roughness and metalness texture when that is enabled.
        """
        input_name = OmniPhysicallyBasedInput
        packed = (
            inputs.texture(input_name.PACKED_TEXTURE)
            if inputs.flag(input_name.ENABLE_PACKED_TEXTURE, False)
            else None
        )
        return RoughnessMetallicPacking(
            ScalarChannel(
                constant=inputs.number(input_name.ROUGHNESS, self.roughness),
                texture=(
                    replace(packed, channel=TextureChannel.GREEN)
                    if packed is not None
                    else inputs.texture(input_name.ROUGHNESS_TEXTURE)
                ),
                influence=inputs.number(input_name.ROUGHNESS_INFLUENCE, 0.0),
            ),
            ScalarChannel(
                constant=inputs.number(input_name.METALLIC, 0.0),
                texture=(
                    replace(packed, channel=TextureChannel.BLUE)
                    if packed is not None
                    else inputs.texture(input_name.METALLIC_TEXTURE)
                ),
                influence=inputs.number(input_name.METALLIC_INFLUENCE, 0.0),
            ),
        )

    def with_emission(
        self, material: PhysicallyBasedMaterial, inputs: ShaderInputs
    ) -> PhysicallyBasedMaterial:
        """
        :param material: The material without emission.
        :param inputs: The authored inputs.
        :return: The material with OmniPBR's emission.
        """
        input_name = OmniPhysicallyBasedInput
        enabled = inputs.flag(input_name.ENABLE_EMISSION, False)
        texture = inputs.texture(input_name.EMISSIVE_TEXTURE)
        color = inputs.color(input_name.EMISSIVE_COLOR, self.emissive_color)
        intensity = inputs.number(
            input_name.EMISSIVE_INTENSITY, self.emissive_intensity
        )
        if not enabled or intensity <= 0.0:
            return material
        emission = self.emission.emission(
            WHITE if texture is not None else color, intensity
        )
        return replace(
            material,
            emissive_factor=emission.factor,
            emissive_texture=texture,
            emissive_strength=emission.strength,
        )

    @staticmethod
    def texture_transform(inputs: ShaderInputs) -> Optional[TextureTransform]:
        """
        :param inputs: The authored inputs.
        :return: OmniPBR's tiling, ``uv * scale + translate``, rewritten for glTF's
            texture coordinates whose V axis is flipped (``v' = 1 - v``), or None
            without tiling.
        """
        scale = inputs.vector(OmniPhysicallyBasedInput.TEXTURE_SCALE, NO_SCALING)
        translate = inputs.vector(
            OmniPhysicallyBasedInput.TEXTURE_TRANSLATE, NO_TRANSLATION
        )
        if scale == NO_SCALING and translate == NO_TRANSLATION:
            return None
        return TextureTransform(
            offset=(translate[0], 1.0 - scale[1] - translate[1]), scale=scale
        )
