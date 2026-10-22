"""
The glTF JSON of one material.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import TYPE_CHECKING, Any, Dict, List, Union

from cramera_usd.gltf.format import GltfExtension, GltfKey, MaterialKey
from cramera_usd.materials.physically_based import (
    DEFAULT_INDEX_OF_REFRACTION,
    AlphaMode,
    PhysicallyBasedMaterial,
)

if TYPE_CHECKING:
    from cramera_usd.gltf.document import GltfDocument

# %% material


@dataclass
class GltfMaterial:
    """
    The glTF JSON of one material.
    """

    material: PhysicallyBasedMaterial
    """
    The material to write, as authored.
    """

    document: GltfDocument
    """
    The document receiving its textures and extensions.
    """

    def to_json(self) -> Dict[str, Any]:
        """
        :return: The material as glTF JSON; a transmissive surface is written as its
            blended approximation, with its :meth:`physical_properties` in the
            ``extras``.
        """
        material = self.document.blending.approximate(self.material)
        result: Dict[str, Any] = {
            GltfKey.NAME: material.name,
            MaterialKey.METALLIC_ROUGHNESS: self.metallic_roughness(material),
            MaterialKey.DOUBLE_SIDED: material.double_sided,
        }
        transform = material.texture_transform
        if material.normal_texture is not None:
            result[MaterialKey.NORMAL_TEXTURE] = self.document.texture_reference(
                material.normal_texture, transform
            ) | {GltfKey.SCALE: float(material.normal_scale)}
        if any(material.emissive_factor):
            result[MaterialKey.EMISSIVE_FACTOR] = [
                float(value) for value in material.emissive_factor
            ]
        if material.emissive_texture is not None:
            result[MaterialKey.EMISSIVE_TEXTURE] = self.document.texture_reference(
                material.emissive_texture, transform
            )
        if material.alpha_mode is not AlphaMode.OPAQUE:
            result[MaterialKey.ALPHA_MODE] = material.alpha_mode.value
        if material.alpha_mode is AlphaMode.MASK:
            result[MaterialKey.ALPHA_CUTOFF] = float(material.alpha_cutoff)
        if material.transmissive:
            result[GltfKey.EXTRAS] = self.physical_properties()
        extensions = self.extensions()
        if extensions:
            result[GltfKey.EXTENSIONS] = extensions
            self.document.extensions.update(extensions)
        return result

    def metallic_roughness(self, material: PhysicallyBasedMaterial) -> Dict[str, Any]:
        """
        :param material: The material as drawn.
        :return: Its ``pbrMetallicRoughness`` property, embedding its textures.
        """
        transform = material.texture_transform
        metallic_roughness: Dict[str, Any] = {
            MaterialKey.BASE_COLOR_FACTOR: [
                float(value) for value in material.base_color_factor
            ],
            MaterialKey.METALLIC_FACTOR: float(material.metallic_factor),
            MaterialKey.ROUGHNESS_FACTOR: float(material.roughness_factor),
        }
        if material.base_color_texture is not None:
            metallic_roughness[MaterialKey.BASE_COLOR_TEXTURE] = (
                self.document.texture_reference(material.base_color_texture, transform)
            )
        if material.metallic_roughness_texture is not None:
            metallic_roughness[MaterialKey.METALLIC_ROUGHNESS_TEXTURE] = (
                self.document.texture_reference(
                    material.metallic_roughness_texture, transform
                )
            )
        return metallic_roughness

    def physical_properties(self) -> Dict[MaterialKey, Union[float, List[float]]]:
        """
        :return: The authored values of a transmissive surface that a renderer which
            refracts needs and the blended approximation replaces: transmission, index
            of refraction, base colour and metalness, named as glTF and its
            ``KHR_materials_transmission`` and ``KHR_materials_ior`` extensions name
            them.
        """
        material = self.material
        return {
            MaterialKey.TRANSMISSION_FACTOR: float(material.transmission),
            MaterialKey.INDEX_OF_REFRACTION: float(material.index_of_refraction),
            MaterialKey.BASE_COLOR_FACTOR: [
                float(value) for value in material.base_color_factor
            ],
            MaterialKey.METALLIC_FACTOR: float(material.metallic_factor),
        }

    def extensions(self) -> Dict[GltfExtension, Dict[str, float]]:
        """
        :return: The material extensions whose values differ from glTF's defaults; the
            index of refraction of a transmissive surface is kept with its
            :meth:`physical_properties`.
        """
        material = self.material
        extensions: Dict[GltfExtension, Dict[str, float]] = {}
        if (
            not material.transmissive
            and material.index_of_refraction != DEFAULT_INDEX_OF_REFRACTION
        ):
            extensions[GltfExtension.INDEX_OF_REFRACTION] = {
                MaterialKey.INDEX_OF_REFRACTION: float(material.index_of_refraction)
            }
        if material.clearcoat > 0.0:
            extensions[GltfExtension.CLEARCOAT] = {
                MaterialKey.CLEARCOAT_FACTOR: float(material.clearcoat),
                MaterialKey.CLEARCOAT_ROUGHNESS_FACTOR: float(
                    material.clearcoat_roughness
                ),
            }
        if material.emissive_strength != 1.0:
            extensions[GltfExtension.EMISSIVE_STRENGTH] = {
                MaterialKey.EMISSIVE_STRENGTH: float(material.emissive_strength)
            }
        if material.anisotropy > 0.0:
            extensions[GltfExtension.ANISOTROPY] = {
                MaterialKey.ANISOTROPY_STRENGTH: float(material.anisotropy)
            }
        return extensions
