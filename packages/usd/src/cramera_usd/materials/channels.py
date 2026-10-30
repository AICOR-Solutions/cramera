"""
Texture channels as numbers: one channel of an image, a scalar property that blends a
constant with a texture, the glTF metallic-roughness texture packed from two of them, a
colour image composed with an opacity image, a normal map with a flipped tangent, and
the sRGB decoding of colour textures.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import IntEnum

import numpy
from PIL import Image
from typing_extensions import Optional

from cramera_usd.materials.images import (
    ImageFormat,
    ImageMode,
    ImageSize,
    TextureImage,
    TextureSizeLimit,
)
from cramera_usd.scene.materials import (
    TextureChannel,
    TextureFile,
    TileGrid,
)

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

    @property
    def grid(self) -> TileGrid:
        """
        The unit squares of texture coordinates the texture covers; one without a
        texture.
        """
        return self.texture.grid if self.textured else TileGrid()

    def texel_values(
        self, size: Optional[ImageSize], grid: Optional[TileGrid] = None
    ) -> numpy.ndarray:
        """
        :param size: The size to resample the texture to, or None to keep the
            texture's own size.
        :param grid: The grid to lay the texture out on, or None for the texture's
            own.
        :return: The blended value per texel, between 0 and 1.
        """
        image = TextureImage(self.texture).opened(grid, size)
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

    @property
    def grid(self) -> TileGrid:
        """
        The unit squares of texture coordinates the textured sources cover.
        """
        return self.roughness.grid.union(self.metallic.grid)

    def encode(self, limit: TextureSizeLimit) -> bytes:
        """
        :param limit: The largest image to embed.
        :return: The packed texture as PNG bytes, sized like the roughness texture (or
            the metalness texture when roughness is constant) within the limit.
        """
        reference = self.roughness if self.roughness.textured else self.metallic
        size = limit.fitted(TextureImage(reference.texture).size_on(self.grid))
        green = self.channel_values(self.roughness, size, self.grid)
        blue = self.channel_values(self.metallic, size, self.grid)
        packed = numpy.stack(
            [numpy.full_like(green, ChannelScale.EIGHT_BIT), green, blue], axis=-1
        ).astype(numpy.uint8)
        stream = io.BytesIO()
        Image.fromarray(packed, mode=ImageMode.RGB).save(stream, format=ImageFormat.PNG)
        return stream.getvalue()

    @staticmethod
    def channel_values(
        channel: ScalarChannel, size: ImageSize, grid: TileGrid
    ) -> numpy.ndarray:
        """
        :param channel: The source of one channel.
        :param size: The size of the packed texture.
        :param grid: The unit squares of texture coordinates the packed texture covers.
        :return: The channel's bytes at the packed size; a constant fills the whole
            image.
        """
        width, height = size
        if not channel.textured:
            return numpy.full(
                (height, width), round(channel.constant * ChannelScale.EIGHT_BIT)
            )
        return numpy.clip(
            numpy.round(channel.texel_values(size, grid) * ChannelScale.EIGHT_BIT),
            0,
            ChannelScale.EIGHT_BIT,
        )


# %% colour with opacity


@dataclass(frozen=True)
class ColorOpacityTexture:
    """
    The glTF base colour texture composed from a colour image and a separate opacity
    image: the colour in the red, green and blue channels, the opacity in alpha.
    """

    color: Optional[TextureFile]
    """
    The colour image, or None for white.
    """

    opacity: TextureFile
    """
    The opacity image; the average of its red, green and blue channels is the opacity,
    as OmniPBR's default opacity mode reads it.
    """

    @property
    def grid(self) -> TileGrid:
        """
        The unit squares of texture coordinates the colour and opacity images cover.
        """
        grid = self.opacity.grid
        return grid if self.color is None else grid.union(self.color.grid)

    def encode(self, limit: TextureSizeLimit) -> bytes:
        """
        :param limit: The largest image to embed.
        :return: The composed texture as PNG bytes, sized like the colour image (or the
            opacity image without one) within the limit.
        """
        grid = self.grid
        reference = self.opacity if self.color is None else self.color
        size = limit.fitted(TextureImage(reference).size_on(grid))
        width, height = size
        color = (
            numpy.full(
                (height, width, len(OPACITY_SOURCE_CHANNELS)), ChannelScale.EIGHT_BIT
            )
            if self.color is None
            else numpy.asarray(
                TextureImage(self.color).opened(grid, size).convert(ImageMode.RGB)
            )
        )
        reader = TextureChannelReader(TextureImage(self.opacity).opened(grid, size))
        opacity = numpy.mean(
            [reader.values(channel) for channel in OPACITY_SOURCE_CHANNELS], axis=0
        )
        composed = numpy.dstack(
            [color, numpy.round(opacity * ChannelScale.EIGHT_BIT)]
        ).astype(numpy.uint8)
        stream = io.BytesIO()
        Image.fromarray(composed, mode=ImageMode.RGBA).save(
            stream, format=ImageFormat.PNG
        )
        return stream.getvalue()


OPACITY_SOURCE_CHANNELS = (
    TextureChannel.RED,
    TextureChannel.GREEN,
    TextureChannel.BLUE,
)
"""
The channels of an opacity image that are averaged into the opacity.
"""


# %% normal map with a flipped tangent


@dataclass(frozen=True)
class FlippedNormalTexture:
    """
    A tangent-space normal map with the X or Y component of its normals flipped: the
    normal map of a shader whose tangent along U or along V points the other way than
    glTF's.
    """

    normal: TextureFile
    """
    The normal map as the stage authors it.
    """

    flip_x: bool
    """
    Whether the component along U, in the red channel, is flipped.
    """

    flip_y: bool
    """
    Whether the component along V, in the green channel, is flipped.
    """

    @property
    def grid(self) -> TileGrid:
        """
        The unit squares of texture coordinates the normal map covers.
        """
        return self.normal.grid

    def encode(self, limit: TextureSizeLimit) -> bytes:
        """
        :param limit: The largest image to embed.
        :return: The normal map as PNG bytes, the flipped channels inverted, within the
            limit.
        """
        image = TextureImage(self.normal)
        reader = TextureChannelReader(image.opened(size=limit.fitted(image.size)))
        flips = (self.flip_x, self.flip_y, False)
        channels = [
            1.0 - reader.values(channel) if flipped else reader.values(channel)
            for channel, flipped in zip(NORMAL_CHANNELS, flips)
        ]
        flipped = numpy.round(
            numpy.stack(channels, axis=-1) * ChannelScale.EIGHT_BIT
        ).astype(numpy.uint8)
        stream = io.BytesIO()
        Image.fromarray(flipped, mode=ImageMode.RGB).save(
            stream, format=ImageFormat.PNG
        )
        return stream.getvalue()


NORMAL_CHANNELS = (TextureChannel.RED, TextureChannel.GREEN, TextureChannel.BLUE)
"""
The channels of a normal map holding the X, Y and Z components of its normals.
"""


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
