"""
Object libraries: directories of ready-made object models whose ``collection.json``
files name each model's folder, its name for people, how it is grasped and its color.

A collection file declares its format version under ``formatVersion``; a file without
one is of the format written before files declared it. A reader reads every minor
version of its own major version and keeps the keys it does not know, so writing a file
back loses nothing a later minor version added.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, List, Mapping, Optional, Self

from cramera_protocol.version import UNVERSIONED, ProtocolVersion

# %% names


class LibraryVariable(StrEnum):
    """
    The environment variables naming object libraries.
    """

    LIBRARIES = "CRAMERA_OBJECT_LIBRARIES"
    """
    The libraries' directories, separated as the system separates paths.
    """


class CollectionFile(StrEnum):
    """
    The files of an object library.
    """

    COLLECTION = "collection.json"
    """
    Names the models of one directory of the library.
    """


class CollectionKey(StrEnum):
    """
    The keys of a collection file and of its entries.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The collection format's version, ``major.minor``.
    """

    OBJECTS = "objects"
    """
    The models.
    """

    SLUG = "slug"
    """
    A model's folder name without its catalogue number.
    """

    NAME = "name"
    """
    A model's name for people.
    """

    GRASP = "grasp"
    """
    How a model is taken hold of; from any side when it is left out.
    """

    COLOR = "color"
    """
    The name perception gives a model's color, such as ``red``; left out for a model of
    no single color.
    """


COLLECTION_FORMAT = ProtocolVersion(major=1, minor=0)
"""
The collection format version this package reads and writes.
"""

# %% collections


@dataclass(frozen=True)
class CollectionEntry:
    """
    One model of a collection.
    """

    slug: str
    """
    The model's folder name without its catalogue number.
    """

    name: str
    """
    The model's name for people.
    """

    grasp: Optional[str] = None
    """
    How it is grasped, or None for any side.
    """

    color: Optional[str] = None
    """
    Its color name, or None.
    """

    unknown: Dict[str, Any] = field(default_factory=dict)
    """
    The keys this reader does not know, kept as written.
    """

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> Self:
        """
        :param data: An entry of a collection file.
        :return: The entry.
        """
        known = {key.value for key in CollectionKey}
        return cls(
            slug=data[CollectionKey.SLUG],
            name=data[CollectionKey.NAME],
            grasp=data.get(CollectionKey.GRASP),
            color=data.get(CollectionKey.COLOR),
            unknown={key: value for key, value in data.items() if key not in known},
        )

    def to_json(self) -> Dict[str, Any]:
        """
        :return: The entry as a collection file holds it.
        """
        data: Dict[str, Any] = {
            CollectionKey.SLUG.value: self.slug,
            CollectionKey.NAME.value: self.name,
        }
        if self.grasp is not None:
            data[CollectionKey.GRASP.value] = self.grasp
        if self.color is not None:
            data[CollectionKey.COLOR.value] = self.color
        return {**data, **self.unknown}


@dataclass(frozen=True)
class ObjectCollection:
    """
    One collection file.
    """

    entries: List[CollectionEntry]
    """
    Its models, in the file's order.
    """

    format_version: ProtocolVersion = UNVERSIONED
    """
    The format version the file declares, or :data:`UNVERSIONED`.
    """

    unknown: Dict[str, Any] = field(default_factory=dict)
    """
    The top-level keys this reader does not know, kept as written.
    """

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> Self:
        """
        :param data: A collection file's content.
        :return: The collection.
        :raises UnsupportedProtocolVersion: When the file is of another major version.
        """
        declared = data.get(CollectionKey.FORMAT_VERSION)
        version = (
            UNVERSIONED if declared is None else ProtocolVersion.from_json(declared)
        )
        version.require_readable_by(COLLECTION_FORMAT)
        known = {CollectionKey.FORMAT_VERSION.value, CollectionKey.OBJECTS.value}
        return cls(
            entries=[
                CollectionEntry.from_json(entry)
                for entry in data.get(CollectionKey.OBJECTS, [])
            ],
            format_version=version,
            unknown={key: value for key, value in data.items() if key not in known},
        )

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A ``collection.json``.
        :return: The collection.
        :raises UnsupportedProtocolVersion: When the file is of another major version.
        """
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))

    def to_json(self) -> Dict[str, Any]:
        """
        :return: The collection as its file holds it, unknown keys included.
        """
        data: Dict[str, Any] = {}
        if self.format_version != UNVERSIONED:
            data[CollectionKey.FORMAT_VERSION.value] = self.format_version.to_json()
        data.update(self.unknown)
        data[CollectionKey.OBJECTS.value] = [entry.to_json() for entry in self.entries]
        return data


# %% catalogue


@dataclass(frozen=True)
class ObjectCatalog:
    """
    What the object libraries say about each model, by the folder name its path ends
    in.
    """

    descriptions: Dict[str, CollectionEntry] = field(default_factory=dict)
    """
    The entries by slug.
    """

    @classmethod
    def from_directories(cls, directories: List[Path]) -> Self:
        """
        :param directories: Object libraries' root directories.
        :return: The entries of every ``collection.json`` below them.
        """
        descriptions = {}
        for directory in directories:
            for path in sorted(directory.rglob(CollectionFile.COLLECTION)):
                for entry in ObjectCollection.from_file(path).entries:
                    descriptions[entry.slug] = entry
        return cls(descriptions)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> Self:
        """
        :param environment: The process environment.
        :return: The catalogue of the libraries it names; empty when it names none.
        """
        configured = environment.get(LibraryVariable.LIBRARIES, "")
        return cls.from_directories(
            [Path(entry) for entry in configured.split(os.pathsep) if entry]
        )

    def description(self, model: str) -> Optional[CollectionEntry]:
        """
        :param model: An object model's path, such as
            ``aicor/objects/cubes/red_cube/model.urdf``.
        :return: Its library's entry, or None for a model no library describes.
        """
        return self.descriptions.get(Path(model).parent.name)
