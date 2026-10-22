"""
Materials as the stage authors them: the shading model and the inputs of the surface
shader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Tuple, Union

# %% vocabularies


class MaterialSource(StrEnum):
    """
    The shading model a bound material was authored with.
    """

    OMNI_PBR = "OmniPBR"
    """
    NVIDIA's OmniPBR MDL material.
    """

    OMNI_SURFACE = "OmniSurface"
    """
    NVIDIA's OmniSurface MDL material, a variant of Autodesk Standard Surface.
    """

    OMNI_GLASS = "OmniGlass"
    """
    NVIDIA's OmniGlass MDL material.
    """

    PREVIEW_SURFACE = "UsdPreviewSurface"
    """
    The USD preview surface shader.
    """

    DISPLAY_COLOR = "displayColor"
    """
    No material is bound; the geometry's display colour primvar (or the USD fallback
    grey) shades it.
    """

    UNKNOWN = "unknown"
    """
    A shader none of the mappings understands.
    """

    @classmethod
    def of_identifier(cls, identifier: str) -> MaterialSource:
        """
        :param identifier: A shader's identifier on the stage.
        :return: The shading model of that identifier, or :attr:`UNKNOWN`.
        """
        known = {member.value: member for member in cls}
        return known.get(identifier, cls.UNKNOWN)


class TextureChannel(StrEnum):
    """
    Which channels of a texture file a shader input reads, named as UsdUVTexture names
    its outputs.
    """

    RGB = "rgb"
    """
    The three colour channels.
    """

    RED = "r"
    """
    The red channel only.
    """

    GREEN = "g"
    """
    The green channel only.
    """

    BLUE = "b"
    """
    The blue channel only.
    """

    ALPHA = "a"
    """
    The alpha channel only.
    """

    @classmethod
    def of_output(cls, output_name: str) -> TextureChannel:
        """
        :param output_name: The name of a UsdUVTexture output.
        :return: The channels the output provides; an output of another name provides
            the colour channels.
        """
        known = {member.value: member for member in cls}
        return known.get(output_name, cls.RGB)

    @property
    def image_index(self) -> int:
        """
        The index of the channel in an RGBA pixel; the colour channels read red, which
        stands for a greyscale image stored as colour.
        """
        return {
            TextureChannel.RGB: 0,
            TextureChannel.RED: 0,
            TextureChannel.GREEN: 1,
            TextureChannel.BLUE: 2,
            TextureChannel.ALPHA: 3,
        }[self]


class ColorSpace(StrEnum):
    """
    How a texture's stored values relate to linear light, named as USD names its colour
    spaces.
    """

    AUTO = "auto"
    """
    The reader decides from the image file.
    """

    SRGB = "sRGB"
    """
    The values are sRGB encoded colours.
    """

    RAW = "raw"
    """
    The values are data, such as roughness, used as stored.
    """

    @classmethod
    def of_name(cls, name: str) -> ColorSpace:
        """
        :param name: A colour space name as the stage declares it, possibly empty.
        :return: The colour space of that name, or :attr:`AUTO`.
        """
        known = {member.value: member for member in cls}
        return known.get(name, cls.AUTO)


# %% inputs


@dataclass(frozen=True)
class TextureFile:
    """
    One texture image a shader input reads.
    """

    path: Path
    """
    The resolved image file.
    """

    color_space: ColorSpace = ColorSpace.AUTO
    """
    The colour space the stage declares for the image.
    """

    channel: TextureChannel = TextureChannel.RGB
    """
    The channels the shader input reads.
    """


ShaderInputValue = Union[bool, int, float, str, Tuple[float, ...], TextureFile]
"""
The value of one authored shader input: a number, a flag, a token, a colour or vector,
or a texture file.
"""


@dataclass
class AuthoredMaterial:
    """
    A material bound on the stage, as the authored inputs of its surface shader.
    """

    name: str
    """
    The material's USD path, or a generated name for display-colour shading.
    """

    source: MaterialSource
    """
    The shading model the inputs belong to.
    """

    inputs: Dict[str, ShaderInputValue] = field(default_factory=dict)
    """
    The authored shader inputs by name, without the ``inputs:`` namespace.
    """

    shader_identifier: str = ""
    """
    The shader's identifier on the stage (MDL sub-identifier or ``info:id``), kept for
    the report when the source is unknown.
    """

    def texture_files(self) -> List[Path]:
        """
        :return: The image files the material's inputs read.
        """
        return [
            value.path
            for value in self.inputs.values()
            if isinstance(value, TextureFile)
        ]
