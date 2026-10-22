"""
Reading GLB files back, to check what the writer wrote.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass

import numpy
from typing_extensions import Any, Dict, Self

from cramera_usd.gltf.format import (
    AccessorType,
    ComponentType,
    GlbSize,
    GltfKey,
)

# %% container layout

LENGTH_LAYOUT = "<I"
"""
The layout of a chunk's length.
"""

# %% content


@dataclass
class GlbContent:
    """
    The JSON and binary chunks of a GLB file, with accessor reading.
    """

    document: Dict[str, Any]
    """
    The parsed JSON chunk.
    """

    binary: bytes
    """
    The binary chunk.
    """

    @classmethod
    def of_bytes(cls, data: bytes) -> Self:
        """
        :param data: A GLB file's content.
        :return: Its chunks.
        """
        json_start = GlbSize.HEADER + GlbSize.CHUNK_HEADER
        json_length = struct.unpack_from(LENGTH_LAYOUT, data, GlbSize.HEADER)[0]
        document = json.loads(data[json_start : json_start + json_length])
        return cls(document, data[json_start + json_length + GlbSize.CHUNK_HEADER :])

    def accessor(self, index: int) -> numpy.ndarray:
        """
        :param index: An accessor index.
        :return: The accessor's values.
        """
        accessor = self.document[GltfKey.ACCESSORS][index]
        view = self.document[GltfKey.BUFFER_VIEWS][accessor[GltfKey.BUFFER_VIEW]]
        width = AccessorType(accessor[GltfKey.TYPE]).width
        values = numpy.frombuffer(
            self.binary,
            dtype=ComponentType(accessor[GltfKey.COMPONENT_TYPE]).numpy_type,
            count=accessor[GltfKey.COUNT] * width,
            offset=view[GltfKey.BYTE_OFFSET],
        )
        return values.reshape(-1, width) if width > 1 else values

    def primitive(self, node: int) -> Dict[str, Any]:
        """
        :param node: A node index.
        :return: The only primitive of the node's mesh.
        """
        mesh = self.document[GltfKey.NODES][node][GltfKey.MESH]
        return self.document[GltfKey.MESHES][mesh][GltfKey.PRIMITIVES][0]

    def embedded(self, image: int) -> bytes:
        """
        :param image: An image index.
        :return: The bytes of the embedded image.
        """
        view = self.document[GltfKey.BUFFER_VIEWS][
            self.document[GltfKey.IMAGES][image][GltfKey.BUFFER_VIEW]
        ]
        start = view[GltfKey.BYTE_OFFSET]
        return self.binary[start : start + view[GltfKey.BYTE_LENGTH]]
