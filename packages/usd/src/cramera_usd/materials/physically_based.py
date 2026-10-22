"""
The glTF 2.0 metallic-roughness material model with the extensions the converter writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from typing_extensions import Optional, Self, Tuple

from cramera_usd.materials.channels import RoughnessMetallicTexture
from cramera_usd.scene.materials import TextureFile

# %% vocabulary


class AlphaMode(StrEnum):
    """
    How the alpha of the base colour is used, named as glTF names its alpha modes.
    """

    OPAQUE = "OPAQUE"
    """
    Alpha is ignored.
    """

    MASK = "MASK"
    """
    Fragments below the alpha cutoff are discarded.
    """

    BLEND = "BLEND"
    """
    The surface is blended over what lies behind it.
    """


LinearColor = Tuple[float, float, float]
"""
A linear red, green and blue.
"""

LinearColorWithAlpha = Tuple[float, float, float, float]
"""
A linear red, green and blue, and an opacity.
"""

WHITE: LinearColor = (1.0, 1.0, 1.0)
"""
Linear white.
"""

BLACK: LinearColor = (0.0, 0.0, 0.0)
"""
Linear black.
"""

DEFAULT_ALPHA_CUTOFF = 0.5
"""
GlTF's default alpha threshold of :attr:`AlphaMode.MASK`.
"""

DEFAULT_INDEX_OF_REFRACTION = 1.5
"""
GlTF's default index of refraction.
"""

DEFAULT_ROUGHNESS = 0.5
"""
The roughness of a material that authors none.
"""


@dataclass(frozen=True)
class TextureTransform:
    """
    An affine change of texture coordinates in glTF's convention (origin top left),
    written as ``KHR_texture_transform``.
    """

    offset: Tuple[float, float] = (0.0, 0.0)
    """
    Added to the scaled coordinates.
    """

    scale: Tuple[float, float] = (1.0, 1.0)
    """
    Multiplies the coordinates; values above one repeat the texture.
    """


# %% material


@dataclass(frozen=True)
class PhysicallyBasedMaterial:
    """
    A glTF 2.0 metallic-roughness material with the extensions the converter writes.

    Equal materials share one glTF material and one draw call.
    """

    name: str = field(compare=False)
    """
    The name of the material on the stage.
    """

    base_color_factor: LinearColorWithAlpha = (*WHITE, 1.0)
    """
    Linear base colour and alpha, multiplied with the base colour texture.
    """

    base_color_texture: Optional[TextureFile] = None
    """
    The sRGB base colour texture.
    """

    metallic_factor: float = 0.0
    """
    Metalness, multiplied with the blue channel of the metallic-roughness texture.
    """

    roughness_factor: float = DEFAULT_ROUGHNESS
    """
    Perceptual roughness, multiplied with the green channel of the metallic-roughness
    texture.
    """

    metallic_roughness_texture: Optional[RoughnessMetallicTexture] = None
    """
    The packed roughness and metalness texture.
    """

    normal_texture: Optional[TextureFile] = None
    """
    The tangent-space normal map.
    """

    normal_scale: float = 1.0
    """
    The strength of the normal map.
    """

    emissive_factor: LinearColor = BLACK
    """
    Linear emitted colour, each component at most one.
    """

    emissive_texture: Optional[TextureFile] = None
    """
    The sRGB emission texture.
    """

    emissive_strength: float = 1.0
    """
    Multiplies the emission beyond the unit range (``KHR_materials_emissive_strength``).
    """

    alpha_mode: AlphaMode = AlphaMode.OPAQUE
    """
    How alpha is used.
    """

    alpha_cutoff: float = DEFAULT_ALPHA_CUTOFF
    """
    The alpha threshold in :attr:`AlphaMode.MASK`.
    """

    double_sided: bool = False
    """
    Whether back faces are drawn.
    """

    transmission: float = 0.0
    """
    The share of light passing through the surface, tinted by the base colour.
    """

    index_of_refraction: float = DEFAULT_INDEX_OF_REFRACTION
    """
    The index of refraction (``KHR_materials_ior``).
    """

    clearcoat: float = 0.0
    """
    The strength of a clear coat layer (``KHR_materials_clearcoat``).
    """

    clearcoat_roughness: float = 0.0
    """
    The roughness of the clear coat layer.
    """

    anisotropy: float = 0.0
    """
    The strength of anisotropic reflection (``KHR_materials_anisotropy``).
    """

    texture_transform: Optional[TextureTransform] = None
    """
    A change of texture coordinates shared by every texture of the material.
    """

    unmapped_inputs: Tuple[str, ...] = field(default=(), compare=False)
    """
    The authored shader inputs the mapping did not carry over.
    """

    @property
    def transmissive(self) -> bool:
        """
        Whether light passes through the surface.
        """
        return self.transmission > 0.0

    @property
    def textured(self) -> bool:
        """
        Whether any texture of the material reads texture coordinates.
        """
        return any(
            texture is not None
            for texture in (
                self.base_color_texture,
                self.metallic_roughness_texture,
                self.normal_texture,
                self.emissive_texture,
            )
        )

    def with_double_sides(self) -> Self:
        """
        :return: The same material drawn from both sides.
        """
        return replace(self, double_sided=True)
