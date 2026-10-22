"""
The file references inside the files of a scene bundle: meshes and textures of URDF
models, material libraries of OBJ meshes, textures of material libraries and COLLADA
documents, and the buffers and images of glTF meshes.
"""

from __future__ import annotations

import re
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from xml.etree import ElementTree

from typing_extensions import Any, List, Mapping, Optional

from cramera_offline.exceptions import InvalidReference, UnreadableFile
from cramera_offline.json_file import JsonFile
from cramera_protocol.bundle.files import MeshFormat

# %% vocabulary


class DescriptionFormat(StrEnum):
    """
    The suffixes of kinematic model descriptions.
    """

    URDF = ".urdf"
    """
    The Unified Robot Description Format.
    """


class UrdfName(StrEnum):
    """
    The URDF elements and attributes that reference files.
    """

    MESH = "mesh"
    """
    A geometry drawn from a mesh file.
    """

    TEXTURE = "texture"
    """
    An image of a material.
    """

    FILENAME = "filename"
    """
    The attribute naming the file.
    """


class GltfKey(StrEnum):
    """
    The glTF keys that reference files.
    """

    BUFFERS = "buffers"
    """
    The binary payloads.
    """

    IMAGES = "images"
    """
    The textures.
    """

    URI = "uri"
    """
    The location of a buffer or image, absent when it is stored in the GLB file.
    """


class WavefrontDirective(StrEnum):
    """
    The OBJ and MTL statements that reference files.
    """

    MATERIAL_LIBRARY = "mtllib"
    """
    The material libraries of an OBJ mesh.
    """

    MAP_PREFIX = "map_"
    """
    The prefix of material texture maps such as ``map_Kd``.
    """

    BUMP = "bump"
    """
    A bump map.
    """

    NORMAL = "norm"
    """
    A normal map.
    """

    DISPLACEMENT = "disp"
    """
    A displacement map.
    """

    DECAL = "decal"
    """
    A decal map.
    """

    REFLECTION = "refl"
    """
    A reflection map.
    """


class TextureOption(StrEnum):
    """
    The options a material texture statement may give before its file name.
    """

    BLEND_HORIZONTAL = "-blendu"
    """
    Horizontal texture blending.
    """

    BLEND_VERTICAL = "-blendv"
    """
    Vertical texture blending.
    """

    COLOR_CORRECTION = "-cc"
    """
    Colour correction.
    """

    CLAMP = "-clamp"
    """
    Texture clamping.
    """

    BOOST = "-boost"
    """
    Mipmap sharpness.
    """

    RESOLUTION = "-texres"
    """
    The texture resolution.
    """

    BUMP_MULTIPLIER = "-bm"
    """
    The bump multiplier.
    """

    CHANNEL = "-imfchan"
    """
    The image channel used.
    """

    TYPE = "-type"
    """
    The reflection mapping.
    """

    COLOR_SPACE = "-colorspace"
    """
    The image's colour space.
    """

    RANGE = "-mm"
    """
    The base and gain of the values.
    """

    SCALE = "-s"
    """
    One to three scale factors.
    """

    OFFSET = "-o"
    """
    One to three offsets.
    """

    TURBULENCE = "-t"
    """
    One to three turbulence values.
    """


FIXED_OPTION_ARGUMENTS: Mapping[TextureOption, int] = MappingProxyType(
    {
        TextureOption.BLEND_HORIZONTAL: 1,
        TextureOption.BLEND_VERTICAL: 1,
        TextureOption.COLOR_CORRECTION: 1,
        TextureOption.CLAMP: 1,
        TextureOption.BOOST: 1,
        TextureOption.RESOLUTION: 1,
        TextureOption.BUMP_MULTIPLIER: 1,
        TextureOption.CHANNEL: 1,
        TextureOption.TYPE: 1,
        TextureOption.COLOR_SPACE: 1,
        TextureOption.RANGE: 2,
    }
)
"""
How many arguments each texture option with a fixed count takes.
"""

VECTOR_OPTION_ARGUMENTS = 3
"""
The most numbers the scale, offset and turbulence options take.
"""

WAVEFRONT_TOKEN = re.compile(r'"([^"]*)"|(\S+)')
"""
One token of an OBJ or MTL statement: quoted text, or text up to whitespace.
"""

WAVEFRONT_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
"""
A number argument of a texture option.
"""

WAVEFRONT_COMMENT = "#"
"""
Starts a comment that runs to the end of the line.
"""

COLLADA_IMAGES = ".//{*}library_images/{*}image//{*}init_from"
"""
The image locations of a COLLADA document; ``init_from`` inside effects names images by
identifier, not by file, and is left out.
"""

# %% readers


class ReferenceReader(ABC):
    """
    Reads the file references declared inside one format of file.
    """

    @abstractmethod
    def references(self, path: Path) -> List[str]:
        """
        :param path: A file of the reader's format.
        :return: The references the file declares, as written, in file order.
        :raises UnreadableFile: When the file cannot be parsed.
        :raises InvalidReference: When a declaration names no file.
        """


@dataclass(frozen=True)
class XmlDocument:
    """
    An XML file on disk.
    """

    path: Path
    """
    The file.
    """

    def root(self) -> ElementTree.Element:
        """
        The XML parser raises its own error for damaged documents; this is the one place
        where it becomes :class:`UnreadableFile`.

        :return: The document's root element.
        :raises UnreadableFile: When the file is not well-formed XML.
        """
        try:
            return ElementTree.parse(self.path).getroot()
        except ElementTree.ParseError as error:
            raise UnreadableFile(self.path, str(error)) from error


@dataclass(frozen=True)
class UrdfReferences(ReferenceReader):
    """
    The mesh and texture files of a URDF model.
    """

    def references(self, path: Path) -> List[str]:
        return [
            element.attrib[UrdfName.FILENAME]
            for element in XmlDocument(path).root().iter()
            if element.tag.rsplit("}", 1)[-1] in (UrdfName.MESH, UrdfName.TEXTURE)
            and UrdfName.FILENAME in element.attrib
        ]


@dataclass(frozen=True)
class ColladaReferences(ReferenceReader):
    """
    The image files of a COLLADA document.
    """

    def references(self, path: Path) -> List[str]:
        return [
            "".join(element.itertext()).strip()
            for element in XmlDocument(path).root().findall(COLLADA_IMAGES)
        ]


@dataclass(frozen=True)
class WavefrontStatement:
    """
    One line of an OBJ or MTL file, split into its tokens.
    """

    line: str
    """
    The line as the file holds it.
    """

    def tokens(self) -> List[str]:
        """
        :return: The tokens before a comment; quoted tokens without their quotes.
        """
        tokens: List[str] = []
        for match in WAVEFRONT_TOKEN.finditer(self.line):
            quoted, plain = match.groups()
            if plain is not None and plain.startswith(WAVEFRONT_COMMENT):
                break
            tokens.append(quoted if quoted is not None else plain)
        return tokens


@dataclass(frozen=True)
class ObjReferences(ReferenceReader):
    """
    The material libraries of an OBJ mesh; one ``mtllib`` line may name several.
    """

    def references(self, path: Path) -> List[str]:
        references: List[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            tokens = WavefrontStatement(line).tokens()
            if not tokens or tokens[0] != WavefrontDirective.MATERIAL_LIBRARY:
                continue
            if len(tokens) == 1:
                raise InvalidReference(path, line)
            references.extend(tokens[1:])
        return references


@dataclass(frozen=True)
class MaterialLibraryReferences(ReferenceReader):
    """
    The texture files of an MTL material library.
    """

    texture_directives: frozenset[str] = field(
        default=frozenset(
            {
                WavefrontDirective.BUMP,
                WavefrontDirective.NORMAL,
                WavefrontDirective.DISPLACEMENT,
                WavefrontDirective.DECAL,
                WavefrontDirective.REFLECTION,
            }
        )
    )
    """
    The texture statements whose names do not start with ``map_``.
    """

    def references(self, path: Path) -> List[str]:
        references: List[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            tokens = WavefrontStatement(line).tokens()
            if tokens and self.is_texture(tokens[0]):
                references.append(self.texture_file(path, line, tokens[1:]))
        return references

    def is_texture(self, directive: str) -> bool:
        """
        :param directive: The first token of a statement.
        :return: Whether the statement names a texture file.
        """
        lowered = directive.lower()
        return (
            lowered.startswith(WavefrontDirective.MAP_PREFIX)
            or lowered in self.texture_directives
        )

    def texture_file(self, path: Path, line: str, arguments: List[str]) -> str:
        """
        :param path: The material library.
        :param line: The texture statement.
        :param arguments: The tokens after the statement's directive.
        :return: The file name after the options, unquoted spaces included.
        :raises InvalidReference: When an option is unknown or lacks its arguments,
            or no file name follows the options.
        """
        position = 0
        while position < len(arguments) and arguments[position].startswith("-"):
            option = arguments[position].lower()
            position += 1
            if option in (
                TextureOption.SCALE,
                TextureOption.OFFSET,
                TextureOption.TURBULENCE,
            ):
                first = position
                limit = min(first + VECTOR_OPTION_ARGUMENTS, len(arguments))
                while position < limit and WAVEFRONT_NUMBER.fullmatch(
                    arguments[position]
                ):
                    position += 1
                if position == first:
                    raise InvalidReference(path, line)
            elif option in FIXED_OPTION_ARGUMENTS:
                position += FIXED_OPTION_ARGUMENTS[TextureOption(option)]
            else:
                raise InvalidReference(path, line)
        if position >= len(arguments):
            raise InvalidReference(path, line)
        return " ".join(arguments[position:])


@dataclass(frozen=True)
class GltfReferences(ReferenceReader):
    """
    The buffer and image files of a glTF mesh.
    """

    def references(self, path: Path) -> List[str]:
        return self.document_references(path, JsonFile(path).read())

    @staticmethod
    def document_references(path: Path, document: Any) -> List[str]:
        """
        :param path: The file holding the document.
        :param document: A decoded glTF JSON document.
        :return: The locations of its buffers and images that are not stored in a GLB
            file.
        :raises UnreadableFile: When the document is not a JSON object.
        """
        if not isinstance(document, dict):
            raise UnreadableFile(path, "a glTF document is a JSON object")
        return [
            entry[GltfKey.URI]
            for category in (GltfKey.BUFFERS, GltfKey.IMAGES)
            for entry in document.get(category, [])
            if GltfKey.URI in entry
        ]


@dataclass(frozen=True)
class GlbReferences(ReferenceReader):
    """
    The buffer and image files of a binary glTF mesh, read from its JSON chunk.
    """

    header: struct.Struct = field(default=struct.Struct("<4sII"))
    """
    The file header: magic, container version and file length.
    """

    chunk_header: struct.Struct = field(default=struct.Struct("<II"))
    """
    A chunk header: payload length and chunk type.
    """

    magic: bytes = b"glTF"
    """
    The first bytes of every GLB file.
    """

    container_version: int = 2
    """
    The GLB container version this reader understands.
    """

    json_chunk: int = 0x4E4F534A
    """
    The type of the chunk holding the glTF JSON document, ``JSON`` in ASCII.
    """

    def references(self, path: Path) -> List[str]:
        data = path.read_bytes()
        chunk = self.json_chunk_of(data)
        if chunk is None:
            raise UnreadableFile(path, "no valid glTF JSON chunk")
        text = chunk.decode("utf-8", errors="replace")
        return GltfReferences.document_references(path, JsonFile.decode(path, text))

    def json_chunk_of(self, data: bytes) -> Optional[bytes]:
        """
        :param data: The content of a GLB file.
        :return: The payload of its JSON chunk, or None when the header or the chunks
            are damaged or no JSON chunk exists.
        """
        if len(data) < self.header.size:
            return None
        magic, version, length = self.header.unpack_from(data)
        if magic != self.magic or version != self.container_version:
            return None
        if length != len(data):
            return None
        offset = self.header.size
        while offset + self.chunk_header.size <= len(data):
            chunk_length, kind = self.chunk_header.unpack_from(data, offset)
            offset += self.chunk_header.size
            if offset + chunk_length > len(data):
                return None
            if kind == self.json_chunk:
                return data[offset : offset + chunk_length]
            offset += chunk_length
        return None


# %% formats


@dataclass(frozen=True)
class ReferenceReaders:
    """
    The reference reader of each file format that references other files.
    """

    readers: Mapping[str, ReferenceReader] = field(
        default_factory=lambda: MappingProxyType(
            {
                DescriptionFormat.URDF: UrdfReferences(),
                MeshFormat.COLLADA: ColladaReferences(),
                MeshFormat.OBJ: ObjReferences(),
                MeshFormat.MATERIAL_LIBRARY: MaterialLibraryReferences(),
                MeshFormat.GLTF: GltfReferences(),
                MeshFormat.GLB: GlbReferences(),
            }
        )
    )
    """
    The readers by the lower-case suffix of their format.
    """

    def references(self, path: Path) -> List[str]:
        """
        :param path: A file of a bundle.
        :return: The references it declares; none for formats that reference no
            files, such as STL meshes and images.
        :raises UnreadableFile: When the file cannot be parsed.
        :raises InvalidReference: When a declaration names no file.
        """
        reader = self.readers.get(path.suffix.lower())
        if reader is None:
            return []
        return reader.references(path)
