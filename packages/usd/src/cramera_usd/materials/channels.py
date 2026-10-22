"""
Texture channels as numbers: one channel of an image, a scalar property that blends a
constant with a texture, the glTF metallic-roughness texture packed from two of them,
and the sRGB decoding of colour textures.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import IntEnum, StrEnum

import numpy
from PIL import Image
from typing_extensions import Optional, Tuple

from cramera_usd.scene.materials import TextureChannel, TextureFile

# %% image values


class ChannelScale(IntEnum):
    """
    The largest stored value of one channel, by bit depth.
    """

    EIGHT_BIT = 255
    """
    The largest value of an 8-bit channel.
    """

    SIXTEEN_BIT = 65535
    """
    The largest value of a 16-bit channel.
    """


class ImageMode(StrEnum):
    """
    The Pillow image modes the reader and the packer treat specially.
    """

    PALETTE = "P"
    """
    Colours looked up in a palette.
    """

    RGBA = "RGBA"
    """
    Red, green, blue and alpha.
    """

    RGB = "RGB"
    """
    Red, green and blue.
    """

    INTEGER_PREFIX = "I"
    """
    The prefix of the modes holding integers of more than eight bits.
    """


class ImageFormat(StrEnum):
    """
    The image formats the converter encodes.
    """

    PNG = "PNG"
    """
    Portable Network Graphics.
    """


ImageSize = Tuple[int, int]
"""
The width and height of an image in pixels.
"""


@dataclass
class TextureChannelReader:
    """
    Reads one channel of an image as floats between 0 and 1, whatever its bit depth.
    """

    image: Image.Image
    """
    The opened image.
    """

    def values(self, channel: TextureChannel) -> numpy.ndarray:
        """
        :param channel: The channel to read; :attr:`TextureChannel.RGB` reads red, which
            stands for a greyscale image stored as colour.
        :return: The channel's values; a single-channel image answers every channel.
        """
        image = (
            self.image.convert(ImageMode.RGBA)
            if self.image.mode == ImageMode.PALETTE
            else self.image
        )
        pixels = numpy.asarray(image)
        scale = float(
            ChannelScale.SIXTEEN_BIT
            if image.mode.startswith(ImageMode.INTEGER_PREFIX)
            else ChannelScale.EIGHT_BIT
        )
        if pixels.ndim == 2:
            return pixels.astype(numpy.float64) / scale
        index = min(channel.image_index, pixels.shape[-1] - 1)
        return pixels[..., index].astype(numpy.float64) / scale


# %% scalar properties


@dataclass(frozen=True)
class ScalarChannel:
    """
    A scalar material property that blends a constant with a greyscale texture,
    ``(1 - influence) * constant + influence * texture``, as OmniPBR does.
    """

    constant: float
    """
    The value without a texture.
    """

    texture: Optional[TextureFile] = None
    """
    The texture holding the value per texel, or None for the constant alone.
    """

    influence: float = 1.0
    """
    How much the texture replaces the constant, between 0 and 1.
    """

    @property
    def textured(self) -> bool:
        """
        Whether the texture contributes to the value.
        """
        return self.texture is not None and self.influence > 0.0

    def texel_values(self, size: Optional[ImageSize]) -> numpy.ndarray:
        """
        :param size: The size to resample the texture to, or None to keep the
            texture's own size.
        :return: The blended value per texel, between 0 and 1.
        """
        image = Image.open(self.texture.path)
        if size is not None and image.size != size:
            image = image.resize(size, Image.Resampling.BILINEAR)
        values = TextureChannelReader(image).values(self.texture.channel)
        return (1.0 - self.influence) * self.constant + self.influence * values

    def average(self) -> float:
        """
        :return: The value averaged over the texels, or the constant without a
            texture.
        """
        if not self.textured:
            return self.constant
        return float(self.texel_values(None).mean())

    def mixed_with(self, value: float, share: float) -> ScalarChannel:
        """
        :param value: A constant to blend in.
        :param share: The share of the constant, between 0 and 1.
        :return: The channel blended with the constant, ``(1 - share) * channel + share
            * value`` in every texel.
        """
        if share <= 0.0:
            return self
        if not self.textured or share >= 1.0:
            return ScalarChannel((1.0 - share) * self.constant + share * value)
        influence = (1.0 - share) * self.influence
        return ScalarChannel(
            ((1.0 - share) * (1.0 - self.influence) * self.constant + share * value)
            / (1.0 - influence),
            self.texture,
            influence,
        )


# %% packed texture


@dataclass(frozen=True)
class RoughnessMetallicTexture:
    """
    The glTF metallic-roughness texture packed from two greyscale sources: roughness in
    the green channel and metalness in the blue channel.
    """

    roughness: ScalarChannel
    """
    The roughness source.
    """

    metallic: ScalarChannel
    """
    The metalness source.
    """

    def encode(self) -> bytes:
        """
        :return: The packed texture as PNG bytes, sized like the roughness texture (or
            the metalness texture when roughness is constant).
        """
        reference = self.roughness if self.roughness.textured else self.metallic
        size = Image.open(reference.texture.path).size
        green = self.channel_values(self.roughness, size)
        blue = self.channel_values(self.metallic, size)
        packed = numpy.stack(
            [numpy.full_like(green, ChannelScale.EIGHT_BIT), green, blue], axis=-1
        ).astype(numpy.uint8)
        stream = io.BytesIO()
        Image.fromarray(packed, mode=ImageMode.RGB).save(stream, format=ImageFormat.PNG)
        return stream.getvalue()

    @staticmethod
    def channel_values(channel: ScalarChannel, size: ImageSize) -> numpy.ndarray:
        """
        :param channel: The source of one channel.
        :param size: The size of the packed texture.
        :return: The channel's bytes at the packed size; a constant fills the whole
            image.
        """
        width, height = size
        if not channel.textured:
            return numpy.full(
                (height, width), round(channel.constant * ChannelScale.EIGHT_BIT)
            )
        return numpy.clip(
            numpy.round(channel.texel_values(size) * ChannelScale.EIGHT_BIT),
            0,
            ChannelScale.EIGHT_BIT,
        )


# %% colour decoding


@dataclass(frozen=True)
class SrgbTransfer:
    """
    The sRGB transfer function of IEC 61966-2-1, which turns encoded colour values into
    linear light as glTF viewers decode a base colour texture.
    """

    linear_limit: float = 0.04045
    """
    The largest encoded value on the linear segment near black.
    """

    linear_slope: float = 12.92
    """
    The ratio of encoded to linear values on the linear segment.
    """

    offset: float = 0.055
    """
    The offset of the power segment.
    """

    exponent: float = 2.4
    """
    The exponent of the power segment.
    """

    def decoded(self, encoded: numpy.ndarray) -> numpy.ndarray:
        """
        :param encoded: Encoded values between 0 and 1.
        :return: The linear values.
        """
        encoded = numpy.asarray(encoded, dtype=numpy.float64)
        return numpy.where(
            encoded <= self.linear_limit,
            encoded / self.linear_slope,
            ((encoded + self.offset) / (1.0 + self.offset)) ** self.exponent,
        )
