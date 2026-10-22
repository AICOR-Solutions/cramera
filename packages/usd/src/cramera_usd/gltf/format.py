"""
The names and numbers of the glTF 2.0 and GLB formats the writer uses.
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum

import numpy
from typing_extensions import Type

# %% format constants


class ComponentType(IntEnum):
    """
    The glTF accessor component types the writer uses.
    """

    UNSIGNED_SHORT = 5123
    """
    16-bit unsigned integer indices.
    """

    UNSIGNED_INT = 5125
    """
    32-bit unsigned integer indices.
    """

    FLOAT = 5126
    """
    32-bit float attributes.
    """

    @classmethod
    def indices_for(cls, vertex_count: int) -> ComponentType:
        """
        :param vertex_count: The number of vertices.
        :return: The smallest index type addressing that many vertices; glTF reserves
            the largest value of each type, so it never indexes a vertex.
        """
        if vertex_count <= numpy.iinfo(numpy.uint16).max:
            return cls.UNSIGNED_SHORT
        return cls.UNSIGNED_INT

    @property
    def numpy_type(self) -> Type[numpy.generic]:
        """
        The numpy type holding one component.
        """
        return {
            ComponentType.UNSIGNED_SHORT: numpy.uint16,
            ComponentType.UNSIGNED_INT: numpy.uint32,
            ComponentType.FLOAT: numpy.float32,
        }[self]


class BufferTarget(IntEnum):
    """
    What a buffer view holds, as WebGL binds it.
    """

    ARRAY_BUFFER = 34962
    """
    Vertex attributes.
    """

    ELEMENT_ARRAY_BUFFER = 34963
    """
    Triangle indices.
    """


class SamplerSetting(IntEnum):
    """
    The texture sampler settings the writer uses.
    """

    LINEAR = 9729
    """
    Linear magnification.
    """

    LINEAR_MIPMAP_LINEAR = 9987
    """
    Trilinear minification.
    """

    REPEAT = 10497
    """
    Tiling outside the unit square, which baked-in tiling relies on.
    """


class GlbChunk(IntEnum):
    """
    The magic numbers of the GLB container.
    """

    MAGIC = 0x46546C67
    """
    ``glTF`` in little endian, at the start of the file.
    """

    VERSION = 2
    """
    The container version.
    """

    JSON = 0x4E4F534A
    """
    The type of the JSON chunk.
    """

    BINARY = 0x004E4942
    """
    The type of the binary chunk.
    """


class GltfExtension(StrEnum):
    """
    The glTF extensions the writer may use.
    """

    INDEX_OF_REFRACTION = "KHR_materials_ior"
    """
    The index of refraction.
    """

    CLEARCOAT = "KHR_materials_clearcoat"
    """
    A clear coat layer.
    """

    EMISSIVE_STRENGTH = "KHR_materials_emissive_strength"
    """
    Emission brighter than the unit range.
    """

    ANISOTROPY = "KHR_materials_anisotropy"
    """
    Anisotropic reflection.
    """

    TEXTURE_TRANSFORM = "KHR_texture_transform"
    """
    Offset and scale of texture coordinates.
    """


class AttributeName(StrEnum):
    """
    The vertex attributes the writer emits.
    """

    POSITION = "POSITION"
    """
    Vertex positions.
    """

    NORMAL = "NORMAL"
    """
    Vertex normals.
    """

    TEXTURE_COORDINATES = "TEXCOORD_0"
    """
    The first texture coordinate set.
    """


class ImageType(StrEnum):
    """
    The image encodings glTF allows without extensions.
    """

    PNG = "image/png"
    """
    PNG images.
    """

    JPEG = "image/jpeg"
    """
    JPEG images.
    """

    @property
    def signature(self) -> bytes:
        """
        The bytes an image file of this type starts with.
        """
        return {ImageType.PNG: b"\x89PNG", ImageType.JPEG: b"\xff\xd8"}[self]


class GltfKey(StrEnum):
    """
    The property names of the glTF document structure the writer emits, as glTF 2.0
    names them.
    """

    ASSET = "asset"
    """
    The document's metadata.
    """

    VERSION = "version"
    """
    The glTF version the document follows.
    """

    GENERATOR = "generator"
    """
    The tool that wrote the document.
    """

    SCENE = "scene"
    """
    The index of the scene shown by default.
    """

    SCENES = "scenes"
    """
    The scenes, each a list of root nodes.
    """

    NODES = "nodes"
    """
    The nodes; in a scene, the indices of its root nodes.
    """

    MESHES = "meshes"
    """
    The meshes.
    """

    MATERIALS = "materials"
    """
    The materials.
    """

    ACCESSORS = "accessors"
    """
    The typed views of buffer data.
    """

    BUFFER_VIEWS = "bufferViews"
    """
    The byte ranges of the buffers.
    """

    BUFFERS = "buffers"
    """
    The binary buffers.
    """

    SAMPLERS = "samplers"
    """
    The texture samplers.
    """

    IMAGES = "images"
    """
    The embedded images.
    """

    TEXTURES = "textures"
    """
    The textures, each an image with a sampler.
    """

    EXTENSIONS_USED = "extensionsUsed"
    """
    The extensions the document uses.
    """

    EXTENSIONS = "extensions"
    """
    The extension objects of a property.
    """

    EXTRAS = "extras"
    """
    Application data stored on a property.
    """

    NAME = "name"
    """
    The name of a node, mesh or material.
    """

    MAGNIFICATION_FILTER = "magFilter"
    """
    How a sampler magnifies a texture.
    """

    MINIFICATION_FILTER = "minFilter"
    """
    How a sampler minifies a texture.
    """

    WRAP_S = "wrapS"
    """
    How a sampler wraps the first texture coordinate.
    """

    WRAP_T = "wrapT"
    """
    How a sampler wraps the second texture coordinate.
    """

    BUFFER = "buffer"
    """
    The buffer a buffer view lies in.
    """

    BYTE_OFFSET = "byteOffset"
    """
    Where a buffer view starts in its buffer.
    """

    BYTE_LENGTH = "byteLength"
    """
    The number of bytes of a buffer or buffer view.
    """

    TARGET = "target"
    """
    What a buffer view holds, as WebGL binds it.
    """

    BUFFER_VIEW = "bufferView"
    """
    The buffer view an accessor or image reads.
    """

    COMPONENT_TYPE = "componentType"
    """
    The type of an accessor's components.
    """

    COUNT = "count"
    """
    The number of elements of an accessor.
    """

    TYPE = "type"
    """
    Whether an accessor's elements are scalars or vectors.
    """

    MINIMUM = "min"
    """
    The smallest value of each component of an accessor.
    """

    MAXIMUM = "max"
    """
    The largest value of each component of an accessor.
    """

    MIME_TYPE = "mimeType"
    """
    The encoding of an embedded image.
    """

    SOURCE = "source"
    """
    The image of a texture.
    """

    SAMPLER = "sampler"
    """
    The sampler of a texture.
    """

    INDEX = "index"
    """
    The texture a texture reference points at.
    """

    OFFSET = "offset"
    """
    The shift of texture coordinates.
    """

    SCALE = "scale"
    """
    The scale of texture coordinates, or the strength of a normal map.
    """

    PRIMITIVES = "primitives"
    """
    The drawable parts of a mesh.
    """

    ATTRIBUTES = "attributes"
    """
    The vertex attributes of a primitive.
    """

    INDICES = "indices"
    """
    The triangle indices of a primitive.
    """

    MATERIAL = "material"
    """
    The material of a primitive.
    """

    MESH = "mesh"
    """
    The mesh of a node.
    """


class MaterialKey(StrEnum):
    """
    The property names of a glTF material and its extensions the writer emits.
    """

    METALLIC_ROUGHNESS = "pbrMetallicRoughness"
    """
    The metallic-roughness parameters.
    """

    BASE_COLOR_FACTOR = "baseColorFactor"
    """
    The linear base colour and opacity.
    """

    BASE_COLOR_TEXTURE = "baseColorTexture"
    """
    The base colour texture.
    """

    METALLIC_FACTOR = "metallicFactor"
    """
    The metalness.
    """

    ROUGHNESS_FACTOR = "roughnessFactor"
    """
    The roughness.
    """

    METALLIC_ROUGHNESS_TEXTURE = "metallicRoughnessTexture"
    """
    The texture holding roughness in green and metalness in blue.
    """

    DOUBLE_SIDED = "doubleSided"
    """
    Whether both sides of each triangle are drawn.
    """

    NORMAL_TEXTURE = "normalTexture"
    """
    The normal map.
    """

    EMISSIVE_FACTOR = "emissiveFactor"
    """
    The linear emitted colour.
    """

    EMISSIVE_TEXTURE = "emissiveTexture"
    """
    The emitted colour texture.
    """

    ALPHA_MODE = "alphaMode"
    """
    How the opacity is used.
    """

    ALPHA_CUTOFF = "alphaCutoff"
    """
    The opacity below which a masked surface is cut out.
    """

    TRANSMISSION_FACTOR = "transmissionFactor"
    """
    The share of light passing through the surface, named as
    ``KHR_materials_transmission`` names it.
    """

    INDEX_OF_REFRACTION = "ior"
    """
    The index of refraction.
    """

    CLEARCOAT_FACTOR = "clearcoatFactor"
    """
    The strength of the clear coat.
    """

    CLEARCOAT_ROUGHNESS_FACTOR = "clearcoatRoughnessFactor"
    """
    The roughness of the clear coat.
    """

    EMISSIVE_STRENGTH = "emissiveStrength"
    """
    The factor scaling the emitted colour.
    """

    ANISOTROPY_STRENGTH = "anisotropyStrength"
    """
    The strength of the anisotropic reflection.
    """


class NodeExtra(StrEnum):
    """
    The application data the writer stores on each node besides the semantic attributes.
    """

    USD_PATH = "usdPath"
    """
    The prim the node stands for: the common ancestor of the merged prims.
    """

    USD_PATHS = "usdPaths"
    """
    Every prim merged into the node.
    """


class AssetInformation(StrEnum):
    """
    What the writer states about the document in its ``asset`` property.
    """

    VERSION = "2.0"
    """
    The glTF version.
    """

    GENERATOR = "cramera-import"
    """
    The tool that wrote the document.
    """


class AccessorType(StrEnum):
    """
    The shapes of an accessor's elements the writer uses.
    """

    SCALAR = "SCALAR"
    """
    One component.
    """

    VECTOR_2 = "VEC2"
    """
    Two components, such as texture coordinates.
    """

    VECTOR_3 = "VEC3"
    """
    Three components, such as positions and normals.
    """

    @classmethod
    def of_width(cls, width: int) -> AccessorType:
        """
        :param width: A number of components.
        :return: The element shape with that many components.
        """
        return next(member for member in cls if member.width == width)

    @property
    def width(self) -> int:
        """
        The number of components.
        """
        return {
            AccessorType.SCALAR: 1,
            AccessorType.VECTOR_2: 2,
            AccessorType.VECTOR_3: 3,
        }[self]


class GlbSize(IntEnum):
    """
    The byte sizes of the parts of the GLB container.
    """

    ALIGNMENT = 4
    """
    Every chunk starts and ends on a multiple of this many bytes.
    """

    CHUNK_HEADER = 8
    """
    The length and type preceding each chunk.
    """

    HEADER = 12
    """
    The magic number, version and total length at the start of the file.
    """


class StructLayout(StrEnum):
    """
    The ``struct`` layouts of the GLB container's headers, little endian.
    """

    HEADER = "<III"
    """
    The magic number, version and total length.
    """

    CHUNK_HEADER = "<II"
    """
    A chunk's length and type.
    """


class Padding(bytes, Enum):
    """
    The bytes that fill a chunk up to its alignment.
    """

    JSON = b" "
    """
    The JSON chunk is padded with spaces.
    """

    BINARY = b"\0"
    """
    The binary chunk is padded with zeros.
    """


COMPACT_SEPARATORS = (",", ":")
"""
The item and key separators of JSON without optional whitespace.
"""
