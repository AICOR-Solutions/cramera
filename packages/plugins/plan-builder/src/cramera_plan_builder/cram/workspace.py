"""
The installed CRAM workspace as the plan builder's catalog reads it: robot annotations
and what their parts allow, object meshes, torso states and surface annotations, all
read from the workspace's own classes and files.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from typing_extensions import List, Set, Type, get_args

import coraplex
import semantic_digital_twin.robots

# defines the concrete surface annotations the catalog lists
import semantic_digital_twin.semantic_annotations.semantic_annotations  # noqa: F401
from coraplex.datastructures.enums import Arms
from cramera_plan_builder.exceptions import UnknownWorkspaceClass
from cramera_plan_builder.workspace import CramWorkspace
from cramera_protocol.bundle.files import MeshFormat
from cramera_protocol.plan_builder import ObjectModel, RobotModel, StepKind
from krrood.class_diagrams.attribute_introspector import DataclassOnlyIntrospector
from krrood.utils import recursive_subclasses
from semantic_digital_twin.datastructures.definitions import TorsoState
from semantic_digital_twin.robots.robot_part_mixins import (
    HasLeftRightArm,
    HasMobileBase,
)
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

ARM_STEPS = (StepKind.PARK_ARMS, StepKind.PICK_UP, StepKind.PLACE)
"""
The steps any robot with an arm can take.
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

    def steps(self) -> List[StepKind]:
        """
        :return: The steps the robot's parts allow, in the order :class:`StepKind`
            lists them: arms park, pick and place; a torso moves; a mobile base drives
            and transports.
        """
        parts = self.part_types()
        allowed = set()
        if any(issubclass(part, Arm) for part in parts):
            allowed.update(ARM_STEPS)
        if any(issubclass(part, Torso) for part in parts):
            allowed.add(StepKind.MOVE_TORSO)
        if issubclass(self.annotation, HasMobileBase):
            allowed.update({StepKind.NAVIGATE, StepKind.TRANSPORT})
        return [kind for kind in StepKind if kind in allowed]

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
            name=self.annotation.__name__,
            module=self.annotation.__module__,
            steps=self.steps(),
            arms=self.arms(),
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
        :param name: The class name of a robot annotation.
        :return: The annotation class.
        :raises UnknownWorkspaceClass: When no annotation has the name.
        """
        return WorkspaceClasses(self.annotations()).named(name)


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
class InstalledWorkspace(CramWorkspace):
    """
    The CRAM workspace this interpreter imports.
    """

    robot_annotations: RobotAnnotations = field(default_factory=RobotAnnotations)
    """
    The robot annotations.
    """

    directory: Path = OBJECT_DIRECTORY
    """
    The directory of the object meshes.
    """

    def robots(self) -> List[RobotModel]:
        return [
            RobotAnnotation(annotation).model()
            for annotation in self.robot_annotations.annotations()
        ]

    def objects(self) -> List[ObjectModel]:
        mesh_suffixes = {
            member.value
            for member in MeshFormat
            if member is not MeshFormat.MATERIAL_LIBRARY
        }
        return [
            ObjectModel(identifier=path.name, name=path.stem)
            for path in sorted(self.directory.iterdir())
            if path.is_file() and path.suffix.lower() in mesh_suffixes
        ]

    def object_directory(self) -> Path:
        return self.directory

    def torso_states(self) -> List[str]:
        return [state.name for state in TorsoState]

    def surface_types(self) -> List[str]:
        return [
            annotation.__name__ for annotation in SurfaceAnnotations().annotations()
        ]
