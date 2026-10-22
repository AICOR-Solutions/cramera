"""
A glTF document under construction, with one binary buffer, written as a GLB file.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy
from PIL import Image
from typing_extensions import Any, Dict, Optional, Set, Tuple, Union

from cramera_usd.encoding import TEXT_ENCODING
from cramera_usd.gltf.format import (
    COMPACT_SEPARATORS,
    AccessorType,
    AssetInformation,
    AttributeName,
    BufferTarget,
    ComponentType,
    GlbChunk,
    GlbSize,
    GltfExtension,
    GltfKey,
    ImageType,
    Padding,
    SamplerSetting,
    StructLayout,
)
from cramera_usd.gltf.material import GltfMaterial
from cramera_usd.gltf.merged import MergedMesh
from cramera_usd.materials.channels import ImageFormat, RoughnessMetallicTexture
from cramera_usd.materials.physically_based import (
    PhysicallyBasedMaterial,
    TextureTransform,
)
from cramera_usd.materials.transmission import TransmissionBlending
from cramera_usd.scene.materials import TextureFile

# %% images

TextureSource = Union[TextureFile, RoughnessMetallicTexture]
"""
What a texture is made from: an image file, or roughness and metalness packed into one
image.
"""


@dataclass
class EmbeddedImage:
    """
    An image file as glTF can embed it: PNG and JPEG as they are, anything else re-
    encoded as PNG.
    """

    path: Path
    """
    The image file.
    """

    def encoded(self) -> Tuple[bytes, ImageType]:
        """
        :return: The image bytes and their type.
        """
        data = self.path.read_bytes()
        for image_type in ImageType:
            if data.startswith(image_type.signature):
                return data, image_type
        stream = io.BytesIO()
        Image.open(self.path).save(stream, format=ImageFormat.PNG)
        return stream.getvalue(), ImageType.PNG


# %% document


@dataclass
class GltfDocument:
    """
    A glTF document under construction, with one binary buffer.
    """

    json: Dict[str, Any] = field(
        default_factory=lambda: {
            GltfKey.ASSET: {
                GltfKey.VERSION: AssetInformation.VERSION,
                GltfKey.GENERATOR: AssetInformation.GENERATOR,
            },
            GltfKey.SCENE: 0,
            GltfKey.SCENES: [{GltfKey.NODES: []}],
            GltfKey.NODES: [],
            GltfKey.MESHES: [],
            GltfKey.MATERIALS: [],
            GltfKey.ACCESSORS: [],
            GltfKey.BUFFER_VIEWS: [],
            GltfKey.BUFFERS: [],
            GltfKey.SAMPLERS: [
                {
                    GltfKey.MAGNIFICATION_FILTER: SamplerSetting.LINEAR,
                    GltfKey.MINIFICATION_FILTER: SamplerSetting.LINEAR_MIPMAP_LINEAR,
                    GltfKey.WRAP_S: SamplerSetting.REPEAT,
                    GltfKey.WRAP_T: SamplerSetting.REPEAT,
                }
            ],
            GltfKey.IMAGES: [],
            GltfKey.TEXTURES: [],
        }
    )
    """
    The JSON part of the document.
    """

    binary: bytearray = field(default_factory=bytearray)
    """
    The binary buffer.
    """

    material_indices: Dict[PhysicallyBasedMaterial, int] = field(default_factory=dict)
    """
    The index of each material written so far.
    """

    texture_indices: Dict[TextureSource, int] = field(default_factory=dict)
    """
    The index of each texture written so far.
    """

    extensions: Set[GltfExtension] = field(default_factory=set)
    """
    The extensions the document uses.
    """

    blending: TransmissionBlending = field(default_factory=TransmissionBlending)
    """
    How transmissive surfaces are drawn, for viewers that cannot refract.
    """

    def appended(self, key: GltfKey, item: Dict[str, Any]) -> int:
        """
        Append an item to one of the document's lists.

        :param key: The list.
        :param item: The item.
        :return: The item's index in the list.
        """
        self.json[key].append(item)
        return len(self.json[key]) - 1

    def add_buffer_view(
        self, data: bytes, target: Optional[BufferTarget] = None
    ) -> int:
        """
        Append bytes to the buffer, aligned to four bytes, and describe them.

        :param data: The bytes.
        :param target: What the bytes hold, or None for images.
        :return: The index of the buffer view.
        """
        self.binary.extend(
            Padding.BINARY.value * (-len(self.binary) % GlbSize.ALIGNMENT)
        )
        view = {
            GltfKey.BUFFER: 0,
            GltfKey.BYTE_OFFSET: len(self.binary),
            GltfKey.BYTE_LENGTH: len(data),
        }
        if target is not None:
            view[GltfKey.TARGET] = target
        self.binary.extend(data)
        return self.appended(GltfKey.BUFFER_VIEWS, view)

    def add_accessor(
        self,
        values: numpy.ndarray,
        component_type: ComponentType,
        target: BufferTarget,
        with_bounds: bool = False,
    ) -> int:
        """
        Store an array and describe it as an accessor.

        :param values: A one-dimensional (scalars) or two-dimensional (vectors) array
            already of the component type.
        :param component_type: The type of each component.
        :param target: Whether the values are vertex attributes or indices.
        :param with_bounds: Whether to record the per-component minimum and maximum,
            which glTF requires for positions.
        :return: The index of the accessor.
        """
        values = numpy.ascontiguousarray(values)
        width = 1 if values.ndim == 1 else values.shape[1]
        accessor = {
            GltfKey.BUFFER_VIEW: self.add_buffer_view(values.tobytes(), target),
            GltfKey.COMPONENT_TYPE: component_type,
            GltfKey.COUNT: int(values.shape[0]),
            GltfKey.TYPE: AccessorType.of_width(width),
        }
        if with_bounds:
            accessor[GltfKey.MINIMUM] = [float(value) for value in values.min(axis=0)]
            accessor[GltfKey.MAXIMUM] = [float(value) for value in values.max(axis=0)]
        return self.appended(GltfKey.ACCESSORS, accessor)

    def add_texture(self, source: TextureSource) -> int:
        """
        Embed a texture once.

        :param source: An image file, or a texture packed from greyscale sources.
        :return: The index of the texture.
        """
        if source in self.texture_indices:
            return self.texture_indices[source]
        data, image_type = (
            (source.encode(), ImageType.PNG)
            if isinstance(source, RoughnessMetallicTexture)
            else EmbeddedImage(source.path).encoded()
        )
        image = self.appended(
            GltfKey.IMAGES,
            {
                GltfKey.BUFFER_VIEW: self.add_buffer_view(data),
                GltfKey.MIME_TYPE: image_type,
            },
        )
        self.texture_indices[source] = self.appended(
            GltfKey.TEXTURES, {GltfKey.SOURCE: image, GltfKey.SAMPLER: 0}
        )
        return self.texture_indices[source]

    def texture_reference(
        self, source: TextureSource, transform: Optional[TextureTransform]
    ) -> Dict[str, Any]:
        """
        :param source: A texture.
        :param transform: The material's change of texture coordinates, if any.
        :return: A glTF texture info pointing at the embedded texture.
        """
        reference: Dict[str, Any] = {GltfKey.INDEX: self.add_texture(source)}
        if transform is not None:
            self.extensions.add(GltfExtension.TEXTURE_TRANSFORM)
            reference[GltfKey.EXTENSIONS] = {
                GltfExtension.TEXTURE_TRANSFORM: {
                    GltfKey.OFFSET: list(transform.offset),
                    GltfKey.SCALE: list(transform.scale),
                }
            }
        return reference

    def add_material(self, material: PhysicallyBasedMaterial) -> int:
        """
        Write a material, and the textures it uses, once.

        :param material: The material.
        :return: The index of the material.
        """
        if material not in self.material_indices:
            self.material_indices[material] = self.appended(
                GltfKey.MATERIALS, GltfMaterial(material, self).to_json()
            )
        return self.material_indices[material]

    def add_mesh_node(
        self,
        name: str,
        extras: Dict[str, Any],
        mesh: MergedMesh,
        material: PhysicallyBasedMaterial,
    ) -> None:
        """
        Add one node holding one primitive.

        :param name: The node name.
        :param extras: Application data stored on the node.
        :param mesh: The geometry.
        :param material: The material of the geometry.
        """
        attributes = {
            AttributeName.POSITION: self.add_accessor(
                mesh.points, ComponentType.FLOAT, BufferTarget.ARRAY_BUFFER, True
            )
        }
        if mesh.normals is not None:
            attributes[AttributeName.NORMAL] = self.add_accessor(
                mesh.normals, ComponentType.FLOAT, BufferTarget.ARRAY_BUFFER
            )
        if mesh.texture_coordinates is not None:
            attributes[AttributeName.TEXTURE_COORDINATES] = self.add_accessor(
                mesh.texture_coordinates,
                ComponentType.FLOAT,
                BufferTarget.ARRAY_BUFFER,
            )
        index_type = ComponentType.indices_for(len(mesh.points))
        indices = self.add_accessor(
            mesh.triangles.ravel().astype(index_type.numpy_type),
            index_type,
            BufferTarget.ELEMENT_ARRAY_BUFFER,
        )
        primitive = {
            GltfKey.ATTRIBUTES: attributes,
            GltfKey.INDICES: indices,
            GltfKey.MATERIAL: self.add_material(material),
        }
        mesh_index = self.appended(
            GltfKey.MESHES, {GltfKey.NAME: name, GltfKey.PRIMITIVES: [primitive]}
        )
        node = self.appended(
            GltfKey.NODES,
            {GltfKey.NAME: name, GltfKey.MESH: mesh_index, GltfKey.EXTRAS: extras},
        )
        self.json[GltfKey.SCENES][0][GltfKey.NODES].append(node)

    def encode(self) -> bytes:
        """
        :return: The document as a GLB file.
        """
        self.binary.extend(
            Padding.BINARY.value * (-len(self.binary) % GlbSize.ALIGNMENT)
        )
        document = dict(self.json)
        document[GltfKey.BUFFERS] = [{GltfKey.BYTE_LENGTH: len(self.binary)}]
        if self.extensions:
            document[GltfKey.EXTENSIONS_USED] = sorted(self.extensions)
        for key in (GltfKey.IMAGES, GltfKey.TEXTURES, GltfKey.MATERIALS):
            if not document[key]:
                del document[key]
        if GltfKey.IMAGES not in document:
            del document[GltfKey.SAMPLERS]
        text = json.dumps(document, separators=COMPACT_SEPARATORS).encode(TEXT_ENCODING)
        text += Padding.JSON.value * (-len(text) % GlbSize.ALIGNMENT)
        total = (
            GlbSize.HEADER
            + GlbSize.CHUNK_HEADER
            + len(text)
            + GlbSize.CHUNK_HEADER
            + len(self.binary)
        )
        return b"".join(
            [
                struct.pack(
                    StructLayout.HEADER, GlbChunk.MAGIC, GlbChunk.VERSION, total
                ),
                struct.pack(StructLayout.CHUNK_HEADER, len(text), GlbChunk.JSON),
                text,
                struct.pack(
                    StructLayout.CHUNK_HEADER, len(self.binary), GlbChunk.BINARY
                ),
                bytes(self.binary),
            ]
        )
