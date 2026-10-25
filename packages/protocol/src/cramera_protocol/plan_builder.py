"""
The plan builder's documents: the plans a person composes from robot actions, the
catalog of robots, environments and objects a plan uses, the constraints written in
plain language, and the demos generated from a plan and run as child processes.

A plan names its robots, its objects and their poses, and each robot's steps; a step
names a native action by its class name and gives the action's fields as JSON values.
The generated demo builds the world and the native actions from it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

from typing_extensions import Any, Dict, List, Optional, Self

from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.document import JsonDocument, ValueLocation, document_field
from cramera_protocol.geometry import Pose
from cramera_protocol.live_messages import ConstraintMonitorType, MonitorSpecification
from cramera_protocol.version import CURRENT_VERSION, ProtocolVersion

PLAN_FORMAT_VERSION = ProtocolVersion(major=1, minor=2)
"""
The version plans are written with: steps name an action and its values, and robots a
model, by the protocol's identifiers.

Plans of an earlier version are migrated when they are read: those before
:data:`CLASS_NAME_FORMAT_VERSION` name a step kind, which becomes an action; those of
that version name the planner's classes, which :class:`SavedNames` translates.
"""

CLASS_NAME_FORMAT_VERSION = ProtocolVersion(major=1, minor=1)
"""
The version whose plans name actions and robot models by the planner's class names.
"""

# %% plugin


class PlanBuilderName(StrEnum):
    """
    The names under which the plan builder is installed.
    """

    PLUGIN = "plan-builder"
    """
    The plugin's name, which is also its route segment and its side panel's identity.
    """


class PlanBuilderFile(StrEnum):
    """
    The browser files of the plan builder, relative to its web directory.
    """

    MODULE = "index.js"
    """
    The module the viewer registers, which links to the builder page.
    """

    PAGE = "builder.html"
    """
    The builder page, which needs the whole window.
    """

    STEPS_STYLESHEET = "steps.css"
    """
    The look of plan step cards, shared by the builder page and the viewer's panel.
    """


class PlanBuilderRoute(StrEnum):
    """
    The plan builder's routes, below ``/api/plugins/plan-builder/``.
    """

    CATALOG = "catalog"
    """
    The robots, environments, objects, saved plans and limits the builder offers.
    """

    PLANS = "plans"
    """
    The saved plans; a plan record posted here is saved.
    """

    PLAN = "plans/"
    """
    The prefix of one saved plan: ``plans/<identifier>``.
    """

    CONSTRAINT = "constraint"
    """
    Compiles a constraint written in plain language into the monitor it means.
    """

    DEMO = "demo"
    """
    The demo generated from a posted plan, without writing it.
    """

    DEMOS = "demos"
    """
    Writes the demo generated from a posted plan into the output directory.
    """

    RUN = "run"
    """
    The state of the demo process; a run request posted here starts a demo.
    """

    RUN_STOP = "run/stop"
    """
    Stops the demo process.
    """

    OBJECT_FILES = "objects/"
    """
    The prefix of the object models' files: ``objects/<file>``.
    """


class PlanBuilderPageParameter(StrEnum):
    """
    The query parameters of the builder page, :attr:`PlanBuilderFile.PAGE`.
    """

    PLAN = "plan"
    """
    The identity of a saved plan the page opens.
    """

    ENVIRONMENT = "environment"
    """
    The name of an environment bundle a new plan starts in.
    """


class PlanBuilderVariable(StrEnum):
    """
    The environment variables the plan builder reads.
    """

    OUTPUT = "CRAMERA_PLAN_BUILDER_OUTPUT"
    """
    The directory generated demos are written to, below cramera's data directory by
    default.
    """

    PORT = "CRAMERA_PLAN_BUILDER_PORT"
    """
    The port started demos publish their world on, the live publisher's port by default.
    """


# %% destinations


class PlacementMode(StrEnum):
    """
    How a step that puts an object down names where.
    """

    POSE = "pose"
    """
    At an exact pose.
    """

    SURFACE = "surface"
    """
    On or in an annotated surface of the environment, at a free spot found when the step
    runs.
    """


class DestinationKey(StrEnum):
    """
    The keys of where a step puts an object down.
    """

    PLACEMENT = "placement"
    """
    Whether the object goes to a pose or onto a surface.
    """

    POSE = "pose"
    """
    The pose.
    """

    SURFACE_TYPE = "surfaceType"
    """
    The class of the surface.
    """

    SURFACE_NAME = "surfaceName"
    """
    The surface.
    """


@dataclass(kw_only=True)
class Destination(JsonDocument):
    """
    Where a step puts an object down: at a pose, or on or in a surface of the
    environment; the value of a field that accepts a surface.
    """

    placement: PlacementMode = document_field(
        DestinationKey.PLACEMENT, default=PlacementMode.POSE
    )
    """
    Whether the object goes to :attr:`pose` or onto a surface.
    """

    pose: Optional[Pose] = document_field(DestinationKey.POSE, default=None)
    """
    The pose in world coordinates the object is put down at.
    """

    surface_type: Optional[str] = document_field(
        DestinationKey.SURFACE_TYPE, default=None
    )
    """
    The class name of the surface annotation the object is put on or in.
    """

    surface_name: Optional[str] = document_field(
        DestinationKey.SURFACE_NAME, default=None
    )
    """
    The name of one surface annotation, or None for any surface of the type.
    """


# %% constraints


class StepConstraintKey(StrEnum):
    """
    The keys of a constraint attached to a step.
    """

    TEXT = "text"
    """
    The constraint as it was written.
    """

    MONITOR_TYPE = "monitorType"
    """
    The monitor the sentence means.
    """

    MONITOR = "monitor"
    """
    The monitor observed while the step runs.
    """

    SWITCH = "switch"
    """
    The switch of the step's action the constraint turns on.
    """


@dataclass(kw_only=True)
class StepConstraint(JsonDocument):
    """
    A constraint written in plain language and what it compiled to: a monitor the live
    publisher observes, a switch of the step's own action, both or neither.
    """

    text: str = document_field(StepConstraintKey.TEXT)
    """
    The constraint as it was written.
    """

    monitor_type: Optional[ConstraintMonitorType] = document_field(
        StepConstraintKey.MONITOR_TYPE, default=None
    )
    """
    The monitor the sentence means, or None when no rule matches it.
    """

    monitor: Optional[MonitorSpecification] = document_field(
        StepConstraintKey.MONITOR, default=None
    )
    """
    The monitor the live publisher observes while the step runs, or None when the
    sentence names nothing to observe.
    """

    switch: Optional[str] = document_field(StepConstraintKey.SWITCH, default=None)
    """
    The boolean field of the step's action the constraint turns on, or None.
    """


class ConstraintTextKey(StrEnum):
    """
    The keys of a request compiling a constraint.
    """

    TEXT = "text"
    """
    The constraint as it was written.
    """

    STEP_ACTION = "stepAction"
    """
    The action of the step the constraint is attached to.
    """

    STEP_OBJECT = "stepObject"
    """
    The object the step acts on.
    """

    OBJECTS = "objects"
    """
    The names of the plan's objects.
    """


@dataclass(kw_only=True)
class ConstraintText(JsonDocument):
    """
    A constraint to compile, with what the plan tells about its subject.
    """

    text: str = document_field(ConstraintTextKey.TEXT)
    """
    The constraint as it was written.
    """

    step_action: Optional[str] = document_field(
        ConstraintTextKey.STEP_ACTION, default=None
    )
    """
    The class name of the action of the step it is attached to, or None for a constraint
    not attached yet.
    """

    step_object: Optional[str] = document_field(
        ConstraintTextKey.STEP_OBJECT, default=None
    )
    """
    The identifier of the object the step acts on, which the constraint is about when
    the sentence names no object.
    """

    objects: List[str] = document_field(ConstraintTextKey.OBJECTS, default_factory=list)
    """
    The identifiers of the plan's objects, which a sentence can name.
    """


class RuleValue(StrEnum):
    """
    Values of a rule's monitor parameters that stand for something the sentence or the
    plan supplies.
    """

    OBJECT = "@object"
    """
    The body name of the object the constraint is about.
    """

    LENGTH = "@length"
    """
    The length the sentence gives, in metres, or the rule's default length.
    """

    REFERENCE = "@reference"
    """
    The body name of a second object the sentence names, which the first is measured
    against.
    """


class ConstraintRuleKey(StrEnum):
    """
    The keys of one rule of the constraint rule book.
    """

    MONITOR_TYPE = "monitorType"
    """
    The monitor a matching sentence means.
    """

    PHRASING = "phrasing"
    """
    The regular expression a sentence matches.
    """

    EXAMPLES = "examples"
    """
    Wordings the rule understands, for people.
    """

    SENTENCE = "sentence"
    """
    A whole constraint the rule understands, offered to start from.
    """

    EFFECT = "effect"
    """
    What the monitor checks, for people.
    """

    PARAMETERS = "parameters"
    """
    The monitor's parameters.
    """

    DEFAULT_LENGTH = "defaultLength"
    """
    The length the monitor uses when the sentence gives none.
    """

    OBSERVED = "observed"
    """
    Whether the live publisher can observe the monitor.
    """

    SWITCH = "switch"
    """
    The boolean field of the step's action the constraint turns on.
    """


@dataclass(kw_only=True)
class ConstraintRule(JsonDocument):
    """
    One wording of a constraint and the monitor it means.
    """

    monitor_type: ConstraintMonitorType = document_field(ConstraintRuleKey.MONITOR_TYPE)
    """
    The monitor a matching sentence means.
    """

    phrasing: str = document_field(ConstraintRuleKey.PHRASING)
    """
    The regular expression a lowercase sentence is searched for.
    """

    examples: str = document_field(ConstraintRuleKey.EXAMPLES)
    """
    Wordings the rule understands, for the builder's explanation.
    """

    sentence: str = document_field(ConstraintRuleKey.SENTENCE)
    """
    A whole constraint the rule understands, which the builder offers to start from.
    """

    effect: str = document_field(ConstraintRuleKey.EFFECT)
    """
    What the monitor checks, for the builder's explanation.
    """

    parameters: Dict[str, Any] = document_field(
        ConstraintRuleKey.PARAMETERS, default_factory=dict
    )
    """
    The monitor's parameters by
    :class:`~cramera_protocol.live_messages.MonitorParameterKey`; a :class:`RuleValue`
    stands for what the sentence or the plan supplies.
    """

    default_length: Optional[float] = document_field(
        ConstraintRuleKey.DEFAULT_LENGTH, default=None
    )
    """
    The length in metres :attr:`RuleValue.LENGTH` stands for when the sentence gives
    none.
    """

    observed: bool = document_field(ConstraintRuleKey.OBSERVED, default=True)
    """
    Whether the live publisher can observe the monitor from the parameters alone.
    """

    switch: Optional[str] = document_field(ConstraintRuleKey.SWITCH, default=None)
    """
    The name of the boolean field the constraint turns on; it applies to a step whose
    action has a boolean field of that name.
    """


class ConstraintRuleBookKey(StrEnum):
    """
    The keys of the constraint rule book.
    """

    RULES = "rules"
    """
    The rules, in the order they are tried.
    """

    UNITS = "units"
    """
    The length units a sentence may use.
    """

    LENGTH = "length"
    """
    The regular expression finding a number and its unit.
    """


@dataclass(kw_only=True)
class ConstraintRuleBook(JsonDocument):
    """
    How sentences become monitors: rules tried in order, and how lengths are read.
    """

    rules: List[ConstraintRule] = document_field(
        ConstraintRuleBookKey.RULES, default_factory=list
    )
    """
    The rules, in the order they are tried; the first match wins.
    """

    units: Dict[str, float] = document_field(
        ConstraintRuleBookKey.UNITS, default_factory=dict
    )
    """
    How many metres one of each unit is, by the unit's spelling.
    """

    length: str = document_field(ConstraintRuleBookKey.LENGTH)
    """
    The regular expression whose first group is a number and second group a unit of
    :attr:`units`.
    """


# %% plan


class PlanStepKey(StrEnum):
    """
    The keys of one step of a robot's plan.
    """

    IDENTIFIER = "id"
    """
    The step's identity within the plan.
    """

    ACTION = "action"
    """
    The native action the step is.
    """

    VALUES = "values"
    """
    The values of the action's fields.
    """

    CONSTRAINTS = "constraints"
    """
    The constraints attached to the step.
    """


@dataclass(kw_only=True)
class PlanStep(JsonDocument):
    """
    One native action of a robot's plan with the values of its fields; a step written in
    the format before :data:`CLASS_NAME_FORMAT_VERSION`, naming a step kind, is read as
    the action that kind stood for.
    """

    identifier: str = document_field(PlanStepKey.IDENTIFIER)
    """
    The step's identity within the plan.
    """

    action: str = document_field(PlanStepKey.ACTION)
    """
    The native action's identifier, as the catalog's action schemas name it.
    """

    values: Dict[str, Any] = document_field(PlanStepKey.VALUES, default_factory=dict)
    """
    The JSON values of the action's fields by field name: an object's identity, an
    annotation's name, an enumeration member's name, a pose, a :class:`Destination`, a
    number, a boolean or a text, as the field's :class:`ActionFieldKind` asks; fields
    left out keep the action's default.
    """

    constraints: List[StepConstraint] = document_field(
        PlanStepKey.CONSTRAINTS, default_factory=list
    )
    """
    The constraints attached to the step.
    """

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read a step, migrating one that names a step kind; see
        :meth:`JsonDocument.read_at`.
        """
        if isinstance(data, dict) and LegacyStepKey.KIND in data:
            return LegacyPlanStep.read_at(data, location).migrated()
        return super().read_at(data, location)


# %% steps of earlier plans


class LegacyStepKind(StrEnum):
    """
    The step kinds plans named before :data:`CLASS_NAME_FORMAT_VERSION`; read only to
    migrate such plans.
    """

    PARK_ARMS = "park_arms"
    """
    Parked arms.
    """

    MOVE_TORSO = "move_torso"
    """
    Moved the torso to a named height.
    """

    NAVIGATE = "navigate"
    """
    Drove the base to a pose.
    """

    TRANSPORT = "transport"
    """
    Carried an object to a pose or a surface.
    """

    PICK_UP = "pick_up"
    """
    Picked an object up.
    """

    PLACE = "place"
    """
    Put a held object down at a pose or on a surface.
    """


class MigratedAction(StrEnum):
    """
    The native actions the step kinds of earlier plans stood for, named as plans of
    :data:`CLASS_NAME_FORMAT_VERSION` named them, by the planner's class names; frozen,
    since :class:`SavedNames` translates them further.
    """

    PARK_ARMS = "ParkArmsAction"
    """
    Parks arms.
    """

    MOVE_TORSO = "MoveTorsoAction"
    """
    Moves the torso.
    """

    NAVIGATE = "NavigateAction"
    """
    Drives the base.
    """

    TRANSPORT = "TransportAction"
    """
    Carries an object.
    """

    PICK_UP = "PickUpAction"
    """
    Picks an object up.
    """

    PLACE = "PlaceAction"
    """
    Puts a held object down.
    """


class MigratedActionField(StrEnum):
    """
    The fields of the migrated actions the parameters of earlier steps become.
    """

    ARM = "arm"
    """
    The arm.
    """

    TORSO_STATE = "torso_state"
    """
    The torso height.
    """

    OBJECT = "object_designator"
    """
    The object acted on.
    """

    TARGET = "target_location"
    """
    Where the base drives to or the object is put down.
    """


MIGRATED_ACTIONS = MappingProxyType(
    {
        LegacyStepKind.PARK_ARMS: MigratedAction.PARK_ARMS,
        LegacyStepKind.MOVE_TORSO: MigratedAction.MOVE_TORSO,
        LegacyStepKind.NAVIGATE: MigratedAction.NAVIGATE,
        LegacyStepKind.TRANSPORT: MigratedAction.TRANSPORT,
        LegacyStepKind.PICK_UP: MigratedAction.PICK_UP,
        LegacyStepKind.PLACE: MigratedAction.PLACE,
    }
)
"""
The native action each step kind of earlier plans stood for.
"""

DESTINATION_KINDS = frozenset({LegacyStepKind.TRANSPORT, LegacyStepKind.PLACE})
"""
The step kinds of earlier plans whose target was a :class:`Destination`.
"""


class LegacyStepKey(StrEnum):
    """
    The keys of a step of a plan written before :data:`CLASS_NAME_FORMAT_VERSION`.
    """

    IDENTIFIER = "id"
    """
    The step's identity.
    """

    KIND = "kind"
    """
    The step kind, whose presence marks such a step.
    """

    ARM = "arm"
    """
    The arm.
    """

    TORSO_STATE = "torsoState"
    """
    The torso height.
    """

    OBJECT = "object"
    """
    The object acted on.
    """

    TARGET = "target"
    """
    The pose driven to or put down at.
    """

    PLACEMENT = "placement"
    """
    Whether the object went to the pose or onto a surface.
    """

    SURFACE_TYPE = "surfaceType"
    """
    The class of the surface.
    """

    SURFACE_NAME = "surfaceName"
    """
    The surface.
    """

    CONSTRAINTS = "constraints"
    """
    The constraints.
    """


@dataclass(kw_only=True)
class LegacyPlanStep(JsonDocument):
    """
    A step of a plan written before :data:`CLASS_NAME_FORMAT_VERSION`: a step kind with
    kind-specific parameters, read only to migrate it.
    """

    identifier: str = document_field(LegacyStepKey.IDENTIFIER)
    """
    The step's identity.
    """

    kind: LegacyStepKind = document_field(LegacyStepKey.KIND)
    """
    The step kind.
    """

    arm: Optional[str] = document_field(LegacyStepKey.ARM, default=None)
    """
    The name of the arm choice.
    """

    torso_state: Optional[str] = document_field(LegacyStepKey.TORSO_STATE, default=None)
    """
    The name of the torso state.
    """

    object_identifier: Optional[str] = document_field(
        LegacyStepKey.OBJECT, default=None
    )
    """
    The identity of the object acted on.
    """

    target: Optional[Pose] = document_field(LegacyStepKey.TARGET, default=None)
    """
    The pose driven to or put down at.
    """

    placement: PlacementMode = document_field(
        LegacyStepKey.PLACEMENT, default=PlacementMode.POSE
    )
    """
    Whether the object went to :attr:`target` or onto a surface.
    """

    surface_type: Optional[str] = document_field(
        LegacyStepKey.SURFACE_TYPE, default=None
    )
    """
    The class name of the surface annotation.
    """

    surface_name: Optional[str] = document_field(
        LegacyStepKey.SURFACE_NAME, default=None
    )
    """
    The name of one surface annotation.
    """

    constraints: List[StepConstraint] = document_field(
        LegacyStepKey.CONSTRAINTS, default_factory=list
    )
    """
    The constraints, whose switches already named the action's fields.
    """

    def migrated(self) -> PlanStep:
        """
        :return: The step as the native action its kind stood for, with the parameters
            it gave as the action's values.
        """
        values: Dict[str, Any] = {}
        given = {
            MigratedActionField.ARM: self.arm,
            MigratedActionField.TORSO_STATE: self.torso_state,
            MigratedActionField.OBJECT: self.object_identifier,
        }
        for field_name, value in given.items():
            if value is not None:
                values[field_name.value] = value
        target = self.target_value()
        if target is not None:
            values[MigratedActionField.TARGET.value] = target
        return PlanStep(
            identifier=self.identifier,
            action=MIGRATED_ACTIONS[self.kind].value,
            values=values,
            constraints=self.constraints,
        )

    def target_value(self) -> Any:
        """
        :return: The JSON value of the migrated target: a :class:`Destination` for a
            step putting an object down, a pose for a navigation, or None when the step
            gave none.
        """
        if self.kind in DESTINATION_KINDS:
            if self.target is None and self.surface_type is None:
                return None
            return Destination(
                placement=self.placement,
                pose=self.target,
                surface_type=self.surface_type,
                surface_name=self.surface_name,
            ).to_json()
        if self.target is None:
            return None
        return self.target.to_json()


class PlannedRobotKey(StrEnum):
    """
    The keys of one robot of a plan.
    """

    IDENTIFIER = "id"
    """
    The robot's identity within the plan.
    """

    MODEL = "model"
    """
    The robot's annotation class.
    """

    LABEL = "label"
    """
    The robot's display name.
    """

    POSE = "pose"
    """
    Where the robot starts.
    """

    JOINT_POSITIONS = "jointPositions"
    """
    The robot's start posture.
    """

    STEPS = "steps"
    """
    The robot's plan.
    """


@dataclass(kw_only=True)
class PlannedRobot(JsonDocument):
    """
    One robot of a plan: its model, where it starts and what it does.
    """

    identifier: str = document_field(PlannedRobotKey.IDENTIFIER)
    """
    The robot's identity within the plan; it also namespaces the robot's names in the
    built world, so it starts with a letter and holds letters, digits and ``_``.
    """

    model: str = document_field(PlannedRobotKey.MODEL)
    """
    The robot model's identifier, as the catalog lists it.
    """

    label: str = document_field(PlannedRobotKey.LABEL)
    """
    The robot's display name.
    """

    pose: Pose = document_field(PlannedRobotKey.POSE)
    """
    Where the robot's base starts, in world coordinates.
    """

    joint_positions: Dict[str, float] = document_field(
        PlannedRobotKey.JOINT_POSITIONS, default_factory=dict
    )
    """
    Start values of the robot's joints by their full names.
    """

    steps: List[PlanStep] = document_field(PlannedRobotKey.STEPS, default_factory=list)
    """
    The robot's plan, in the order it runs.
    """


class PlannedObjectKey(StrEnum):
    """
    The keys of one object of a plan.
    """

    IDENTIFIER = "id"
    """
    The object's name in the built world.
    """

    MODEL = "model"
    """
    The object model it is a copy of.
    """

    POSE = "pose"
    """
    Where the object starts.
    """

    COLOR = "color"
    """
    The object's colour.
    """


@dataclass(kw_only=True)
class PlannedObject(JsonDocument):
    """
    One free object of a plan, a copy of an object model at a start pose.
    """

    identifier: str = document_field(PlannedObjectKey.IDENTIFIER)
    """
    The name of the object's body in the built world, which steps and constraints name.
    """

    model: str = document_field(PlannedObjectKey.MODEL)
    """
    The identifier of the object model, as the catalog lists it.
    """

    pose: Pose = document_field(PlannedObjectKey.POSE)
    """
    Where the object starts, in world coordinates.
    """

    color: Optional[str] = document_field(PlannedObjectKey.COLOR, default=None)
    """
    The object's colour as a CSS hexadecimal colour, or None for the model's own.
    """


class PlanKey(StrEnum):
    """
    The keys of a plan.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The format version the plan is written in.
    """

    NAME = "name"
    """
    The plan's name.
    """

    TASK = "task"
    """
    What the plan does.
    """

    ENVIRONMENT = "environment"
    """
    The environment bundle the plan runs in.
    """

    ROBOTS = "robots"
    """
    The robots.
    """

    SELECTED_ROBOT = "selectedRobot"
    """
    The robot whose plan runs.
    """

    OBJECTS = "objects"
    """
    The free objects.
    """


@dataclass(kw_only=True)
class PlanDocument(JsonDocument):
    """
    A composed plan: the environment, the robots with their steps, and the free objects;
    the selected robot's steps run when the generated demo runs.
    """

    name: str = document_field(PlanKey.NAME)
    """
    The plan's name; the generated demo's file and recording are named after it.
    """

    format_version: ProtocolVersion = document_field(
        PlanKey.FORMAT_VERSION, default=PLAN_FORMAT_VERSION
    )
    """
    The format version the plan is written in.

    A plan before :data:`CLASS_NAME_FORMAT_VERSION` is migrated to that version when it
    is read; a plan of that version is translated by :class:`SavedNames` and then
    carries :data:`PLAN_FORMAT_VERSION`.
    """

    task: str = document_field(PlanKey.TASK, default="")
    """
    What the plan does, as the scene picker labels its recording.
    """

    environment: Optional[str] = document_field(PlanKey.ENVIRONMENT, default=None)
    """
    The name of the environment bundle, or None for an empty floor.
    """

    robots: List[PlannedRobot] = document_field(PlanKey.ROBOTS, default_factory=list)
    """
    The robots, in the order they were added.
    """

    selected_robot: Optional[str] = document_field(PlanKey.SELECTED_ROBOT, default=None)
    """
    The identifier of the robot whose plan runs.
    """

    objects: List[PlannedObject] = document_field(PlanKey.OBJECTS, default_factory=list)
    """
    The free objects, in the order they were added.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read a plan, migrating one of an earlier format version; see
        :meth:`JsonDocument.read_at`.
        """
        plan = super().read_at(data, location)
        if plan.format_version < CLASS_NAME_FORMAT_VERSION or cls.names_step_kinds(
            data
        ):
            plan.format_version = CLASS_NAME_FORMAT_VERSION
        return plan

    @staticmethod
    def names_step_kinds(data: Any) -> bool:
        """
        :param data: A plan's JSON object.
        :return: Whether a step names a step kind, which a plan without a format version
            may do and which migrates to the planner's class names.
        """
        robots = data.get(PlanKey.ROBOTS, []) if isinstance(data, dict) else []
        return any(
            isinstance(step, dict) and LegacyStepKey.KIND in step
            for robot in robots
            if isinstance(robot, dict)
            for step in robot.get(PlannedRobotKey.STEPS, [])
        )


# %% saved plans


class PlanSummaryKey(StrEnum):
    """
    The keys of a saved plan in the plan list.
    """

    IDENTIFIER = "id"
    """
    The plan's identity.
    """

    NAME = "name"
    """
    The plan's name.
    """

    UPDATED_AT = "updatedAt"
    """
    When the plan was last saved.
    """


@dataclass(kw_only=True)
class PlanSummary(JsonDocument):
    """
    A saved plan as the plan list offers it.
    """

    identifier: str = document_field(PlanSummaryKey.IDENTIFIER)
    """
    The plan's identity.
    """

    name: str = document_field(PlanSummaryKey.NAME)
    """
    The plan's name.
    """

    updated_at: str = document_field(PlanSummaryKey.UPDATED_AT)
    """
    When the plan was last saved, as an ISO 8601 date and time in UTC.
    """


class PlanRecordKey(StrEnum):
    """
    The keys of a plan with its identity.
    """

    IDENTIFIER = "id"
    """
    The plan's identity.
    """

    DOCUMENT = "document"
    """
    The plan.
    """


@dataclass(kw_only=True)
class PlanRecord(JsonDocument):
    """
    A plan with its identity: what is posted to be saved and what a saved plan is
    answered with.
    """

    document: PlanDocument = document_field(PlanRecordKey.DOCUMENT)
    """
    The plan.
    """

    identifier: Optional[str] = document_field(PlanRecordKey.IDENTIFIER, default=None)
    """
    The plan's identity; None in a request to save a new plan.
    """


class PlanListKey(StrEnum):
    """
    The keys of the plan list.
    """

    PLANS = "plans"
    """
    The saved plans.
    """


@dataclass(kw_only=True)
class PlanList(JsonDocument):
    """
    The saved plans.
    """

    plans: List[PlanSummary] = document_field(PlanListKey.PLANS, default_factory=list)
    """
    The saved plans, sorted by identity.
    """


# %% limits


class PlanBuilderLimitsKey(StrEnum):
    """
    The keys of the plan builder's limits.
    """

    MAXIMUM_ROBOTS = "maximumRobots"
    """
    How many robots a plan holds at most.
    """

    MAXIMUM_OBJECTS = "maximumObjects"
    """
    How many objects a plan holds at most.
    """

    MAXIMUM_STEPS = "maximumSteps"
    """
    How many steps a robot's plan holds at most.
    """

    MAXIMUM_CONSTRAINTS = "maximumConstraints"
    """
    How many constraints a step holds at most.
    """

    MAXIMUM_TEXT_LENGTH = "maximumTextLength"
    """
    How long a name, a task or a constraint is at most.
    """

    MAXIMUM_DOCUMENT_BYTES = "maximumDocumentBytes"
    """
    How large a posted plan is at most.
    """

    MAXIMUM_COORDINATE = "maximumCoordinate"
    """
    The largest magnitude of a coordinate or joint value.
    """

    MAXIMUM_LOG_BYTES = "maximumLogBytes"
    """
    How much of a demo's output is kept.
    """


KIBIBYTE = 1024
"""
The number of bytes in a kibibyte.
"""


@dataclass(kw_only=True)
class PlanBuilderLimits(JsonDocument):
    """
    The bounds every plan and demo stays within; the browser checks against the same
    values the server enforces.
    """

    maximum_robots: int = document_field(PlanBuilderLimitsKey.MAXIMUM_ROBOTS, default=8)
    """
    How many robots a plan holds at most.
    """

    maximum_objects: int = document_field(
        PlanBuilderLimitsKey.MAXIMUM_OBJECTS, default=64
    )
    """
    How many objects a plan holds at most.
    """

    maximum_steps: int = document_field(PlanBuilderLimitsKey.MAXIMUM_STEPS, default=64)
    """
    How many steps a robot's plan holds at most.
    """

    maximum_constraints: int = document_field(
        PlanBuilderLimitsKey.MAXIMUM_CONSTRAINTS, default=16
    )
    """
    How many constraints a step holds at most.
    """

    maximum_text_length: int = document_field(
        PlanBuilderLimitsKey.MAXIMUM_TEXT_LENGTH, default=200
    )
    """
    How many characters a name, a label, a task or a constraint has at most.
    """

    maximum_document_bytes: int = document_field(
        PlanBuilderLimitsKey.MAXIMUM_DOCUMENT_BYTES, default=512 * KIBIBYTE
    )
    """
    How large a posted plan's JSON is at most, in bytes.
    """

    maximum_coordinate: float = document_field(
        PlanBuilderLimitsKey.MAXIMUM_COORDINATE, default=1000.0
    )
    """
    The largest magnitude of a coordinate in metres or a joint value.
    """

    maximum_log_bytes: int = document_field(
        PlanBuilderLimitsKey.MAXIMUM_LOG_BYTES, default=64 * KIBIBYTE
    )
    """
    How many of the newest bytes of a demo's output are kept.
    """


# %% actions


class ActionFieldKind(StrEnum):
    """
    What a field of a native action holds, which decides how the builder asks for it and
    how the demo converts it.
    """

    BODY = "body"
    """
    An object of the plan, named by its identity.
    """

    ANNOTATION = "annotation"
    """
    A world entity carrying a given semantic annotation class, named by the annotation's
    name.
    """

    ENUM = "enum"
    """
    A member of an enumeration, named by the member's name.
    """

    POSE = "pose"
    """
    A pose in world coordinates.
    """

    POSE_OR_SURFACE = "poseOrSurface"
    """
    A pose, or the free spots of a surface sampled when the step runs.
    """

    NUMBER = "number"
    """
    A real number.
    """

    INTEGER = "integer"
    """
    A whole number.
    """

    BOOLEAN = "boolean"
    """
    A switch that is on or off.
    """

    TEXT = "text"
    """
    A text.
    """

    GRASP = "grasp"
    """
    A grasp, never entered: the demo derives it from the action's arm and object.
    """


class ActionGroup(StrEnum):
    """
    The packages of native actions the builder groups its palette by.
    """

    CORE = "core"
    """
    The actions the robot performs directly.
    """

    COMPOSITE = "composite"
    """
    The actions made of other actions.
    """


class ActionFieldKey(StrEnum):
    """
    The keys of one field of an action schema.
    """

    NAME = "name"
    """
    The field's keyword argument.
    """

    LABEL = "label"
    """
    The field's display name.
    """

    KIND = "kind"
    """
    What the field holds.
    """

    REQUIRED = "required"
    """
    Whether a step must give the field.
    """

    DEFAULT = "default"
    """
    The value the action takes when a step leaves the field out.
    """

    ENUM_TYPE = "enumType"
    """
    The enumeration of an enumeration field.
    """

    MEMBERS = "members"
    """
    The members of the enumeration.
    """

    ANNOTATION = "annotation"
    """
    The annotation class of an annotation field.
    """

    ACCEPTS_SURFACE = "acceptsSurface"
    """
    Whether a pose field also takes a surface.
    """

    DERIVED_FROM = "derivedFrom"
    """
    The fields a derived field is computed from.
    """

    DOCUMENTATION = "documentation"
    """
    What the field means.
    """


@dataclass(kw_only=True)
class ActionField(JsonDocument):
    """
    One keyword argument of a native action the builder offers, with what it holds.
    """

    name: str = document_field(ActionFieldKey.NAME)
    """
    The keyword argument, which a step's values are keyed by.
    """

    label: str = document_field(ActionFieldKey.LABEL)
    """
    The display name.
    """

    kind: ActionFieldKind = document_field(ActionFieldKey.KIND)
    """
    What the field holds.
    """

    required: bool = document_field(ActionFieldKey.REQUIRED)
    """
    Whether a step must give the field before its demo runs.
    """

    default: Any = document_field(ActionFieldKey.DEFAULT, default=None)
    """
    The JSON form of the value the action takes when a step leaves the field out, or
    None when it has none or none JSON can hold.
    """

    enum_type: Optional[str] = document_field(ActionFieldKey.ENUM_TYPE, default=None)
    """
    The class name of the enumeration of an :attr:`ActionFieldKind.ENUM` field.
    """

    members: List[str] = document_field(ActionFieldKey.MEMBERS, default_factory=list)
    """
    The names of the enumeration's members, in their order.
    """

    annotation: Optional[str] = document_field(ActionFieldKey.ANNOTATION, default=None)
    """
    The class name of the semantic annotation an :attr:`ActionFieldKind.ANNOTATION`
    field names an entity of.
    """

    accepts_surface: bool = document_field(
        ActionFieldKey.ACCEPTS_SURFACE, default=False
    )
    """
    Whether the field takes a surface besides a pose; its value is then a
    :class:`Destination`.
    """

    derived_from: List[str] = document_field(
        ActionFieldKey.DERIVED_FROM, default_factory=list
    )
    """
    The names of the fields an :attr:`ActionFieldKind.GRASP` field is derived from: the
    arm and the object.
    """

    documentation: str = document_field(ActionFieldKey.DOCUMENTATION, default="")
    """
    What the field means, as its attribute docstring says, or the empty text.
    """


class HiddenActionFieldKey(StrEnum):
    """
    The keys of a field the builder leaves at its default.
    """

    NAME = "name"
    """
    The field's keyword argument.
    """

    TYPE = "type"
    """
    The field's type.
    """


@dataclass(kw_only=True)
class HiddenActionField(JsonDocument):
    """
    A field with a default whose type the builder has no form control for; the action
    keeps its default.
    """

    name: str = document_field(HiddenActionFieldKey.NAME)
    """
    The keyword argument.
    """

    type_name: str = document_field(HiddenActionFieldKey.TYPE)
    """
    The field's type as text, or why it cannot be resolved.
    """


class ActionSchemaKey(StrEnum):
    """
    The keys of one action schema.
    """

    NAME = "name"
    """
    The action's identifier.
    """

    MODULE = "module"
    """
    The module defining the class.
    """

    LABEL = "label"
    """
    The action's display name.
    """

    SAVED_AS = "savedAs"
    """
    The names plans saved the action under before the protocol named it.
    """

    GROUP = "group"
    """
    The package the action belongs to.
    """

    DOCUMENTATION = "documentation"
    """
    What the action does.
    """

    FIELDS = "fields"
    """
    The fields a step gives.
    """

    HIDDEN = "hidden"
    """
    The fields left at their default.
    """

    AVAILABLE = "available"
    """
    Whether a step can be this action.
    """

    UNAVAILABLE_REASON = "unavailableReason"
    """
    Why a step cannot be this action.
    """


@dataclass(kw_only=True)
class ActionSchema(JsonDocument):
    """
    A native action of the CRAM workspace as the builder offers it: its fields, read
    from the action's dataclass fields, and whether every required one has a form
    control.
    """

    name: str = document_field(ActionSchemaKey.NAME)
    """
    The action's identifier, which plans name it by and which stays when the planner
    renames its class, such as ``pick_up``.
    """

    module: str = document_field(ActionSchemaKey.MODULE)
    """
    The module defining the class.
    """

    label: str = document_field(ActionSchemaKey.LABEL)
    """
    The display name: the words of the class name without the ``Action`` suffix.
    """

    group: str = document_field(ActionSchemaKey.GROUP)
    """
    The package below the actions package the module lies in, mostly an
    :class:`ActionGroup` value.
    """

    documentation: str = document_field(ActionSchemaKey.DOCUMENTATION, default="")
    """
    The first paragraph of the class's docstring, or the empty text.
    """

    fields: List[ActionField] = document_field(
        ActionSchemaKey.FIELDS, default_factory=list
    )
    """
    The fields a step gives, required ones first, in the order the class declares them.
    """

    hidden: List[HiddenActionField] = document_field(
        ActionSchemaKey.HIDDEN, default_factory=list
    )
    """
    The fields with a default the builder has no form control for.
    """

    available: bool = document_field(ActionSchemaKey.AVAILABLE, default=True)
    """
    Whether a step can be this action.
    """

    unavailable_reason: Optional[str] = document_field(
        ActionSchemaKey.UNAVAILABLE_REASON, default=None
    )
    """
    Why a step cannot be this action, or None for an available one.
    """

    saved_as: List[str] = document_field(ActionSchemaKey.SAVED_AS, default_factory=list)
    """
    The names plans of format 1.1 and earlier saved the action under, the planner's
    class names then, so such plans are translated to :attr:`name` when read.
    """

    def field_named(self, name: str) -> Optional[ActionField]:
        """
        :param name: A keyword argument.
        :return: The field of that name, or None.
        """
        for candidate in self.fields:
            if candidate.name == name:
                return candidate
        return None


class FailedActionModuleKey(StrEnum):
    """
    The keys of an action module that cannot be imported.
    """

    MODULE = "module"
    """
    The module's name.
    """

    ERROR = "error"
    """
    What importing it raised.
    """


@dataclass(kw_only=True)
class FailedActionModule(JsonDocument):
    """
    A module of the actions package that cannot be imported, so its actions are not
    offered.
    """

    module: str = document_field(FailedActionModuleKey.MODULE)
    """
    The module's name.
    """

    error: str = document_field(FailedActionModuleKey.ERROR)
    """
    The class and message of the error importing it raised.
    """


class ActionCatalogKey(StrEnum):
    """
    The keys of the discovered actions.
    """

    ACTIONS = "actions"
    """
    The action schemas.
    """

    FAILED_MODULES = "failedModules"
    """
    The action modules that cannot be imported.
    """


@dataclass(kw_only=True)
class ActionCatalog(JsonDocument):
    """
    The native actions found in the CRAM workspace's actions package.
    """

    actions: List[ActionSchema] = document_field(
        ActionCatalogKey.ACTIONS, default_factory=list
    )
    """
    The action schemas, core actions first, then by label.
    """

    failed_modules: List[FailedActionModule] = document_field(
        ActionCatalogKey.FAILED_MODULES, default_factory=list
    )
    """
    The modules that cannot be imported, sorted by name.
    """


# %% catalog


class RobotModelKey(StrEnum):
    """
    The keys of one robot model of the catalog.
    """

    NAME = "name"
    """
    The robot's identifier.
    """

    LABEL = "label"
    """
    The robot's display name.
    """

    MODULE = "module"
    """
    The module defining the class.
    """

    SAVED_AS = "savedAs"
    """
    The names plans saved the robot under before the protocol named it.
    """

    CHOICES = "choices"
    """
    The members of the enumerations whose choices depend on the robot.
    """


@dataclass(kw_only=True)
class RobotModel(JsonDocument):
    """
    A robot annotation of the CRAM workspace and what its parts let it do.
    """

    name: str = document_field(RobotModelKey.NAME)
    """
    The robot's identifier, which plans name it by and which stays when the planner
    renames its annotation class, such as ``pr2``.
    """

    label: str = document_field(RobotModelKey.LABEL, default="")
    """
    The robot's display name, such as ``PR2``; empty in catalogs written before, which
    show the identifier.
    """

    module: str = document_field(RobotModelKey.MODULE)
    """
    The module defining the annotation class.
    """

    saved_as: List[str] = document_field(RobotModelKey.SAVED_AS, default_factory=list)
    """
    The names plans of format 1.1 and earlier saved the robot under, the class names of
    its annotation then, so such plans are translated to :attr:`name` when read.
    """

    choices: Dict[str, List[str]] = document_field(
        RobotModelKey.CHOICES, default_factory=dict
    )
    """
    The names of the members the robot's parts allow, by the class name of their
    enumeration: the arm choices of its arms, the torso states when it has a torso and
    none otherwise. An enumeration not listed offers all its members.
    """


class ObjectModelKey(StrEnum):
    """
    The keys of one object model of the catalog.
    """

    IDENTIFIER = "id"
    """
    The model's file name.
    """

    NAME = "name"
    """
    The model's display name.
    """


@dataclass(kw_only=True)
class ObjectModel(JsonDocument):
    """
    A mesh a plan can place copies of as free objects.
    """

    identifier: str = document_field(ObjectModelKey.IDENTIFIER)
    """
    The mesh's file name, served below :attr:`PlanBuilderRoute.OBJECT_FILES`.
    """

    name: str = document_field(ObjectModelKey.NAME)
    """
    The model's display name, the file name without its suffix.
    """


class PlanBuilderCatalogKey(StrEnum):
    """
    The keys of the plan builder's catalog.
    """

    ROBOTS = "robots"
    """
    The robot models.
    """

    ENVIRONMENTS = "environments"
    """
    The environment bundles.
    """

    OBJECTS = "objects"
    """
    The object models.
    """

    SURFACE_TYPES = "surfaceTypes"
    """
    The classes of surfaces objects can be put on or in.
    """

    ACTIONS = "actions"
    """
    The native actions a step can be.
    """

    FAILED_ACTION_MODULES = "failedActionModules"
    """
    The action modules that cannot be imported.
    """

    CONSTRAINT_RULES = "constraintRules"
    """
    The wordings constraints understand.
    """

    PLANS = "plans"
    """
    The saved plans.
    """

    LIMITS = "limits"
    """
    The bounds plans and demos stay within.
    """

    LIVE_URL = "liveUrl"
    """
    Where started demos publish their world.
    """

    MISSING = "missing"
    """
    The CRAM modules that cannot be found.
    """


@dataclass(kw_only=True)
class PlanBuilderCatalog(JsonDocument):
    """
    What the plan builder offers.
    """

    live_url: str = document_field(PlanBuilderCatalogKey.LIVE_URL)
    """
    The base URL of the live publisher started demos publish on.
    """

    robots: List[RobotModel] = document_field(
        PlanBuilderCatalogKey.ROBOTS, default_factory=list
    )
    """
    The robot annotations of the CRAM workspace, sorted by name; empty without CRAM.
    """

    environments: List[SceneIndexEntry] = document_field(
        PlanBuilderCatalogKey.ENVIRONMENTS, default_factory=list
    )
    """
    The bundles without a robot, as the viewer's scene index lists them.
    """

    objects: List[ObjectModel] = document_field(
        PlanBuilderCatalogKey.OBJECTS, default_factory=list
    )
    """
    The object meshes of the CRAM workspace, sorted by identifier.
    """

    surface_types: List[str] = document_field(
        PlanBuilderCatalogKey.SURFACE_TYPES, default_factory=list
    )
    """
    The class names of the native annotations with a supporting surface, sorted.
    """

    actions: List[ActionSchema] = document_field(
        PlanBuilderCatalogKey.ACTIONS, default_factory=list
    )
    """
    The native actions of the CRAM workspace, available or not; empty without CRAM.
    """

    failed_action_modules: List[FailedActionModule] = document_field(
        PlanBuilderCatalogKey.FAILED_ACTION_MODULES, default_factory=list
    )
    """
    The modules of the actions package that cannot be imported.
    """

    constraint_rules: List[ConstraintRule] = document_field(
        PlanBuilderCatalogKey.CONSTRAINT_RULES, default_factory=list
    )
    """
    The rules constraints are compiled with, in the order they are tried.
    """

    plans: List[PlanSummary] = document_field(
        PlanBuilderCatalogKey.PLANS, default_factory=list
    )
    """
    The saved plans.
    """

    limits: PlanBuilderLimits = document_field(
        PlanBuilderCatalogKey.LIMITS, default_factory=PlanBuilderLimits
    )
    """
    The bounds plans and demos stay within.
    """

    missing: List[str] = document_field(
        PlanBuilderCatalogKey.MISSING, default_factory=list
    )
    """
    The CRAM modules that cannot be found; robots, objects, surfaces and actions stay
    empty while one is missing.
    """


# %% demos


class DemoDocumentKey(StrEnum):
    """
    The keys of what a generated demo runs.
    """

    PLAN = "plan"
    """
    The plan.
    """

    ENVIRONMENT_DIRECTORY = "environmentDirectory"
    """
    The environment bundle's directory.
    """


@dataclass(kw_only=True)
class DemoDocument(JsonDocument):
    """
    What a generated demo runs: the plan, with where its environment bundle was found
    when the demo was generated, so the demo finds it in any scenes directory.
    """

    plan: PlanDocument = document_field(DemoDocumentKey.PLAN)
    """
    The plan.
    """

    environment_directory: Optional[str] = document_field(
        DemoDocumentKey.ENVIRONMENT_DIRECTORY, default=None
    )
    """
    The absolute path of the plan's environment bundle, or None for an empty floor.
    """


class DemoOption(StrEnum):
    """
    The options of a generated demo's command line, which the plan builder starts it
    with and cramera-bridge's plan demo command reads.
    """

    STAGE = "--stage"
    """
    Only build the world and publish it until the process is stopped.
    """

    PORT = "--port"
    """
    The port the world is published on.
    """

    LIFELINE = "--lifeline"
    """
    End when standard input closes, which happens when the process that started the demo
    ends.
    """


class DemoSourceKey(StrEnum):
    """
    The keys of a generated demo.
    """

    FILE_NAME = "fileName"
    """
    The demo's file name.
    """

    SOURCE = "source"
    """
    The demo's Python source.
    """


@dataclass(kw_only=True)
class DemoSource(JsonDocument):
    """
    The demo generated from a plan.
    """

    file_name: str = document_field(DemoSourceKey.FILE_NAME)
    """
    The file name the demo is written under.
    """

    source: str = document_field(DemoSourceKey.SOURCE)
    """
    The demo's Python source.
    """


class SavedDemoKey(StrEnum):
    """
    The keys of a written demo.
    """

    PATH = "path"
    """
    Where the demo was written.
    """

    COMMAND = "command"
    """
    How to run it.
    """


@dataclass(kw_only=True)
class SavedDemo(JsonDocument):
    """
    A demo written into the output directory.
    """

    path: str = document_field(SavedDemoKey.PATH)
    """
    The demo file's absolute path.
    """

    command: str = document_field(SavedDemoKey.COMMAND)
    """
    The command that runs the demo.
    """


# %% runs


class RunMode(StrEnum):
    """
    What a started demo does.
    """

    STAGE = "stage"
    """
    Builds the world and publishes it until it is stopped, so objects can be placed in
    it.
    """

    PERFORM = "perform"
    """
    Performs the selected robot's plan, records it and saves the recording.
    """


class RunState(StrEnum):
    """
    The state of the demo process.
    """

    IDLE = "idle"
    """
    No demo was started.
    """

    RUNNING = "running"
    """
    The demo runs.
    """

    FINISHED = "finished"
    """
    The demo ended on its own with success.
    """

    FAILED = "failed"
    """
    The demo ended on its own with an error.
    """

    STOPPED = "stopped"
    """
    The demo was stopped.
    """


class RunRequestKey(StrEnum):
    """
    The keys of a request starting a demo.
    """

    PLAN = "plan"
    """
    The plan whose demo starts.
    """

    MODE = "mode"
    """
    What the demo does.
    """


@dataclass(kw_only=True)
class RunRequest(JsonDocument):
    """
    Starts the demo of a plan, replacing a demo that still runs.
    """

    plan: PlanDocument = document_field(RunRequestKey.PLAN)
    """
    The plan whose demo is generated and started.
    """

    mode: RunMode = document_field(RunRequestKey.MODE, default=RunMode.STAGE)
    """
    What the demo does.
    """


class RunStatusKey(StrEnum):
    """
    The keys of the demo process's state.
    """

    STATE = "state"
    """
    The process's state.
    """

    MODE = "mode"
    """
    What the demo does.
    """

    RETURN_CODE = "returnCode"
    """
    The process's exit status.
    """

    LOG = "log"
    """
    The newest output.
    """

    PATH = "path"
    """
    The demo file.
    """


@dataclass(kw_only=True)
class RunStatus(JsonDocument):
    """
    The state of the demo process and its newest output.
    """

    state: RunState = document_field(RunStatusKey.STATE, default=RunState.IDLE)
    """
    The process's state.
    """

    mode: Optional[RunMode] = document_field(RunStatusKey.MODE, default=None)
    """
    What the demo does, or None before one was started.
    """

    return_code: Optional[int] = document_field(RunStatusKey.RETURN_CODE, default=None)
    """
    The process's exit status, or None while it runs.
    """

    log: str = document_field(RunStatusKey.LOG, default="")
    """
    The newest output of the process, at most
    :attr:`PlanBuilderLimits.maximum_log_bytes` of it.
    """

    path: Optional[str] = document_field(RunStatusKey.PATH, default=None)
    """
    The started demo file.
    """


# %% plans naming the planner's classes


@dataclass(frozen=True)
class SavedNames:
    """
    The identifiers of the actions and robot models by the names plans of
    :data:`CLASS_NAME_FORMAT_VERSION` saved them under, as a catalog lists them.
    """

    actions: Dict[str, str]
    """
    The action identifiers by saved name.
    """

    robots: Dict[str, str]
    """
    The robot identifiers by saved name.
    """

    @classmethod
    def of_catalog(cls, catalog: PlanBuilderCatalog) -> Self:
        """
        :param catalog: A plan builder catalog.
        :return: The names its actions and robots were saved under.
        """
        return cls(
            actions={
                saved: schema.name
                for schema in catalog.actions
                for saved in schema.saved_as
            },
            robots={
                saved: robot.name
                for robot in catalog.robots
                for saved in robot.saved_as
            },
        )

    def translated(self, plan: PlanDocument) -> PlanDocument:
        """
        :param plan: A plan.
        :return: The plan with every saved action and robot model name replaced by its
            identifier and carrying :data:`PLAN_FORMAT_VERSION`; a plan of that version
            unchanged. A name the catalog does not list stays, for the catalog check to
            report.
        """
        if plan.format_version >= PLAN_FORMAT_VERSION:
            return plan
        return replace(
            plan,
            format_version=PLAN_FORMAT_VERSION,
            robots=[
                replace(
                    robot,
                    model=self.robots.get(robot.model, robot.model),
                    steps=[
                        replace(step, action=self.actions.get(step.action, step.action))
                        for step in robot.steps
                    ],
                )
                for robot in plan.robots
            ],
        )
