"""
Texture images as the converter embeds them: the pixels of a texture file, the atlas the
tiles of a UDIM set make, and the largest size an embedded image keeps.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PIL import Image
from typing_extensions import Dict, List, Optional, Tuple

from cramera_usd.scene.materials import TextureFile, TileGrid

# %% vocabulary


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

    GREYSCALE = "L"
    """
    One 8-bit channel.
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

    JPEG = "JPEG"
    """
    JPEG, for images that were JPEG files already.
    """


ImageSize = Tuple[int, int]
"""
The width and height of an image in pixels.
"""

JPEG_QUALITY = 90
"""
The quality a JPEG file is encoded at again when it is scaled down.
"""

# %% size limit

DEFAULT_TEXTURE_SIZE = 1024
"""
The longest side an embedded image keeps unless the conversion asks for another.

Each GLB of a bundle embeds the textures its link draws, so a texture shared by many
links is uploaded to the browser's GPU once per link: the 66 textures of the SimReady
items in LabAutomationTwin's S2 lab, 4096 pixels square, are embedded 247 times and need
20.8 GB of texture memory, 1.4 GB at this size.
"""


@dataclass(frozen=True)
class TextureSizeLimit:
    """
    The largest image the converter embeds, by its longer side; a larger image is scaled
    down to it, keeping its aspect ratio.
    """

    longest_side: Optional[int] = DEFAULT_TEXTURE_SIZE
    """
    The longest side in pixels, or None to embed every image at its own size.
    """

    def fitted(self, size: ImageSize) -> ImageSize:
        """
        :param size: The size of an image.
        :return: The size it is embedded at.
        """
        width, height = size
        if self.longest_side is None or max(width, height) <= self.longest_side:
            return size
        scale = self.longest_side / max(width, height)
        return max(1, round(width * scale)), max(1, round(height * scale))


# %% texture images


@dataclass(frozen=True)
class TextureImage:
    """
    The pixels of a texture file: its image, or one atlas image of a UDIM set's tiles,
    each in the unit square of texture coordinates it covers.

    In the atlas of a grid of ``C`` columns and ``R`` rows, the tile in column ``c`` and
    row ``r`` sits ``c`` tiles from the left and ``R - 1 - r`` tiles from the top, since V
    grows upwards; the texture coordinates ``(u / C, v / R)`` read the atlas where
    ``(u, v)`` read the tiles.
    """

    texture: TextureFile
    """
    The texture file.
    """

    @property
    def tile_size(self) -> ImageSize:
        """
        The size of one tile: the largest tile's width and height, or the size of a
        single image.
        """
        sizes = [self.size_of(path) for path in self.texture.files]
        return max(width for width, _ in sizes), max(height for _, height in sizes)

    @property
    def size(self) -> ImageSize:
        """
        The size of the texture's image, its atlas for a UDIM set.
        """
        return self.size_on(self.texture.grid)

    def size_on(self, grid: TileGrid) -> ImageSize:
        """
        :param grid: A grid of unit squares.
        :return: The size of the texture laid out on the grid, one tile per square.
        """
        width, height = self.tile_size
        return width * grid.columns, height * grid.rows

    def opened(
        self, grid: Optional[TileGrid] = None, size: Optional[ImageSize] = None
    ) -> Image.Image:
        """
        :param grid: The grid to lay the texture out on, or None for the texture's own.
        :param size: The size of the result, or None for :meth:`size_on` the grid.
        :return: The texture's pixels: a UDIM set's tiles in their squares, black where
            the set has no tile, and a single image in every square, as the repeating
            sampler of every embedded texture draws it.
        """
        grid = self.texture.grid if grid is None else grid
        image = Image.open(self.texture.path) if grid.single else self.atlas_on(grid)
        if size is not None and image.size != size:
            image = image.resize(size, Image.Resampling.BILINEAR)
        return image

    def atlas_on(self, grid: TileGrid) -> Image.Image:
        """
        :param grid: A grid of unit squares.
        :return: One image of the texture laid out on the grid.
        """
        tile_width, tile_height = self.tile_size
        images: Dict[Path, Image.Image] = {}
        for _, path in self.placements(grid):
            if path not in images:
                images[path] = self.tile_image(path, (tile_width, tile_height))
        first = next(iter(images.values()))
        atlas = Image.new(
            first.mode, (tile_width * grid.columns, tile_height * grid.rows)
        )
        for (column, row), path in self.placements(grid):
            atlas.paste(
                images[path], (column * tile_width, (grid.rows - 1 - row) * tile_height)
            )
        return atlas

    def placements(self, grid: TileGrid) -> List[Tuple[Tuple[int, int], Path]]:
        """
        :param grid: A grid of unit squares.
        :return: The image of each square of the grid the texture covers, by column and
            row.
        """
        if self.texture.tiles:
            return [
                ((tile.column, tile.row), tile.path)
                for tile in self.texture.tiles
                if tile.column < grid.columns and tile.row < grid.rows
            ]
        return [
            ((column, row), self.texture.path)
            for column in range(grid.columns)
            for row in range(grid.rows)
        ]

    def tile_image(self, path: Path, size: ImageSize) -> Image.Image:
        """
        :param path: The image file of one tile.
        :param size: The size of every tile.
        :return: The tile at that size, in the mode of the texture's first file (a
            palette resolved to colours with alpha).
        """
        with Image.open(self.texture.files[0]) as first:
            mode = ImageMode.RGBA if first.mode == ImageMode.PALETTE else first.mode
        image = Image.open(path)
        if image.mode != mode:
            image = image.convert(mode)
        if image.size != size:
            image = image.resize(size, Image.Resampling.BILINEAR)
        return image

    @staticmethod
    def size_of(path: Path) -> ImageSize:
        """
        :param path: An image file.
        :return: Its size, read from its header.
        """
        with Image.open(path) as image:
            return image.size
