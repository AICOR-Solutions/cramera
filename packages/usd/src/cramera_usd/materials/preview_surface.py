"""
The UsdPreviewSurface shader mapped onto glTF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Dict

from cramera_usd.materials.channels import ScalarChannel
from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.mapping import RoughnessMetallicPacking, ShaderMapping
from cramera_usd.materials.physically_based import (
    BLACK,
    DEFAULT_ALPHA_CUTOFF,
    DEFAULT_INDEX_OF_REFRACTION,
    DEFAULT_ROUGHNESS,
    WHITE,
    AlphaMode,
    LinearColor,
    PhysicallyBasedMaterial,
)
from cramera_usd.materials.transmission import NORMAL_INCIDENCE, TransmissionBlending
from cramera_usd.scene.materials import ShaderInputValue

# %% inputs


class PreviewSurfaceInput(StrEnum):
    """
    The UsdPreviewSurface inputs the mapping knows: those it reads, and those glTF
    cannot express that it may leave out at a neutral value.
    """

    DIFFUSE_COLOR = "diffuseColor"
    """
    The base colour, or a texture.
    """

    EMISSIVE_COLOR = "emissiveColor"
    """
    The emitted colour, or a texture.
    """

    METALLIC = "metallic"
    """
    The metalness, or a texture.
    """

    ROUGHNESS = "roughness"
    """
    The roughness, or a texture.
    """

    OPACITY = "opacity"
    """
    The opacity.
    """

    OPACITY_THRESHOLD = "opacityThreshold"
    """
    The opacity below which the surface is cut out.
    """

    INDEX_OF_REFRACTION = "ior"
    """
    The index of refraction.
    """

    NORMAL = "normal"
    """
    The normal map.
    """

    CLEARCOAT = "clearcoat"
    """
    The strength of the clear coat.
    """

    CLEARCOAT_ROUGHNESS = "clearcoatRoughness"
    """
    The roughness of the clear coat.
    """

    USE_SPECULAR_WORKFLOW = "useSpecularWorkflow"
    """
    Whether the specular colour replaces the metalness.
    """

    SPECULAR_COLOR = "specularColor"
    """
    The specular colour of the specular workflow.
    """

    DISPLACEMENT = "displacement"
    """
    The displacement of the surface.
    """

    OCCLUSION = "occlusion"
    """
    The ambient occlusion.
    """


# %% mapping


@dataclass
class PreviewSurfaceMapping(ShaderMapping):
    """
    UsdPreviewSurface, whose metallic workflow is glTF's model and whose specular
    workflow becomes glTF's specular colour; a connected texture replaces the constant
    of its input.
    """

    diffuse_color: LinearColor = (0.18, 0.18, 0.18)
    """
    UsdPreviewSurface's default ``diffuseColor``.
    """

    clearcoat_roughness: float = 0.01
    """
    UsdPreviewSurface's default ``clearcoatRoughness``.
    """

    neutral_inputs: Dict[str, ShaderInputValue] = field(
        default_factory=lambda: {
            PreviewSurfaceInput.SPECULAR_COLOR: BLACK,
            PreviewSurfaceInput.DISPLACEMENT: 0.0,
            PreviewSurfaceInput.OCCLUSION: 1.0,
        }
    )
    """
    Inputs the glTF model cannot express but that are harmless at these values.
    """

    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        input_name = PreviewSurfaceInput
        diffuse_texture = inputs.texture(input_name.DIFFUSE_COLOR)
        emissive_texture = inputs.texture(input_name.EMISSIVE_COLOR)
        opacity = inputs.number(input_name.OPACITY, 1.0)
        threshold = inputs.number(input_name.OPACITY_THRESHOLD, 0.0)
        index_of_refraction = inputs.number(
            input_name.INDEX_OF_REFRACTION, DEFAULT_INDEX_OF_REFRACTION
        )
        specular_workflow = inputs.flag(input_name.USE_SPECULAR_WORKFLOW, False)
        metallic = ScalarChannel(
            inputs.number(input_name.METALLIC, 0.0),
            inputs.texture(input_name.METALLIC),
        )
        return RoughnessMetallicPacking(
            ScalarChannel(
                inputs.number(input_name.ROUGHNESS, DEFAULT_ROUGHNESS),
                inputs.texture(input_name.ROUGHNESS),
            ),
            ScalarChannel(0.0) if specular_workflow else metallic,
        ).apply(
            PhysicallyBasedMaterial(
                name="",
                base_color_factor=(
                    *(
                        WHITE
                        if diffuse_texture is not None
                        else inputs.color(input_name.DIFFUSE_COLOR, self.diffuse_color)
                    ),
                    opacity,
                ),
                base_color_texture=diffuse_texture,
                emissive_factor=(
                    WHITE
                    if emissive_texture is not None
                    else inputs.color(input_name.EMISSIVE_COLOR, BLACK)
                ),
                emissive_texture=emissive_texture,
                normal_texture=inputs.texture(input_name.NORMAL),
                index_of_refraction=index_of_refraction,
                specular_color_factor=(
                    self.specular_color_factor(inputs, index_of_refraction)
                    if specular_workflow
                    else WHITE
                ),
                clearcoat=inputs.number(input_name.CLEARCOAT, 0.0),
                clearcoat_roughness=inputs.number(
                    input_name.CLEARCOAT_ROUGHNESS, self.clearcoat_roughness
                ),
                alpha_mode=self.alpha_mode(opacity, threshold),
                alpha_cutoff=threshold if threshold > 0.0 else DEFAULT_ALPHA_CUTOFF,
            )
        )

    @staticmethod
    def specular_color_factor(
        inputs: ShaderInputs, index_of_refraction: float
    ) -> LinearColor:
        """
        :param inputs: The authored inputs of a material in the specular workflow.
        :param index_of_refraction: The material's index of refraction.
        :return: The specular colour, the reflectance at normal incidence, relative to
            the reflectance the index of refraction gives.
        """
        reflectance = TransmissionBlending.fresnel_reflectance(
            NORMAL_INCIDENCE, index_of_refraction
        )
        specular = inputs.color(PreviewSurfaceInput.SPECULAR_COLOR, BLACK)
        return (
            specular[0] / reflectance,
            specular[1] / reflectance,
            specular[2] / reflectance,
        )

    @staticmethod
    def alpha_mode(opacity: float, threshold: float) -> AlphaMode:
        """
        :param opacity: The authored opacity.
        :param threshold: The opacity below which the surface is cut out.
        :return: Cut out with a threshold, else blended when partly transparent, else
            opaque.
        """
        if threshold > 0.0:
            return AlphaMode.MASK
        if opacity < 1.0:
            return AlphaMode.BLEND
        return AlphaMode.OPAQUE
