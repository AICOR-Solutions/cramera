"""
The contract of a shader mapping, and the packing of roughness and metalness and the
orientation of normal maps the mappings share.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import StrEnum

from typing_extensions import Dict, Optional

from cramera_usd.materials.channels import (
    FlippedNormalTexture,
    RoughnessMetallicTexture,
    ScalarChannel,
)
from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.scene.materials import AuthoredMaterial, ShaderInputValue, TextureFile

# %% mapping


@dataclass
class ShaderMapping(ABC):
    """
    Maps the inputs of one shading model onto a glTF material.
    """

    neutral_inputs: Dict[str, ShaderInputValue] = field(default_factory=dict)
    """
    Inputs the glTF model cannot express but that are harmless at these values.
    """

    def map(self, material: AuthoredMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: An authored material.
        :return: Its glTF material, listing the inputs left out.
        """
        inputs = ShaderInputs(material)
        mapped = self.map_inputs(inputs)
        return replace(
            mapped,
            name=material.name,
            unmapped_inputs=inputs.unmapped(self.neutral_inputs),
        )

    @abstractmethod
    def map_inputs(self, inputs: ShaderInputs) -> PhysicallyBasedMaterial:
        """
        :param inputs: The authored inputs.
        :return: The glTF material for the inputs; :meth:`map` fills in the name.
        """


# %% roughness and metalness


@dataclass
class RoughnessMetallicPacking:
    """
    Puts roughness and metalness into a glTF material: as factors while both are
    constant, else as one packed texture with the blend baked in.
    """

    roughness: ScalarChannel
    """
    The roughness source.
    """

    metallic: ScalarChannel
    """
    The metalness source.
    """

    def apply(self, material: PhysicallyBasedMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: A material to complete.
        :return: The material with roughness and metalness set.
        """
        if not self.roughness.textured and not self.metallic.textured:
            return replace(
                material,
                roughness_factor=self.roughness.constant,
                metallic_factor=self.metallic.constant,
            )
        return replace(
            material,
            roughness_factor=1.0,
            metallic_factor=1.0,
            metallic_roughness_texture=RoughnessMetallicTexture(
                self.roughness, self.metallic
            ),
        )


# %% normal maps


@dataclass(frozen=True)
class NormalMap:
    """
    Puts a tangent-space normal map into a glTF material when the shader's tangent along
    U or along V may point the other way than glTF's: both flipped negate the strength,
    which flips both components; one flipped inverts its component in the image, which
    glTF has no parameter for.
    """

    texture: Optional[TextureFile]
    """
    The normal map, or None for a surface without one, whose tangents have no effect.
    """

    strength: float = 1.0
    """
    The strength of the normal map.
    """

    flip_x: bool = False
    """
    Whether the shader's tangent along U points the other way than glTF's.
    """

    flip_y: bool = False
    """
    Whether the shader's tangent along V points the other way than glTF's.
    """

    def apply(self, material: PhysicallyBasedMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: A material to complete.
        :return: The material with the normal map oriented as glTF reads it.
        """
        if self.texture is None:
            return material
        if self.flip_x and self.flip_y:
            return replace(
                material, normal_texture=self.texture, normal_scale=-self.strength
            )
        if self.flip_x or self.flip_y:
            return replace(
                material,
                normal_texture=FlippedNormalTexture(
                    self.texture, self.flip_x, self.flip_y
                ),
                normal_scale=self.strength,
            )
        return replace(
            material, normal_texture=self.texture, normal_scale=self.strength
        )


class TangentFlipInput(StrEnum):
    """
    The inputs of NVIDIA's MDL materials (OmniPBR, OmniGlass) that flip the tangents
    their normal map is read along.
    """

    FLIP_U = "flip_tangent_u"
    """
    Whether the tangent along U is flipped.
    """

    FLIP_V = "flip_tangent_v"
    """
    Whether the tangent along V is flipped.
    """


@dataclass(frozen=True)
class TangentFlips:
    """
    Reads the tangent flips of an MDL material against its defaults, under which it
    reads a normal map as glTF does (green pointing up the image): SimReady packages
    feed one normal map to OmniPBR at these defaults and to UsdPreviewSurface, whose
    tangents are glTF's.
    """

    flip_u: bool = False
    """
    The material's default ``flip_tangent_u``.
    """

    flip_v: bool = True
    """
    The material's default ``flip_tangent_v``.
    """

    def normal_map(
        self, inputs: ShaderInputs, texture: Optional[TextureFile], strength: float
    ) -> NormalMap:
        """
        :param inputs: The authored inputs.
        :param texture: The material's normal map, or None.
        :param strength: The strength of the normal map.
        :return: The normal map, its tangents flipped where they differ from the
            defaults; read even without a normal map, where they have no effect.
        """
        return NormalMap(
            texture,
            strength,
            inputs.flag(TangentFlipInput.FLIP_U, self.flip_u) != self.flip_u,
            inputs.flag(TangentFlipInput.FLIP_V, self.flip_v) != self.flip_v,
        )
