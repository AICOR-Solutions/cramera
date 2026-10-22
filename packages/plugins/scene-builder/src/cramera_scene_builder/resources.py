"""
The resource library: the files a draft can place, found in named root directories and
addressed as ``<root>/<path>``; nothing outside the roots is listed or served.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from urllib.parse import unquote

from typing_extensions import (
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Self,
    Tuple,
)

from cramera.confinement import ConfinedDirectory
from cramera_protocol.bundle.files import BundleFile, MeshFormat
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.scene_builder import (
    PointCloudFormat,
    PointCloudMetadata,
    ResourceCategory,
    ResourceDescription,
    ResourceKind,
    ResourceNotice,
)
from cramera_scene_builder.exceptions import (
    InvalidResourceIdentifier,
    InvalidRootName,
    NotAModel,
    NotAPointCloud,
    OutsideLibrary,
    UnknownResourceRoot,
    UnservedResourceFile,
)

# %% file types


class ModelSuffix(StrEnum):
    """
    The suffixes of model files besides the mesh formats.
    """

    URDF = ".urdf"
    """
    A URDF model.
    """


class DependencySuffix(StrEnum):
    """
    The suffixes of files a model loads besides other models: materials, buffers and
    textures.
    """

    MATERIAL_LIBRARY = MeshFormat.MATERIAL_LIBRARY.value
    """
    An OBJ material library.
    """

    BUFFER = ".bin"
    """
    A glTF buffer.
    """

    PNG = ".png"
    """
    A PNG texture.
    """

    JPG = ".jpg"
    """
    A JPEG texture.
    """

    JPEG = ".jpeg"
    """
    A JPEG texture with the long suffix.
    """

    WEBP = ".webp"
    """
    A WebP texture.
    """

    TGA = ".tga"
    """
    A Targa texture.
    """

    BMP = ".bmp"
    """
    A bitmap texture.
    """

    GIF = ".gif"
    """
    A GIF texture.
    """

    SVG = ".svg"
    """
    An SVG texture.
    """

    DDS = ".dds"
    """
    A DirectDraw surface texture.
    """

    KTX2 = ".ktx2"
    """
    A Khronos texture.
    """


class NoticeFile(StrEnum):
    """
    The names of licence and attribution documents kept with resources.
    """

    NOTICE = "NOTICE.md"
    """
    An attribution notice.
    """

    LICENSE_TEXT = "LICENSE.txt"
    """
    A licence as plain text.
    """

    LICENSE = "LICENSE"
    """
    A licence without suffix.
    """

    LICENSE_MARKDOWN = "LICENSE.md"
    """
    A licence as Markdown.
    """

    COPYING = "COPYING"
    """
    A licence as GNU projects name it.
    """

    RIGHTS = "rights.json"
    """
    A machine-readable statement of rights.
    """


MESH_SUFFIXES = frozenset(
    suffix.value for suffix in MeshFormat if suffix is not MeshFormat.MATERIAL_LIBRARY
)
"""
The suffixes of mesh files.
"""

POINT_CLOUD_FORMATS: Mapping[str, PointCloudFormat] = MappingProxyType(
    {
        point_cloud_format.suffix(): point_cloud_format
        for point_cloud_format in PointCloudFormat
    }
)
"""
The point cloud format of each point cloud file suffix.
"""

POINT_CLOUD_SUFFIXES = frozenset(POINT_CLOUD_FORMATS)
"""
The suffixes of point cloud files.
"""

PLACEABLE_SUFFIXES = MESH_SUFFIXES | POINT_CLOUD_SUFFIXES | {ModelSuffix.URDF.value}
"""
The suffixes of files a draft can place.
"""

SERVED_SUFFIXES = PLACEABLE_SUFFIXES | {suffix.value for suffix in DependencySuffix}
"""
The suffixes of files the library serves.
"""

NOTICE_NAMES = tuple(sorted(notice.value for notice in NoticeFile))
"""
The names of notices, in the order they are listed.
"""


class CategoryDirectory(StrEnum):
    """
    Directory names that tell what the models below them show.
    """

    WORLDS = "worlds"
    """
    Rooms and buildings.
    """

    ROBOTS = "robots"
    """
    Robot models.
    """

    ROBOT_DESCRIPTIONS = "robot_descriptions"
    """
    Robot description packages.
    """


DIRECTORY_CATEGORIES: Tuple[Tuple[CategoryDirectory, ResourceCategory], ...] = (
    (CategoryDirectory.WORLDS, ResourceCategory.ENVIRONMENT),
    (CategoryDirectory.ROBOTS, ResourceCategory.ROBOT),
    (CategoryDirectory.ROBOT_DESCRIPTIONS, ResourceCategory.ROBOT),
)
"""
The category of models below each telling directory; later entries win.
"""


class GenericModelName(StrEnum):
    """
    File names that say nothing about the model, which is then named after its
    directory.
    """

    MODEL = "model"
    """
    A model.
    """

    ENVIRONMENT = "environment"
    """
    An environment.
    """

    ROBOT = "robot"
    """
    A robot.
    """


class MetadataSuffix(StrEnum):
    """
    The suffix of the description stored next to an uploaded point cloud.
    """

    POINT_CLOUD = ".metadata.json"
    """
    The point cloud's :class:`PointCloudMetadata`.
    """


HIDDEN_PREFIX = "."
"""
Starts the names of hidden files and directories, which the library never lists.
"""

PATH_SEPARATOR = "/"
"""
Separates the root and the path segments of a resource identifier.
"""

# %% identifiers


@dataclass(frozen=True)
class ResourceIdentifier:
    """
    A file of the library, ``<root>/<path>``.
    """

    root: str
    """
    The name of the root directory.
    """

    path: str
    """
    The file's path below the root, with ``/`` separators.
    """

    @classmethod
    def parse(cls, text: str) -> Self:
        """
        :param text: An identifier as written.
        :return: The identifier.
        :raises InvalidResourceIdentifier: When the text holds empty, hidden, ``.`` or
            ``..`` segments, backslashes, NUL characters or escapes.
        """
        segments = text.split(PATH_SEPARATOR)
        if (
            "\\" in text
            or "\x00" in text
            or unquote(text) != text
            or len(segments) < 2
            or any(
                not segment or segment.startswith(HIDDEN_PREFIX) for segment in segments
            )
        ):
            raise InvalidResourceIdentifier(text)
        return cls(root=segments[0], path=PATH_SEPARATOR.join(segments[1:]))

    def text(self) -> str:
        """
        :return: The identifier as written.
        """
        return f"{self.root}{PATH_SEPARATOR}{self.path}"

    def suffix(self) -> str:
        """
        :return: The file's suffix, in lowercase.
        """
        return PurePosixPath(self.path).suffix.lower()

    def file_name(self) -> str:
        """
        :return: The file's name.
        """
        return PurePosixPath(self.path).name


# %% library


@dataclass(frozen=True)
class ResourceLibrary:
    """
    Named root directories of resources.
    """

    roots: Mapping[str, Path]
    """
    The directory of each root, by root name.
    """

    @classmethod
    def of(cls, roots: Mapping[str, Path]) -> Self:
        """
        :param roots: The directory of each root, by root name.
        :return: The library.
        :raises InvalidRootName: When a root name is not a plain name.
        """
        for name, directory in roots.items():
            if not SceneName.is_valid(name):
                raise InvalidRootName(directory)
        return cls(roots=dict(roots))

    def directory(self, root: str) -> Path:
        """
        :param root: A root name.
        :return: The root's directory.
        :raises UnknownResourceRoot: When the library has no such root.
        """
        if root not in self.roots:
            raise UnknownResourceRoot(root)
        return self.roots[root]

    def file(self, identifier: ResourceIdentifier) -> Path:
        """
        :param identifier: A file of the library.
        :return: The file, confined to its root.
        :raises UnknownResourceRoot: When the library has no such root.
        :raises PathOutsideDirectory: When the path leads out of its root.
        :raises FileNotInDirectory: When the root holds no such file.
        :raises UnservedResourceFile: When the file is neither a model, a model's file
            nor a notice.
        """
        path = ConfinedDirectory(self.directory(identifier.root)).file(identifier.path)
        if identifier.suffix() not in SERVED_SUFFIXES and (
            identifier.file_name() not in NOTICE_NAMES
        ):
            raise UnservedResourceFile(identifier.text())
        return path

    def placeable_file(self, identifier: ResourceIdentifier) -> Path:
        """
        :param identifier: A file of the library.
        :return: The file, which a draft can place.
        :raises NotAModel: When the file is a dependency or a notice.
        """
        path = self.file(identifier)
        if identifier.suffix() not in PLACEABLE_SUFFIXES:
            raise NotAModel(identifier.text())
        return path

    def identifier_of(self, path: Path) -> ResourceIdentifier:
        """
        :param path: A file.
        :return: Its identifier in the first root that holds it.
        :raises OutsideLibrary: When no root holds the file.
        """
        resolved = path.resolve()
        for name, directory in self.roots.items():
            root = directory.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return ResourceIdentifier(name, resolved.relative_to(root).as_posix())
        raise OutsideLibrary(path)

    def files(self) -> Iterator[Tuple[ResourceIdentifier, Path]]:
        """
        :return: Every visible file of every root, without following directory links
            and without files whose links lead out of their root.
        """
        for name, directory in self.roots.items():
            if not directory.is_dir():
                continue
            root = directory.resolve()
            for parent, directories, names in os.walk(directory, followlinks=False):
                directories[:] = sorted(
                    entry
                    for entry in directories
                    if not entry.startswith(HIDDEN_PREFIX)
                )
                for entry in sorted(names):
                    candidate = Path(parent) / entry
                    if (
                        entry.startswith(HIDDEN_PREFIX)
                        or not candidate.resolve().is_relative_to(root)
                        or not candidate.is_file()
                    ):
                        continue
                    relative = candidate.relative_to(directory).as_posix()
                    yield ResourceIdentifier(name, relative), candidate

    def notices(self, identifier: ResourceIdentifier) -> List[ResourceNotice]:
        """
        :param identifier: A file of the library.
        :return: The notices in the file's directory and every directory above it up
            to its root, nearest first.
        """
        root = self.directory(identifier.root).resolve()
        directory = self.file(identifier).parent
        notices = []
        while directory.is_relative_to(root):
            for name in NOTICE_NAMES:
                candidate = directory / name
                if candidate.is_file() and candidate.resolve().is_relative_to(root):
                    notices.append(
                        ResourceNotice(
                            name=name, asset=self.identifier_of(candidate).text()
                        )
                    )
            if directory == root:
                break
            directory = directory.parent
        return notices

    def resources(self) -> List[ResourceDescription]:
        """
        :return: Every file a draft can place, with what it shows.
        """
        files = list(self.files())
        roles = BundleRoles.of(path for _, path in files)
        return [
            self.describe(identifier, path, roles)
            for identifier, path in files
            if identifier.suffix() in PLACEABLE_SUFFIXES
        ]

    def resource(self, identifier: ResourceIdentifier) -> ResourceDescription:
        """
        :param identifier: A file a draft can place, outside any scene bundle.
        :return: The file as the library lists it.
        :raises NotAModel: When the file cannot be placed.
        """
        path = self.placeable_file(identifier)
        return self.describe(identifier, path, BundleRoles(categories={}))

    def point_cloud_format(self, identifier: ResourceIdentifier) -> PointCloudFormat:
        """
        :param identifier: A file of the library.
        :return: The file's point cloud format.
        :raises NotAPointCloud: When the file is no point cloud.
        """
        if identifier.suffix() not in POINT_CLOUD_FORMATS:
            raise NotAPointCloud(identifier.text())
        return POINT_CLOUD_FORMATS[identifier.suffix()]

    def describe(
        self, identifier: ResourceIdentifier, path: Path, roles: BundleRoles
    ) -> ResourceDescription:
        """
        :param identifier: A file a draft can place.
        :param path: The file.
        :param roles: What the models of the library's bundles show.
        :return: The file as the library lists it.
        """
        stem = PurePosixPath(identifier.path).stem
        generic = stem in {name.value for name in GenericModelName}
        kind = self.kind_of(identifier)
        return ResourceDescription(
            identifier=identifier.text(),
            name=path.parent.name if generic else stem,
            kind=kind,
            category=roles.category_of(identifier, path),
            notices=self.notices(identifier),
            point_cloud=(
                PointCloudMetadataFile(path).read()
                if kind is ResourceKind.POINT_CLOUD
                else None
            ),
        )

    @staticmethod
    def kind_of(identifier: ResourceIdentifier) -> ResourceKind:
        """
        :param identifier: A file a draft can place.
        :return: How the browser loads it.
        """
        if identifier.suffix() == ModelSuffix.URDF:
            return ResourceKind.URDF
        if identifier.suffix() in POINT_CLOUD_SUFFIXES:
            return ResourceKind.POINT_CLOUD
        return ResourceKind.MESH


# %% categories


@dataclass(frozen=True)
class BundleRoles:
    """
    What the models of scene bundles show, as their ``scene.json`` says.
    """

    categories: Dict[Path, ResourceCategory]
    """
    The category of each model a bundle names, by its resolved file.
    """

    @classmethod
    def of(cls, paths: Iterable[Path]) -> Self:
        """
        :param paths: Files of the library; the bundle descriptions among them are read.
        :return: The categories their models have.
        """
        categories: Dict[Path, ResourceCategory] = {}
        for path in paths:
            if path.name != BundleFile.SCENE:
                continue
            description = BundleDescriptionReader(path).read()
            if description is None:
                continue
            for model in description.models:
                categories[(path.parent / model.urdf).resolve()] = (
                    ResourceCategory.ROBOT
                    if model.robot
                    else ResourceCategory.ENVIRONMENT
                )
        return cls(categories=categories)

    def category_of(
        self, identifier: ResourceIdentifier, path: Path
    ) -> ResourceCategory:
        """
        :param identifier: A file a draft can place.
        :param path: The file.
        :return: What the file shows: a point cloud, what its bundle says, or what its
            directories tell; an object otherwise.
        """
        if identifier.suffix() in POINT_CLOUD_SUFFIXES:
            return ResourceCategory.POINT_CLOUD
        category = self.categories.get(path.resolve(), ResourceCategory.OBJECT)
        directories = PurePosixPath(identifier.path).parts[:-1]
        for directory, telling in DIRECTORY_CATEGORIES:
            if directory in directories:
                category = telling
        return category


@dataclass(frozen=True)
class BundleDescriptionReader:
    """
    Reads a bundle's ``scene.json`` for the library.
    """

    path: Path
    """
    The ``scene.json`` file.
    """

    def read(self) -> Optional[SceneDescription]:
        """
        A broken bundle must not hide the library's other resources, so this is the one
        place where its reading errors become absence.

        :return: The description, or None when the file cannot be read.
        """
        try:
            return SceneDescription.from_json(
                json.loads(self.path.read_text(encoding="utf-8"))
            )
        except (ValueError, ProtocolError):
            return None


@dataclass(frozen=True)
class PointCloudMetadataFile:
    """
    The description stored next to an uploaded point cloud.
    """

    point_cloud: Path
    """
    The point cloud file.
    """

    def path(self) -> Path:
        """
        :return: Where the description is stored.
        """
        return self.point_cloud.with_suffix(MetadataSuffix.POINT_CLOUD)

    def read(self) -> Optional[PointCloudMetadata]:
        """
        :return: The description, or None for a file without one.
        """
        path = self.path()
        if path.is_symlink() or not path.is_file():
            return None
        return PointCloudMetadata.from_json(
            json.loads(path.read_text(encoding="utf-8"))
        )
