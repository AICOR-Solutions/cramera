"""
The choice of a shader mapping by shading model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import Dict

from cramera_usd.materials.fallbacks import DisplayColorMapping, UnknownShaderMapping
from cramera_usd.materials.mapping import ShaderMapping
from cramera_usd.materials.omni_glass import OmniGlassMapping
from cramera_usd.materials.omni_pbr import OmniPhysicallyBasedMapping
from cramera_usd.materials.omni_surface import OmniSurfaceMapping
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.materials.preview_surface import PreviewSurfaceMapping
from cramera_usd.scene.materials import AuthoredMaterial, MaterialSource

# %% mapper


@dataclass
class MaterialMapper:
    """
    Picks the mapping for each authored material's shading model.
    """

    mappings: Dict[MaterialSource, ShaderMapping] = field(
        default_factory=lambda: {
            MaterialSource.OMNI_PBR: OmniPhysicallyBasedMapping(),
            MaterialSource.OMNI_SURFACE: OmniSurfaceMapping(),
            MaterialSource.OMNI_GLASS: OmniGlassMapping(),
            MaterialSource.PREVIEW_SURFACE: PreviewSurfaceMapping(),
            MaterialSource.DISPLAY_COLOR: DisplayColorMapping(),
            MaterialSource.UNKNOWN: UnknownShaderMapping(),
        }
    )
    """
    The mapping per shading model.
    """

    def map(self, material: AuthoredMaterial) -> PhysicallyBasedMaterial:
        """
        :param material: An authored material.
        :return: Its glTF material.
        """
        return self.mappings[material.source].map(material)
