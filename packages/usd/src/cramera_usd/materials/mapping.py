"""
The contract of a shader mapping, and the packing of roughness and metalness every
mapping shares.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace

from typing_extensions import Dict

from cramera_usd.materials.channels import RoughnessMetallicTexture, ScalarChannel
from cramera_usd.materials.inputs import ShaderInputs
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.scene.materials import AuthoredMaterial, ShaderInputValue

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
