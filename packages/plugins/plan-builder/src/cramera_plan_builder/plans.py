"""
Checking plans against the builder's limits and its catalog, and keeping them in the
plan directory.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from typing_extensions import Iterable, List, Sized, Union

from cramera_plan_builder.exceptions import (
    DuplicateIdentifier,
    InvalidIdentifier,
    InvalidPlanName,
    InvalidPlanText,
    MissingStepParameter,
    PlanTooLarge,
    PlanWithoutRobot,
    TooManyEntries,
    UnknownPlan,
    UnknownReference,
    UnreadablePlan,
    UnsafeStoragePath,
    UnsupportedByCatalog,
    ValueOutOfRange,
)
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.geometry import Pose
from cramera_protocol.plan_builder import (
    PlacementMode,
    PlanBuilderCatalog,
    PlanBuilderLimits,
    PlanDocument,
    PlanKey,
    PlannedObject,
    PlannedObjectKey,
    PlannedRobot,
    PlannedRobotKey,
    PlanRecord,
    PlanStep,
    PlanStepKey,
    PlanSummary,
    RobotModel,
    StepConstraintKey,
    StepKind,
)

NAME_IDENTITY = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
"""
What a robot, object or step identity looks like: it names bodies and namespaces in the
built world.
"""

PLAN_IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,96}")
"""
What a saved plan's identity looks like.
"""

CONTROL_CHARACTER_LIMIT = 32
"""
Characters below this code point are control characters, which texts must not hold.
"""

PLAN_INDENTATION = 2
"""
The indentation of a saved plan's JSON, so it stays readable in an editor.
"""

LOCATION_SEPARATOR = "."
"""
Joins the keys of a location in a plan, for error messages.
"""


class PlanFile(StrEnum):
    """
    The files of the plan directory.
    """

    SUFFIX = ".json"
    """
    The suffix of a saved plan, named after its identity.
    """

    TEMPORARY_PREFIX = ".plan-"
    """
    The prefix of a plan being written, which is hidden until it is complete.
    """


STEP_PARAMETERS = MappingProxyType(
    {
        StepKind.PARK_ARMS: (PlanStepKey.ARM,),
        StepKind.MOVE_TORSO: (PlanStepKey.TORSO_STATE,),
        StepKind.NAVIGATE: (PlanStepKey.TARGET,),
        StepKind.TRANSPORT: (PlanStepKey.OBJECT, PlanStepKey.ARM),
        StepKind.PICK_UP: (PlanStepKey.OBJECT, PlanStepKey.ARM),
        StepKind.PLACE: (PlanStepKey.OBJECT, PlanStepKey.ARM),
    }
)
"""
The parameters each step kind needs, apart from where it puts an object down.
"""

PUTTING_DOWN = frozenset({StepKind.TRANSPORT, StepKind.PLACE})
"""
The step kinds that put an object down and so need a target or a surface.
"""

# %% limits


@dataclass(frozen=True)
class PlanCheck:
    """
    Checks that a plan is complete and stays within the builder's limits.
    """

    limits: PlanBuilderLimits
    """
    The limits.
    """

    def check(self, plan: PlanDocument) -> None:
        """
        :param plan: A plan as a browser sent it.
        :raises InvalidPlanName: For a name that cannot name a demo and a recording.
        :raises InvalidPlanText: For an empty or overly long text or one with control
            characters.
        :raises InvalidIdentifier: For an identity of other characters.
        :raises DuplicateIdentifier: For two robots, objects or steps of one identity.
        :raises TooManyEntries: For more robots, objects, steps or constraints than fit.
        :raises ValueOutOfRange: For a number that is not finite or beyond its limit.
        :raises UnknownReference: For a selected robot or step object the plan lacks.
        :raises PlanTooLarge: For a plan whose JSON is too large.
        """
        if not SceneName.is_valid(plan.name):
            raise InvalidPlanName(plan.name)
        if plan.task:
            self.text(PlanKey.TASK, plan.task)
        self.count(PlanKey.ROBOTS, plan.robots, self.limits.maximum_robots)
        self.count(PlanKey.OBJECTS, plan.objects, self.limits.maximum_objects)
        self.unique(PlanKey.ROBOTS, (robot.identifier for robot in plan.robots))
        self.unique(PlanKey.OBJECTS, (item.identifier for item in plan.objects))
        objects = {item.identifier for item in plan.objects}
        for planned_object in plan.objects:
            self.planned_object(planned_object)
        for robot in plan.robots:
            self.robot(robot, objects)
        robots = {robot.identifier for robot in plan.robots}
        if plan.selected_robot is not None and plan.selected_robot not in robots:
            raise UnknownReference(PlanKey.SELECTED_ROBOT, plan.selected_robot)
        size = len(json.dumps(plan.to_json(), allow_nan=False).encode("utf-8"))
        if size > self.limits.maximum_document_bytes:
            raise PlanTooLarge(size, self.limits.maximum_document_bytes)

    def robot(self, robot: PlannedRobot, objects: Iterable[str]) -> None:
        """
        :param robot: One robot of a plan.
        :param objects: The identities of the plan's objects.
        """
        location = self.location(PlanKey.ROBOTS, robot.identifier)
        self.identity(PlanKey.ROBOTS, robot.identifier)
        self.text(self.location(location, PlannedRobotKey.LABEL), robot.label)
        self.pose(self.location(location, PlannedRobotKey.POSE), robot.pose)
        for joint, value in robot.joint_positions.items():
            joint_location = self.location(
                location, PlannedRobotKey.JOINT_POSITIONS, joint
            )
            self.text(joint_location, joint)
            self.number(joint_location, value)
        steps_location = self.location(location, PlannedRobotKey.STEPS)
        self.count(steps_location, robot.steps, self.limits.maximum_steps)
        self.unique(steps_location, (step.identifier for step in robot.steps))
        for step in robot.steps:
            self.step(self.location(steps_location, step.identifier), step, objects)

    def step(self, location: str, step: PlanStep, objects: Iterable[str]) -> None:
        """
        :param location: Where the step sits.
        :param step: One step of a robot's plan.
        :param objects: The identities of the plan's objects.
        :raises UnknownReference: For a step acting on an object the plan lacks.
        """
        self.identity(location, step.identifier)
        if step.object_identifier is not None and step.object_identifier not in set(
            objects
        ):
            raise UnknownReference(
                self.location(location, PlanStepKey.OBJECT), step.object_identifier
            )
        if step.target is not None:
            self.pose(self.location(location, PlanStepKey.TARGET), step.target)
        constraints_location = self.location(location, PlanStepKey.CONSTRAINTS)
        self.count(
            constraints_location, step.constraints, self.limits.maximum_constraints
        )
        for constraint in step.constraints:
            self.text(
                self.location(constraints_location, StepConstraintKey.TEXT),
                constraint.text,
            )

    def complete(self, plan: PlanDocument) -> None:
        """
        :param plan: A plan whose limits were checked.
        :raises PlanWithoutRobot: For a plan without a robot.
        :raises MissingStepParameter: For a step without a parameter its kind needs,
            which a saved plan may still lack but a demo may not.
        """
        if not plan.robots:
            raise PlanWithoutRobot(plan.name)
        for robot in plan.robots:
            for step in robot.steps:
                location = self.location(
                    PlanKey.ROBOTS,
                    robot.identifier,
                    PlannedRobotKey.STEPS,
                    step.identifier,
                )
                given = {
                    PlanStepKey.ARM: step.arm,
                    PlanStepKey.TORSO_STATE: step.torso_state,
                    PlanStepKey.OBJECT: step.object_identifier,
                    PlanStepKey.TARGET: step.target,
                }
                for parameter in STEP_PARAMETERS[step.kind]:
                    if given[parameter] is None:
                        raise MissingStepParameter(location, parameter)
                if step.kind in PUTTING_DOWN:
                    self.destination(location, step)

    @staticmethod
    def destination(location: str, step: PlanStep) -> None:
        """
        :param location: Where the step sits.
        :param step: A step that puts an object down.
        :raises MissingStepParameter: When it names neither a pose nor a surface type,
            as its placement asks.
        """
        if step.placement is PlacementMode.POSE and step.target is None:
            raise MissingStepParameter(location, PlanStepKey.TARGET)
        if step.placement is PlacementMode.SURFACE and step.surface_type is None:
            raise MissingStepParameter(location, PlanStepKey.SURFACE_TYPE)

    def planned_object(self, planned_object: PlannedObject) -> None:
        """
        :param planned_object: One object of a plan.
        """
        location = self.location(PlanKey.OBJECTS, planned_object.identifier)
        self.identity(PlanKey.OBJECTS, planned_object.identifier)
        self.text(self.location(location, PlannedObjectKey.MODEL), planned_object.model)
        self.pose(self.location(location, PlannedObjectKey.POSE), planned_object.pose)

    @staticmethod
    def identity(location: str, identifier: str) -> None:
        """
        :param location: Where the identity sits.
        :param identifier: A robot, object or step identity.
        :raises InvalidIdentifier: Unless it starts with a letter and holds letters,
            digits and ``_`` only.
        """
        if NAME_IDENTITY.fullmatch(identifier) is None:
            raise InvalidIdentifier(location, identifier)

    def unique(self, location: str, identifiers: Iterable[str]) -> None:
        """
        :param location: Where the identities sit.
        :param identifiers: The identities of entries of one list.
        :raises DuplicateIdentifier: When two of them are equal.
        """
        seen = set()
        for identifier in identifiers:
            if identifier in seen:
                raise DuplicateIdentifier(location, identifier)
            seen.add(identifier)

    def text(self, location: str, text: str) -> None:
        """
        :param location: Where the text sits.
        :param text: A name, label, task or constraint.
        :raises InvalidPlanText: When it is blank, too long or holds control
            characters.
        """
        if (
            not text.strip()
            or len(text) > self.limits.maximum_text_length
            or any(ord(character) < CONTROL_CHARACTER_LIMIT for character in text)
        ):
            raise InvalidPlanText(location, text)

    def pose(self, location: str, pose: Pose) -> None:
        """
        :param location: Where the pose sits.
        :param pose: A position and orientation.
        """
        for index, value in enumerate(pose.to_json()):
            self.number(self.location(location, str(index)), value)

    def number(self, location: str, value: float) -> None:
        """
        :param location: Where the number sits.
        :param value: A coordinate or joint value.
        :raises ValueOutOfRange: When it is not finite or beyond the limit.
        """
        maximum = self.limits.maximum_coordinate
        if not math.isfinite(value) or abs(value) > maximum:
            raise ValueOutOfRange(location, value, maximum)

    @staticmethod
    def count(location: str, entries: Sized, limit: int) -> None:
        """
        :param location: Where the entries sit.
        :param entries: A list of a plan.
        :param limit: How many entries fit.
        :raises TooManyEntries: When it holds more.
        """
        if len(entries) > limit:
            raise TooManyEntries(location, len(entries), limit)

    @staticmethod
    def location(*steps: str) -> str:
        """
        :param steps: Keys from the plan's root.
        :return: The location they name, for error messages.
        """
        return LOCATION_SEPARATOR.join(steps)


# %% catalog


@dataclass(frozen=True)
class CatalogCheck:
    """
    Checks that a plan uses only what the catalog offers.
    """

    catalog: PlanBuilderCatalog
    """
    The catalog.
    """

    def check(self, plan: PlanDocument) -> None:
        """
        :param plan: A plan whose limits were checked.
        :raises UnsupportedByCatalog: For an environment, robot model, object model,
            step kind, arm, torso state or surface type the catalog does not offer;
            without the CRAM workspace only the environment is checked, since the
            catalog then offers no robots and objects.
        """
        environments = [entry.name for entry in self.catalog.environments]
        if plan.environment is not None:
            self.offered(PlanKey.ENVIRONMENT, plan.environment, environments)
        if self.catalog.missing:
            return
        objects = [model.identifier for model in self.catalog.objects]
        for planned_object in plan.objects:
            self.offered(
                PlanCheck.location(
                    PlanKey.OBJECTS, planned_object.identifier, PlannedObjectKey.MODEL
                ),
                planned_object.model,
                objects,
            )
        models = {model.name: model for model in self.catalog.robots}
        for robot in plan.robots:
            location = PlanCheck.location(PlanKey.ROBOTS, robot.identifier)
            self.offered(
                PlanCheck.location(location, PlannedRobotKey.MODEL),
                robot.model,
                list(models),
            )
            for step in robot.steps:
                self.step(
                    PlanCheck.location(
                        location, PlannedRobotKey.STEPS, step.identifier
                    ),
                    step,
                    models[robot.model],
                )

    def step(self, location: str, step: PlanStep, model: RobotModel) -> None:
        """
        :param location: Where the step sits.
        :param step: One step of the robot's plan.
        :param model: The robot's model.
        """
        self.offered(
            PlanCheck.location(location, PlanStepKey.KIND),
            step.kind,
            [kind.value for kind in model.steps],
        )
        if step.arm is not None:
            self.offered(
                PlanCheck.location(location, PlanStepKey.ARM), step.arm, model.arms
            )
        if step.torso_state is not None:
            self.offered(
                PlanCheck.location(location, PlanStepKey.TORSO_STATE),
                step.torso_state,
                self.catalog.torso_states,
            )
        if step.placement is PlacementMode.SURFACE and step.surface_type is not None:
            self.offered(
                PlanCheck.location(location, PlanStepKey.SURFACE_TYPE),
                step.surface_type,
                self.catalog.surface_types,
            )

    @staticmethod
    def offered(location: str, value: str, offered: List[str]) -> None:
        """
        :param location: Where the value sits.
        :param value: A value of the plan.
        :param offered: What the catalog offers there.
        :raises UnsupportedByCatalog: When the value is not offered.
        """
        if value not in offered:
            raise UnsupportedByCatalog(location, value, offered)


# %% storage


@dataclass(frozen=True)
class PlanStore:
    """
    The saved plans, one JSON file per plan, written whole or not at all.
    """

    directory: Path
    """
    The plan directory.
    """

    def summaries(self) -> List[PlanSummary]:
        """
        :return: Every readable saved plan, sorted by identity; a damaged plan does not
            hide the others.
        """
        if not self.directory.is_dir():
            return []
        summaries = []
        for path in sorted(self.directory.glob(f"*{PlanFile.SUFFIX}")):
            if path.is_symlink() or PLAN_IDENTITY.fullmatch(path.stem) is None:
                continue
            read = PlanFileReader(path).read()
            if isinstance(read, UnreadablePlan):
                continue
            summaries.append(
                PlanSummary(
                    identifier=path.stem,
                    name=read.name,
                    updated_at=datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc
                    ).isoformat(),
                )
            )
        return summaries

    def load(self, identifier: str) -> PlanRecord:
        """
        :param identifier: A plan's identity.
        :return: The saved plan.
        :raises InvalidIdentifier: For a malformed identity.
        :raises UnknownPlan: When no plan has the identity.
        :raises UnreadablePlan: When the plan's file is damaged.
        """
        path = self.path(identifier)
        if not path.is_file():
            raise UnknownPlan(identifier)
        read = PlanFileReader(path).read()
        if isinstance(read, UnreadablePlan):
            raise read
        return PlanRecord(identifier=identifier, document=read)

    def save(self, record: PlanRecord) -> PlanRecord:
        """
        :param record: A checked plan, with the identity of the plan it replaces or
            without one for a new plan.
        :return: The saved plan with its identity.
        :raises InvalidIdentifier: For a malformed identity.
        :raises UnsafeStoragePath: When the plan directory or file is a symbolic link.
        """
        identifier = record.identifier or uuid.uuid4().hex
        target = self.path(identifier)
        if self.directory.is_symlink():
            raise UnsafeStoragePath(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            prefix=PlanFile.TEMPORARY_PREFIX,
            delete=False,
        ) as temporary:
            json.dump(
                record.document.to_json(),
                temporary,
                indent=PLAN_INDENTATION,
                allow_nan=False,
            )
            temporary.write("\n")
        os.replace(temporary.name, target)
        return PlanRecord(identifier=identifier, document=record.document)

    def path(self, identifier: str) -> Path:
        """
        :param identifier: A plan's identity.
        :return: The plan's file.
        :raises InvalidIdentifier: For a malformed identity.
        :raises UnsafeStoragePath: When the file is a symbolic link.
        """
        if PLAN_IDENTITY.fullmatch(identifier) is None:
            raise InvalidIdentifier(PlanFile.SUFFIX, identifier)
        path = self.directory / f"{identifier}{PlanFile.SUFFIX}"
        if path.is_symlink():
            raise UnsafeStoragePath(path)
        return path


@dataclass(frozen=True)
class PlanFileReader:
    """
    Reads one saved plan file.
    """

    path: Path
    """
    The plan's file, named after its identity.
    """

    def read(self) -> Union[PlanDocument, UnreadablePlan]:
        """
        A saved plan is written by the store, so a file that is no plan is damaged; this
        is the one place where its reading errors become data, so a damaged plan does
        not hide the others.

        :return: The plan, or why it cannot be read.
        """
        try:
            return PlanDocument.from_json(
                json.loads(self.path.read_text(encoding="utf-8"))
            )
        except (ValueError, ProtocolError) as error:
            return UnreadablePlan(self.path.stem, str(error))
