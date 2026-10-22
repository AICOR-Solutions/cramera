"""
The plan builder's documents: the plans a person composes from robot actions, the
catalog of robots, environments and objects a plan uses, the constraints written in
plain language, and the demos generated from a plan and run as child processes.

A plan names its robots, its objects and their poses, and each robot's steps; the
generated demo builds the world and the native actions from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.geometry import Pose
from cramera_protocol.live_messages import ConstraintMonitorType, MonitorSpecification
from cramera_protocol.version import CURRENT_VERSION, ProtocolVersion

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


# %% steps


class StepKind(StrEnum):
    """
    The robot actions a plan step can be.
    """

    PARK_ARMS = "park_arms"
    """
    Moves arms into their park posture.
    """

    MOVE_TORSO = "move_torso"
    """
    Moves the torso to one of its named heights.
    """

    NAVIGATE = "navigate"
    """
    Drives the mobile base to a pose.
    """

    TRANSPORT = "transport"
    """
    Picks an object up and places it at a target, driving where needed.
    """

    PICK_UP = "pick_up"
    """
    Picks an object up from where the robot stands.
    """

    PLACE = "place"
    """
    Places a held object at a target from where the robot stands.
    """


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


class StepSwitch(StrEnum):
    """
    The switches of a native action a constraint turns on; each value is the action's
    keyword argument.
    """

    LOOK_AT_OPERATION_SITE = "look_at_operation_site"
    """
    The transport looks at the object before picking it up and at the target before
    placing it.
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

    switch: Optional[StepSwitch] = document_field(
        StepConstraintKey.SWITCH, default=None
    )
    """
    The switch of the step's action the constraint turns on, or None.
    """


class ConstraintTextKey(StrEnum):
    """
    The keys of a request compiling a constraint.
    """

    TEXT = "text"
    """
    The constraint as it was written.
    """

    STEP_KIND = "stepKind"
    """
    The kind of the step the constraint is attached to.
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

    step_kind: Optional[StepKind] = document_field(
        ConstraintTextKey.STEP_KIND, default=None
    )
    """
    The kind of the step it is attached to, or None for a constraint not attached yet.
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

    SWITCHES = "switches"
    """
    The switch the constraint turns on, by the kind of step it is attached to.
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

    switches: Dict[str, StepSwitch] = document_field(
        ConstraintRuleKey.SWITCHES, default_factory=dict
    )
    """
    The switch the constraint turns on, by the :class:`StepKind` value of the step it is
    attached to.
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

    KIND = "kind"
    """
    The action the step is.
    """

    ARM = "arm"
    """
    The arm the step uses.
    """

    TORSO_STATE = "torsoState"
    """
    The torso height the step moves to.
    """

    OBJECT = "object"
    """
    The object the step acts on.
    """

    TARGET = "target"
    """
    Where the step drives to or puts the object down.
    """

    PLACEMENT = "placement"
    """
    How the step names where it puts the object down.
    """

    SURFACE_TYPE = "surfaceType"
    """
    The class of the surface the object is put on or in.
    """

    SURFACE_NAME = "surfaceName"
    """
    The surface the object is put on or in.
    """

    CONSTRAINTS = "constraints"
    """
    The constraints attached to the step.
    """


@dataclass(kw_only=True)
class PlanStep(JsonDocument):
    """
    One action of a robot's plan with its parameters; which parameters apply depends on
    :attr:`kind`.
    """

    identifier: str = document_field(PlanStepKey.IDENTIFIER)
    """
    The step's identity within the plan.
    """

    kind: StepKind = document_field(PlanStepKey.KIND)
    """
    The action the step is.
    """

    arm: Optional[str] = document_field(PlanStepKey.ARM, default=None)
    """
    The name of the native arm choice, as the catalog lists it for the robot.
    """

    torso_state: Optional[str] = document_field(PlanStepKey.TORSO_STATE, default=None)
    """
    The name of the native torso state, as the catalog lists it.
    """

    object_identifier: Optional[str] = document_field(PlanStepKey.OBJECT, default=None)
    """
    The identifier of the plan's object the step acts on.
    """

    target: Optional[Pose] = document_field(PlanStepKey.TARGET, default=None)
    """
    The pose in world coordinates the base drives to or the object is put down at.
    """

    placement: PlacementMode = document_field(
        PlanStepKey.PLACEMENT, default=PlacementMode.POSE
    )
    """
    How the step names where it puts the object down.
    """

    surface_type: Optional[str] = document_field(PlanStepKey.SURFACE_TYPE, default=None)
    """
    The class name of the surface annotation the object is put on or in.
    """

    surface_name: Optional[str] = document_field(PlanStepKey.SURFACE_NAME, default=None)
    """
    The name of one surface annotation, or None for any surface of the type.
    """

    constraints: List[StepConstraint] = document_field(
        PlanStepKey.CONSTRAINTS, default_factory=list
    )
    """
    The constraints attached to the step.
    """


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
    The class name of the robot's annotation, as the catalog lists it.
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
    The protocol version the plan was written with.
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
        PlanKey.FORMAT_VERSION, default=CURRENT_VERSION
    )
    """
    The protocol version the plan was written with.
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


# %% catalog


class RobotModelKey(StrEnum):
    """
    The keys of one robot model of the catalog.
    """

    NAME = "name"
    """
    The annotation class.
    """

    MODULE = "module"
    """
    The module defining the class.
    """

    STEPS = "steps"
    """
    The step kinds the robot's parts allow.
    """

    ARMS = "arms"
    """
    The arm choices the robot's parts allow.
    """


@dataclass(kw_only=True)
class RobotModel(JsonDocument):
    """
    A robot annotation of the CRAM workspace and what its parts let it do.
    """

    name: str = document_field(RobotModelKey.NAME)
    """
    The class name of the robot's annotation.
    """

    module: str = document_field(RobotModelKey.MODULE)
    """
    The module defining the annotation class.
    """

    steps: List[StepKind] = document_field(RobotModelKey.STEPS, default_factory=list)
    """
    The step kinds the robot's parts allow, in the order :class:`StepKind` lists them.
    """

    arms: List[str] = document_field(RobotModelKey.ARMS, default_factory=list)
    """
    The names of the native arm choices the robot's arms allow.
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

    TORSO_STATES = "torsoStates"
    """
    The torso heights.
    """

    SURFACE_TYPES = "surfaceTypes"
    """
    The classes of surfaces objects can be put on or in.
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

    torso_states: List[str] = document_field(
        PlanBuilderCatalogKey.TORSO_STATES, default_factory=list
    )
    """
    The names of the native torso states.
    """

    surface_types: List[str] = document_field(
        PlanBuilderCatalogKey.SURFACE_TYPES, default_factory=list
    )
    """
    The class names of the native annotations with a supporting surface, sorted.
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
    The CRAM modules that cannot be found; robots, objects, torso states and surfaces
    stay empty while one is missing.
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
