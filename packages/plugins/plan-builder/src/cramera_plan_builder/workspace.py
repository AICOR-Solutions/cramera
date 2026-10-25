"""
What the CRAM workspace offers a plan: its robot annotations, object meshes, surface
annotations and native actions, as cramera-bridge reads them and hands them over in the
protocol's documents.

Whether the workspace is importable is decided by asking the import system before
anything imports it, so an absent workspace is a value the plugin reads rather than an
import error it has to catch; the module reading the workspace is only imported once
every module is found.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import ModuleSpec
from pathlib import Path

from typing_extensions import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from cramera.confinement import ConfinedDirectory
from cramera.exceptions import FileNotInDirectory
from cramera_plan_builder.exceptions import CramUnavailable
from cramera_protocol.bundle.files import MeshFormat
from cramera_protocol.plan_builder import ActionCatalog, ObjectModel, RobotModel

if TYPE_CHECKING:
    from cramera_bridge.plans.workspace import PlanWorkspace

TEXTURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
"""
The suffixes of the textures a mesh may reference beside it.
"""

DESCRIPTION_SUFFIX = ".urdf"
"""
The suffix of an object library model's description, which names its meshes.
"""

LIBRARY_SEPARATOR = "/"
"""
Separates an object library's name from a file's path in the library.
"""

# %% modules


class CramModule(StrEnum):
    """
    The top-level modules a plan's catalog and its demo import.
    """

    SEMANTIC_DIGITAL_TWIN = "semantic_digital_twin"
    """
    The robot annotations, surfaces and enumerations.
    """

    CORAPLEX = "coraplex"
    """
    The actions and the object meshes.
    """

    KRROOD = "krrood"
    """
    The class introspection robot parts are read with.
    """

    CRAMERA_BRIDGE = "cramera_bridge"
    """
    The robot task demo a generated demo runs as.
    """


ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


@dataclass(frozen=True)
class CramModules:
    """
    Finds out which of the workspace's modules are installed.
    """

    modules: Tuple[CramModule, ...] = tuple(CramModule)
    """
    The modules that must be installed.
    """

    finder: ModuleFinder = field(default=importlib.util.find_spec)
    """
    Finds a module without importing it.
    """

    def missing(self) -> List[str]:
        """
        :return: The modules that cannot be found, in the order of :attr:`modules`; a
            directory that only shares a module's name does not count as the module.
        """
        return [
            module.value for module in self.modules if not self.is_installed(module)
        ]

    def is_installed(self, module: CramModule) -> bool:
        """
        :param module: A top-level module.
        :return: Whether a module with code of its own is found under that name.
        """
        specification = self.finder(module)
        return specification is not None and specification.origin is not None


# %% workspace


class CramWorkspace(ABC):
    """
    What the CRAM workspace offers a plan.
    """

    @abstractmethod
    def robots(self) -> List[RobotModel]:
        """
        :return: The robot annotations with what their parts allow, sorted by name.
        """

    @abstractmethod
    def objects(self) -> List[ObjectModel]:
        """
        :return: The object meshes, sorted by identifier.
        """

    @abstractmethod
    def object_directory(self) -> Path:
        """
        :return: The directory holding the object meshes.
        :raises CramUnavailable: Without the workspace.
        """

    @abstractmethod
    def surface_types(self) -> List[str]:
        """
        :return: The identifiers of the annotations objects can be put on or in, sorted.
        """

    def saved_surface_types(self) -> Dict[str, str]:
        """
        :return: The identifier of each surface type by the name plans saved it under
            before the protocol named it; none by default.
        """
        return {}

    @abstractmethod
    def action_catalog(self) -> ActionCatalog:
        """
        :return: The schemas of the native actions and the action modules that failed
            to import.
        """

    def missing(self) -> List[str]:
        """
        :return: The modules that cannot be found; none for an installed workspace.
        """
        return []

    def object_roots(self) -> Dict[str, Path]:
        """
        :return: The root of each object library by the name its files' paths start
            with; none without libraries.
        """
        return {}

    def object_file(self, requested: str) -> Path:
        """
        :param requested: A mesh of the object directory, or a material library or
            texture beside one; or ``<library>/<path>`` of a library model's
            description, mesh or texture.
        :return: The file.
        :raises CramUnavailable: Without the workspace.
        :raises PathOutsideDirectory: For a path leaving the directory or the library.
        :raises FileNotInDirectory: For a missing file or one that is no mesh, material
            library, texture or description.
        """
        library, _, relative = requested.partition(LIBRARY_SEPARATOR)
        roots = self.object_roots()
        if relative and library in roots:
            directory, requested = roots[library], relative
        else:
            directory = self.object_directory()
        file = ConfinedDirectory(directory).file(requested)
        if file.suffix.lower() not in self.served_suffixes():
            raise FileNotInDirectory(directory, requested)
        return file

    @staticmethod
    def served_suffixes() -> frozenset[str]:
        """
        :return: The suffixes of the object directory's files that are served.
        """
        return (
            frozenset(member.value for member in MeshFormat)
            | TEXTURE_SUFFIXES
            | {DESCRIPTION_SUFFIX}
        )


@dataclass(frozen=True)
class MissingWorkspace(CramWorkspace):
    """
    The workspace of an interpreter that cannot import CRAM: it offers nothing and names
    what is missing.
    """

    missing_modules: List[str]
    """
    The modules that cannot be found.
    """

    def robots(self) -> List[RobotModel]:
        return []

    def objects(self) -> List[ObjectModel]:
        return []

    def object_directory(self) -> Path:
        raise CramUnavailable(self.missing_modules)

    def surface_types(self) -> List[str]:
        return []

    def action_catalog(self) -> ActionCatalog:
        return ActionCatalog()

    def missing(self) -> List[str]:
        return list(self.missing_modules)


@dataclass(frozen=True)
class InstalledWorkspace(CramWorkspace):
    """
    The workspace of an interpreter that imports CRAM, as cramera-bridge reads it.
    """

    plans: PlanWorkspace
    """
    The workspace as cramera-bridge reads it.
    """

    def robots(self) -> List[RobotModel]:
        return self.plans.robots()

    def objects(self) -> List[ObjectModel]:
        return self.plans.objects()

    def object_directory(self) -> Path:
        return self.plans.object_directory()

    def object_roots(self) -> Dict[str, Path]:
        return self.plans.object_roots()

    def surface_types(self) -> List[str]:
        return self.plans.surface_types()

    def saved_surface_types(self) -> Dict[str, str]:
        return self.plans.saved_surface_types()

    def action_catalog(self) -> ActionCatalog:
        return self.plans.action_catalog()


# %% choice


class WorkspaceModule(StrEnum):
    """
    The module of cramera-bridge reading the installed workspace; it imports CRAM, so it
    is only imported once every module is found.
    """

    INSTALLED = "cramera_bridge.plans.workspace"
    """
    :class:`cramera_bridge.plans.workspace.PlanWorkspace`.
    """


@dataclass
class WorkspaceLoader:
    """
    Reads the workspace once, when it is first asked for: importing CRAM takes seconds,
    which the viewer's start does not wait for.
    """

    modules: CramModules = field(default_factory=CramModules)
    """
    Finds out which modules are installed.
    """

    loaded: Optional[CramWorkspace] = field(default=None, init=False)
    """
    The workspace once it was read.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Lets one request read the workspace while others wait for it.
    """

    def workspace(self) -> CramWorkspace:
        """
        :return: The installed workspace, or a :class:`MissingWorkspace` naming the
            modules that cannot be found.
        """
        with self.lock:
            if self.loaded is None:
                self.loaded = self.read()
            return self.loaded

    def read(self) -> CramWorkspace:
        """
        :return: The workspace the installed modules allow.
        """
        missing = self.modules.missing()
        if missing:
            return MissingWorkspace(missing)
        module = importlib.import_module(WorkspaceModule.INSTALLED)
        return InstalledWorkspace(module.PlanWorkspace())
