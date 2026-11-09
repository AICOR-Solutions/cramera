"""
Object libraries: directories of ready-made object models, each a folder with a URDF and
its meshes, that the plan builder offers besides the meshes beside coraplex, such as the
``private_meshes`` repository checked out under this repository's ``resources``.

A library model is named ``<library>/<path of its URDF in the library>``, so the plan,
the builder's file route and the generated demo all resolve it the same way; a mesh
beside coraplex keeps its bare file name.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Mapping, Optional

from cramera_protocol.plan_builder import ObjectModel

LIBRARY_VARIABLE = "CRAMERA_OBJECT_LIBRARIES"
"""
The environment variable naming further libraries, separated like ``PATH``.
"""

REPOSITORY_RESOURCES = Path(__file__).resolve().parents[5] / "resources"
"""
The ``resources`` directory of this repository's checkout, whose libraries are offered
without being named; it does not exist in an installation from a package index.
"""

SEPARATOR = "/"
"""
Separates a library model's library from its path in the library.
"""

ID_PREFIX = re.compile(r"^\d+-")
"""
The catalogue number a model folder's name may start with, as in ``139-folding_crate``.
"""


class LibraryFile(StrEnum):
    """
    The names a library is read by.
    """

    OBJECTS = "objects"
    """
    The directory holding the models, below the library's root.
    """

    MODEL = "model.urdf"
    """
    A model's description, in its own folder.
    """

    COLLECTION = "collection.json"
    """
    The names of a collection's models, by the slug of their folders.
    """


class CollectionKey(StrEnum):
    """
    The keys of a collection file.
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
    How a model is taken hold of, an :class:`ObjectGrasp` value; from any side when it
    is left out.
    """


class ObjectGrasp(StrEnum):
    """
    How the robot takes hold of a library model.
    """

    ANY_SIDE = "any_side"
    """
    Around the model's origin, from any side, as nothing more is known of its shape.
    """

    FROM_ABOVE = "from_above"
    """
    From straight above, around the middle of its collision geometry, as a small block
    standing on a table is taken.
    """


# %% library


@dataclass(frozen=True)
class ObjectLibrary:
    """
    One directory of object models.
    """

    directory: Path
    """
    The library's root, holding its ``objects`` directory.
    """

    @property
    def name(self) -> str:
        """
        :return: The name a model identifier starts with.
        """
        return self.directory.name

    def is_library(self) -> bool:
        """
        :return: Whether the directory holds models.
        """
        return (self.directory / LibraryFile.OBJECTS).is_dir()

    def models(self) -> List[ObjectModel]:
        """
        :return: Every model of the library, sorted by identifier.
        """
        descriptions = sorted(
            (self.directory / LibraryFile.OBJECTS).rglob(LibraryFile.MODEL)
        )
        names = self.names()
        return [
            ObjectModel(
                identifier=SEPARATOR.join(
                    (self.name, description.relative_to(self.directory).as_posix())
                ),
                name=names.get(self.slug(description), self.readable(description)),
            )
            for description in descriptions
        ]

    def names(self) -> Dict[str, str]:
        """
        :return: The names the library's collection files give, by slug.
        """
        return {
            entry[CollectionKey.SLUG]: entry[CollectionKey.NAME]
            for entry in self.collection_entries()
            if CollectionKey.NAME in entry
        }

    def grasps(self) -> Dict[str, ObjectGrasp]:
        """
        :return: How the library's collection files say their models are taken hold
            of, by slug, for the models whose entry says so.
        """
        return {
            entry[CollectionKey.SLUG]: ObjectGrasp(entry[CollectionKey.GRASP])
            for entry in self.collection_entries()
            if CollectionKey.GRASP in entry
        }

    def collection_entries(self) -> List[Dict[str, str]]:
        """
        :return: The model entries of every collection file of the library.
        """
        entries: List[Dict[str, str]] = []
        for collection in sorted(
            (self.directory / LibraryFile.OBJECTS).rglob(LibraryFile.COLLECTION)
        ):
            document = json.loads(collection.read_text(encoding="utf-8"))
            entries.extend(document.get(CollectionKey.OBJECTS, []))
        return entries

    @staticmethod
    def slug(description: Path) -> str:
        """
        :param description: A model's URDF.
        :return: Its folder's name without the catalogue number.
        """
        return ID_PREFIX.sub("", description.parent.name)

    @classmethod
    def readable(cls, description: Path) -> str:
        """
        :param description: A model's URDF.
        :return: Its folder's slug as words, for a model no collection names.
        """
        return cls.slug(description).replace("_", " ").capitalize()


# %% libraries


@dataclass(frozen=True)
class ObjectLibraries:
    """
    Every library the builder offers.
    """

    libraries: List[ObjectLibrary] = field(default_factory=list)
    """
    The libraries, in the order their models are listed.
    """

    @classmethod
    def of_environment(
        cls,
        environment: Optional[Mapping[str, str]] = None,
        resources: Path = REPOSITORY_RESOURCES,
    ) -> ObjectLibraries:
        """
        :param environment: The environment variables, the process's by default.
        :param resources: A directory whose children may be libraries.
        :return: The libraries of :data:`LIBRARY_VARIABLE`, then those in ``resources``;
            a directory that holds no models is left out, and a name is offered once.
        """
        environment = os.environ if environment is None else environment
        named = [
            Path(entry)
            for entry in environment.get(LIBRARY_VARIABLE, "").split(os.pathsep)
            if entry
        ]
        found = sorted(resources.iterdir()) if resources.is_dir() else []
        libraries: Dict[str, ObjectLibrary] = {}
        for directory in named + found:
            library = ObjectLibrary(directory.resolve())
            if library.is_library() and library.name not in libraries:
                libraries[library.name] = library
        return cls(list(libraries.values()))

    def models(self) -> List[ObjectModel]:
        """
        :return: The models of every library, library by library.
        """
        return [model for library in self.libraries for model in library.models()]

    def roots(self) -> Dict[str, Path]:
        """
        :return: Each library's root by its name.
        """
        return {library.name: library.directory for library in self.libraries}

    def grasp_of(self, identifier: str) -> ObjectGrasp:
        """
        :param identifier: An object model's identifier.
        :return: How the model is taken hold of: as its library's collection says, else
            from any side.
        """
        library, _, relative = identifier.partition(SEPARATOR)
        for candidate in self.libraries:
            if relative and candidate.name == library:
                return candidate.grasps().get(
                    ObjectLibrary.slug(Path(relative)), ObjectGrasp.ANY_SIDE
                )
        return ObjectGrasp.ANY_SIDE

    def path_of(self, identifier: str, directory: Path) -> Path:
        """
        :param identifier: An object model's identifier.
        :param directory: The directory of the models no library holds.
        :return: The model's file.
        """
        library, _, relative = identifier.partition(SEPARATOR)
        roots = self.roots()
        if relative and library in roots:
            return roots[library] / relative
        return directory / identifier
