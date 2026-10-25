"""
The installed CRAM workspace as the plan builder's catalog reads it: robot annotations
and the choices their parts allow, object meshes, surface annotations and native
actions, all read from the workspace's own classes and files and handed over as the
protocol's documents.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from typing_extensions import Dict, List, Set, Type, get_args

import coraplex
import semantic_digital_twin.robots

# defines the concrete surface annotations the catalog lists
import semantic_digital_twin.semantic_annotations.semantic_annotations  # noqa: F401
from cramera_bridge.plans.actions import ActionDiscovery, DiscoveredActions
from cramera_bridge.plans.arms import Arms
from cramera_bridge.plans.objects import ObjectLibraries
from cramera_bridge.exceptions import UnknownWorkspaceClass
from cramera_bridge.names import ROBOT_NAMES
from cramera_protocol.bundle.files import MeshFormat
from cramera_protocol.plan_builder import ActionCatalog, ObjectModel, RobotModel
from krrood.class_diagrams.attribute_introspector import DataclassOnlyIntrospector
from krrood.utils import recursive_subclasses
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.robots.robot_part_mixins import HasLeftRightArm
from semantic_digital_twin.robots.robot_parts import (
    AbstractRobot,
    AbstractRobotPart,
    Arm,
    Torso,
)
from semantic_digital_twin.semantic_annotations import mixins
from semantic_digital_twin.semantic_annotations.mixins import HasSupportingSurface

OBJECT_DIRECTORY = (
    Path(coraplex.__file__).resolve().parents[2] / "resources" / "objects"
)
"""
The object meshes coraplex's own demos and tests place, beside its sources.
"""

# %% classes by name


@dataclass(frozen=True)
class WorkspaceClasses:
    """
    Annotation classes of the workspace, found by the class names a plan uses.
    """

    classes: List[type]
    """
    The classes.
    """

    def named(self, name: str) -> type:
        """
        :param name: A class name.
        :return: The class of that name.
        :raises UnknownWorkspaceClass: When none has the name.
        """
        for candidate in self.classes:
            if candidate.__name__ == name:
                return candidate
        raise UnknownWorkspaceClass(
            name, [candidate.__name__ for candidate in self.classes]
        )


# %% robots


@dataclass(frozen=True)
class RobotAnnotation:
    """
    One robot annotation class and the part classes it declares, read from its fields
    without loading the robot's model.
    """

    annotation: Type[AbstractRobot]
    """
    The robot's annotation class.
    """

    def part_types(self) -> Set[type]:
        """
        :return: The robot's class and every robot part class its fields declare,
            through generic arguments and nested parts.
        """
        pending: List[object] = [self.annotation]
        found: Set[type] = set()
        introspector = DataclassOnlyIntrospector()
        while pending:
            candidate = pending.pop()
            arguments = get_args(candidate)
            if arguments:
                pending.extend(arguments)
                continue
            if (
                not isinstance(candidate, type)
                or not issubclass(candidate, (AbstractRobot, AbstractRobotPart))
                or candidate in found
            ):
                continue
            found.add(candidate)
            pending.extend(
                attribute.field.type for attribute in introspector.discover(candidate)
            )
        return found

    def arms(self) -> List[str]:
        """
        :return: The native arm choices: every choice for a robot that names a left and
            a right arm, else the choice coraplex resolves to the robot's only arm.
        """
        parts = self.part_types()
        if any(issubclass(part, HasLeftRightArm) for part in parts):
            return [arm.name for arm in Arms]
        if any(issubclass(part, Arm) for part in parts):
            return [Arms.BOTH.name]
        return []

    def torso_states(self) -> List[str]:
        """
        :return: The native torso states for a robot with a torso, else none.
        """
        if any(issubclass(part, Torso) for part in self.part_types()):
            return [state.name for state in TorsoState]
        return []

    def choices(self) -> Dict[str, List[str]]:
        """
        :return: The members of the enumerations whose choices depend on the robot's
            parts, by the enumeration's class name.
        """
        return {Arms.__name__: self.arms(), TorsoState.__name__: self.torso_states()}

    def has_model_description(self) -> bool:
        """
        :return: Whether the annotation names a file describing the robot's model.
        """
        # an annotation without a description signals it with NotImplementedError,
        # which is the boundary to the workspace's classes, not a control flow of ours
        try:
            return bool(self.annotation.get_ros_file_path())
        except NotImplementedError:
            return False

    def model(self) -> RobotModel:
        """
        :return: The robot as the catalog lists it.
        """
        return RobotModel(
            name=ROBOT_NAMES.identifier_of(self.annotation),
            label=self.annotation.__name__,
            module=self.annotation.__module__,
            saved_as=ROBOT_NAMES.saved_as(self.annotation),
            choices=self.choices(),
        )


@dataclass(frozen=True)
class RobotAnnotations:
    """
    The concrete robot annotations of the workspace's robot package.
    """

    package: ModuleType = semantic_digital_twin.robots
    """
    The package whose modules define the robot annotations.
    """

    def annotations(self) -> List[Type[AbstractRobot]]:
        """
        :return: Every concrete robot annotation with a model description, sorted by
            name, after importing every module of :attr:`package`.
        """
        for module in pkgutil.iter_modules(self.package.__path__):
            importlib.import_module(f"{self.package.__name__}.{module.name}")
        concrete = [
            annotation
            for annotation in recursive_subclasses(AbstractRobot)
            if not inspect.isabstract(annotation)
            and RobotAnnotation(annotation).has_model_description()
        ]
        return sorted(set(concrete), key=lambda annotation: annotation.__name__)

    def named(self, name: str) -> Type[AbstractRobot]:
        """
        :param name: A robot's identifier, or a name a plan saved it under before.
        :return: The annotation class.
        :raises UnknownWorkspaceClass: When no annotation has the name.
        """
        annotations = self.annotations()
        for annotation in annotations:
            if ROBOT_NAMES.matches(annotation, name):
                return annotation
        raise UnknownWorkspaceClass(
            name, [ROBOT_NAMES.identifier_of(annotation) for annotation in annotations]
        )


# %% surfaces


@dataclass(frozen=True)
class SurfaceAnnotations:
    """
    The concrete annotations of the workspace that objects can be put on or in.
    """

    def annotations(self) -> List[Type[HasSupportingSurface]]:
        """
        :return: Every concrete annotation with a supporting surface, without the
            mixins, sorted by name.
        """
        concrete = {
            annotation
            for annotation in recursive_subclasses(HasSupportingSurface)
            if not inspect.isabstract(annotation)
            and annotation.__module__ != mixins.__name__
        }
        return sorted(concrete, key=lambda annotation: annotation.__name__)

    def named(self, name: str) -> Type[HasSupportingSurface]:
        """
        :param name: The class name of a surface annotation.
        :return: The annotation class.
        :raises UnknownWorkspaceClass: When no annotation has the name.
        """
        return WorkspaceClasses(self.annotations()).named(name)


# %% workspace


@dataclass(frozen=True)
class PlanWorkspace:
    """
    What the CRAM workspace this interpreter imports offers a plan, as the protocol's
    documents the plan builder's catalog lists.
    """

    robot_annotations: RobotAnnotations = field(default_factory=RobotAnnotations)
    """
    The robot annotations.
    """

    directory: Path = OBJECT_DIRECTORY
    """
    The directory of the object meshes.
    """

    libraries: ObjectLibraries = field(default_factory=ObjectLibraries.of_environment)
    """
    The object libraries offered besides the meshes, read once when the workspace is
    read.
    """

    discovered_actions: DiscoveredActions = field(
        default_factory=lambda: ActionDiscovery().discover()
    )
    """
    The native actions, discovered once when the workspace is read: discovery imports
    every action module.
    """

    def robots(self) -> List[RobotModel]:
        """
        :return: The robot annotations with what their parts allow, sorted by name.
        """
        return [
            RobotAnnotation(annotation).model()
            for annotation in self.robot_annotations.annotations()
        ]

    def objects(self) -> List[ObjectModel]:
        """
        :return: The object meshes, sorted by identifier, then the models of each object
            library.
        """
        mesh_suffixes = {
            member.value
            for member in MeshFormat
            if member is not MeshFormat.MATERIAL_LIBRARY
        }
        meshes = [
            ObjectModel(identifier=path.name, name=path.stem)
            for path in sorted(self.directory.iterdir())
            if path.is_file() and path.suffix.lower() in mesh_suffixes
        ]
        return meshes + self.libraries.models()

    def object_directory(self) -> Path:
        """
        :return: The directory holding the object meshes.
        """
        return self.directory

    def object_roots(self) -> Dict[str, Path]:
        """
        :return: The root of each object library by the name its models' identifiers
            start with.
        """
        return self.libraries.roots()

    def surface_types(self) -> List[str]:
        """
        :return: The class names of the annotations objects can be put on or in, sorted.
        """
        return [
            annotation.__name__ for annotation in SurfaceAnnotations().annotations()
        ]

    def action_catalog(self) -> ActionCatalog:
        """
        :return: The schemas of the native actions and the action modules that failed
            to import.
        """
        return self.discovered_actions.catalog()
