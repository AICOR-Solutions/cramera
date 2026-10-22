"""
Serving library files to the browser's loaders: a URDF's mesh references and a glTF's
buffer and image references are rewritten into paths relative to the file, so every
request stays below the builder's asset route.
"""

from __future__ import annotations

import json
import posixpath
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from typing_extensions import Any, List, Optional

from cramera.http.messages import MediaType, Response
from cramera_protocol.bundle.files import MeshFormat
from cramera_scene_builder.exceptions import (
    DocumentTypeDeclaration,
    ExternalDependency,
    MalformedResourceDocument,
    MissingDependency,
)
from cramera_scene_builder.resources import (
    PATH_SEPARATOR,
    ModelSuffix,
    ResourceIdentifier,
    ResourceLibrary,
)

# %% vocabulary


class UrdfName(StrEnum):
    """
    The URDF elements and attributes that refer to other files.
    """

    MESH = "mesh"
    """
    A mesh of a link's visual or collision geometry.
    """

    TEXTURE = "texture"
    """
    A texture of a material.
    """

    FILE_NAME = "filename"
    """
    The attribute holding the reference.
    """


class GltfName(StrEnum):
    """
    The glTF collections and keys that refer to other files.
    """

    BUFFERS = "buffers"
    """
    The binary buffers.
    """

    IMAGES = "images"
    """
    The texture images.
    """

    URI = "uri"
    """
    The key holding the reference.
    """


class ReferenceScheme(StrEnum):
    """
    The URL schemes of references a model may hold.
    """

    PACKAGE = "package"
    """
    A file of a ROS package, ``package://<package>/<path>``.
    """

    DATA = "data"
    """
    Content embedded in the reference itself.
    """


DOCUMENT_DECLARATIONS = (b"<!DOCTYPE", b"<!ENTITY")
"""
The XML declarations a URDF must not hold, since they could expand without bound.
"""

PARENT_SEGMENTS = frozenset({"", ".", ".."})
"""
Segments a package reference must not hold.
"""

# %% dependencies


@dataclass
class DependencyResolver:
    """
    Finds the library file a model refers to, by a relative path or a package path.
    """

    library: ResourceLibrary
    """
    The library the model and its files belong to.
    """

    library_files: Optional[List[Path]] = field(default=None, init=False)
    """
    The library's files, listed once on the first package reference.
    """

    def resolve(
        self, model: ResourceIdentifier, path: Path, reference: str
    ) -> ResourceIdentifier:
        """
        :param model: The model holding the reference.
        :param path: The model's file.
        :param reference: The reference as the model writes it.
        :return: The file the reference names.
        :raises ExternalDependency: For an absolute path or a web address.
        :raises MissingDependency: When the library holds no such file.
        :raises OutsideLibrary: When the reference leads out of the library.
        """
        parts = urlsplit(reference)
        if parts.scheme == ReferenceScheme.PACKAGE:
            return self.package_file(
                model, reference, unquote(parts.netloc + parts.path)
            )
        relative = unquote(parts.path)
        if (
            parts.scheme
            or parts.netloc
            or parts.query
            or parts.fragment
            or Path(relative).is_absolute()
        ):
            raise ExternalDependency(model.text(), reference)
        target = path.parent / relative
        if not target.is_file():
            raise MissingDependency(model.text(), reference)
        dependency = self.library.identifier_of(target)
        self.library.file(dependency)
        return dependency

    def package_file(
        self, model: ResourceIdentifier, reference: str, relative: str
    ) -> ResourceIdentifier:
        """
        :param model: The model holding the reference.
        :param reference: The reference as the model writes it.
        :param relative: The package name and the path within the package.
        :return: The first library file whose path ends in the package path.
        :raises MissingDependency: When no library file does.
        """
        if any(
            segment in PARENT_SEGMENTS for segment in relative.split(PATH_SEPARATOR)
        ):
            raise ExternalDependency(model.text(), reference)
        if self.library_files is None:
            self.library_files = [path for _, path in self.library.files()]
        ending = f"{PATH_SEPARATOR}{relative}"
        for candidate in self.library_files:
            if candidate.as_posix().endswith(ending):
                dependency = self.library.identifier_of(candidate)
                self.library.file(dependency)
                return dependency
        raise MissingDependency(model.text(), reference)

    def relative_reference(
        self, model: ResourceIdentifier, path: Path, reference: str
    ) -> str:
        """
        :param model: The model holding the reference.
        :param path: The model's file.
        :param reference: The reference as the model writes it.
        :return: The URL path of the referenced file relative to the model's URL path.
        """
        dependency = self.resolve(model, path, reference)
        relative = posixpath.relpath(dependency.text(), posixpath.dirname(model.text()))
        return quote(relative, safe=PATH_SEPARATOR)


# %% assets


@dataclass(frozen=True)
class AssetFiles:
    """
    Answers requests for library files.
    """

    library: ResourceLibrary
    """
    The library the files belong to.
    """

    def answer(self, identifier: ResourceIdentifier) -> Response:
        """
        :param identifier: A file of the library.
        :return: The file; a URDF or glTF with its references rewritten.
        """
        path = self.library.file(identifier)
        suffix = identifier.suffix()
        if suffix == ModelSuffix.URDF:
            return Response(body=self.urdf(identifier, path), media_type=MediaType.XML)
        if suffix == MeshFormat.GLTF:
            return Response(body=self.gltf(identifier, path), media_type=MediaType.GLTF)
        return Response.of_file(path)

    def urdf(self, identifier: ResourceIdentifier, path: Path) -> bytes:
        """
        :param identifier: A URDF of the library.
        :param path: Its file.
        :return: The URDF with mesh and texture references relative to it.
        :raises DocumentTypeDeclaration: When the URDF declares a document type.
        :raises MalformedResourceDocument: When the URDF is no XML.
        """
        content = path.read_bytes()
        if any(declaration in content.upper() for declaration in DOCUMENT_DECLARATIONS):
            raise DocumentTypeDeclaration(identifier.text())
        document = UrdfParser(identifier).parse(content)
        resolver = DependencyResolver(self.library)
        for element in document.iter():
            if element.tag not in (UrdfName.MESH, UrdfName.TEXTURE):
                continue
            reference = element.get(UrdfName.FILE_NAME)
            if reference is None:
                continue
            element.set(
                UrdfName.FILE_NAME,
                resolver.relative_reference(identifier, path, reference),
            )
        return ElementTree.tostring(document, encoding="utf-8", xml_declaration=True)

    def gltf(self, identifier: ResourceIdentifier, path: Path) -> bytes:
        """
        :param identifier: A glTF file of the library.
        :param path: Its file.
        :return: The glTF with buffer and image references relative to it.
        :raises MalformedResourceDocument: When the file is no JSON object.
        """
        document = GltfParser(identifier).parse(path.read_bytes())
        resolver = DependencyResolver(self.library)
        for collection in (GltfName.BUFFERS, GltfName.IMAGES):
            for entry in document.get(collection, []):
                reference = entry.get(GltfName.URI)
                if reference is None or reference.startswith(
                    f"{ReferenceScheme.DATA}:"
                ):
                    continue
                entry[GltfName.URI] = resolver.relative_reference(
                    identifier, path, reference
                )
        return json.dumps(document).encode("utf-8")


# %% parsers


@dataclass(frozen=True)
class UrdfParser:
    """
    Parses a URDF; the one place where the XML parser's errors become the builder's.
    """

    identifier: ResourceIdentifier
    """
    The URDF being parsed.
    """

    def parse(self, content: bytes) -> ElementTree.Element:
        """
        :param content: The URDF's bytes.
        :return: Its root element.
        :raises MalformedResourceDocument: When the content is no XML.
        """
        try:
            return ElementTree.fromstring(content)
        except ElementTree.ParseError as error:
            raise MalformedResourceDocument(
                self.identifier.text(), str(error)
            ) from error


@dataclass(frozen=True)
class GltfParser:
    """
    Parses a glTF file; the one place where the JSON decoder's errors become the
    builder's.
    """

    identifier: ResourceIdentifier
    """
    The file being parsed.
    """

    def parse(self, content: bytes) -> Any:
        """
        :param content: The file's bytes.
        :return: Its JSON object.
        :raises MalformedResourceDocument: When the content is no JSON object.
        """
        try:
            document = json.loads(content.decode("utf-8"))
        except ValueError as error:
            raise MalformedResourceDocument(
                self.identifier.text(), str(error)
            ) from error
        if not isinstance(document, dict):
            raise MalformedResourceDocument(self.identifier.text(), "not a JSON object")
        return document
