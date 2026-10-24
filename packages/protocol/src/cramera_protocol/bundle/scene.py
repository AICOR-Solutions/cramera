"""
The scene description, ``scene.json``: which models, robot and objects a bundle shows,
how to look at them, and what the recorded run did.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional, Self

from cramera_protocol.document import (
    JsonDocument,
    ValueLocation,
    document_field,
    extension_field,
)
from cramera_protocol.geometry import Bounds, FloorRectangle, Pose, Vector3
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion

# %% models


class ModelKey(StrEnum):
    """
    The keys of one kinematic model of a scene.
    """

    NAME = "name"
    """
    The model's name.
    """

    URDF = "urdf"
    """
    The model's URDF file, relative to the bundle.
    """

    PREFIX = "prefix"
    """
    The prefix of the model's link and joint names in the trajectory.
    """

    ROBOT = "robot"
    """
    Whether the model is a robot.
    """

    LINKS = "links"
    """
    How many links the model has.
    """

    MOVABLE_JOINTS = "movableJoints"
    """
    The names of the model's joints that move.
    """

    PRESERVE_MATERIALS = "preserveMaterials"
    """
    Whether the viewer keeps the authored materials of the model's meshes.
    """

    POSED_JOINTS = "posedJoints"
    """
    The joints whose poses are streamed instead of joint values.
    """

    IDENTIFIER = "identifier"
    """
    The identity of one robot instance among several of the same model.
    """

    POSE = "pose"
    """
    The model's root pose.
    """


@dataclass(kw_only=True)
class ModelDescription(JsonDocument):
    """
    One kinematic model, given as a URDF file, that a scene shows.
    """

    name: str = document_field(ModelKey.NAME)
    """
    The model's name.
    """

    urdf: str = document_field(ModelKey.URDF)
    """
    The model's URDF file, relative to the bundle.
    """

    prefix: str = document_field(ModelKey.PREFIX)
    """
    The prefix of the model's link and joint names in the trajectory.
    """

    robot: bool = document_field(ModelKey.ROBOT)
    """
    Whether the model is a robot.
    """

    links: Optional[int] = document_field(ModelKey.LINKS, default=None)
    """
    How many links the model has, when the writer counted them.
    """

    movable_joints: List[str] = document_field(
        ModelKey.MOVABLE_JOINTS, default_factory=list
    )
    """
    The names of the model's joints that move.
    """

    preserve_materials: Optional[bool] = document_field(
        ModelKey.PRESERVE_MATERIALS, default=None
    )
    """
    Whether the viewer keeps the authored materials of the model's meshes.
    """

    posed_joints: List[str] = document_field(
        ModelKey.POSED_JOINTS, default_factory=list
    )
    """
    The joints written as floating joints, for connections a URDF has no type for; their
    poses are streamed instead of joint values.
    """

    identifier: Optional[str] = document_field(ModelKey.IDENTIFIER, default=None)
    """
    The identity of one robot instance among several of the same model.
    """

    pose: Optional[Pose] = document_field(ModelKey.POSE, default=None)
    """
    The model's root pose, when the scene places it.
    """


# %% robot


class RobotKey(StrEnum):
    """
    The keys of a scene's robot.
    """

    NAME = "name"
    """
    The robot's name.
    """

    PREFIX = "prefix"
    """
    The prefix of the robot's link and joint names.
    """

    BASE_BODY = "baseBody"
    """
    The robot's root link.
    """

    PARTS = "parts"
    """
    The robot's semantic parts mapped to their links.
    """

    PART_ANNOTATIONS = "partAnnotations"
    """
    The robot's semantic parts with their roles.
    """

    IDENTIFIER = "identifier"
    """
    The identity of the robot instance.
    """

    LABEL = "label"
    """
    The robot's display name.
    """


class PartKey(StrEnum):
    """
    The keys of one semantic part of a robot.
    """

    NAME = "name"
    """
    The part's name.
    """

    ROLE = "role"
    """
    What the part is for.
    """

    SIDE = "side"
    """
    Which side of the robot the part is on.
    """

    LINKS = "links"
    """
    The links that belong to the part.
    """

    ATTACHED_TO = "attachedTo"
    """
    The part this part hangs from.
    """


class PartRole(StrEnum):
    """
    What a semantic part of a robot is for.
    """

    ARM = "arm"
    """
    A kinematic chain that positions an end effector.
    """

    END_EFFECTOR = "end_effector"
    """
    A gripper or hand at the end of an arm.
    """


class PartSide(StrEnum):
    """
    Which side of the robot a part is on.
    """

    LEFT = "left"
    """
    The robot's left side.
    """

    RIGHT = "right"
    """
    The robot's right side.
    """


@dataclass(kw_only=True)
class RobotPart(JsonDocument):
    """
    One semantic part of a robot, as its annotation in the semantic world names it.
    """

    name: str = document_field(PartKey.NAME)
    """
    The part's annotation name.
    """

    role: PartRole = document_field(PartKey.ROLE)
    """
    What the part is for.
    """

    side: Optional[PartSide] = document_field(PartKey.SIDE, default=None)
    """
    Which side the part is on, or None for a robot with one arm.
    """

    links: List[str] = document_field(PartKey.LINKS, default_factory=list)
    """
    The links that belong to the part.
    """

    attached_to: Optional[str] = document_field(PartKey.ATTACHED_TO, default=None)
    """
    The name of the part this part hangs from, if any.
    """


@dataclass(kw_only=True)
class RobotDescription(JsonDocument):
    """
    The robot of a scene.
    """

    name: str = document_field(RobotKey.NAME)
    """
    The robot's name.
    """

    prefix: str = document_field(RobotKey.PREFIX)
    """
    The prefix of the robot's link and joint names.
    """

    base_body: str = document_field(RobotKey.BASE_BODY)
    """
    The robot's root link.
    """

    parts: Dict[str, List[str]] = document_field(RobotKey.PARTS, default_factory=dict)
    """
    The robot's semantic parts mapped to their links.
    """

    part_annotations: List[RobotPart] = document_field(
        RobotKey.PART_ANNOTATIONS, default_factory=list
    )
    """
    The robot's semantic parts with their roles.
    """

    identifier: Optional[str] = document_field(RobotKey.IDENTIFIER, default=None)
    """
    The identity of the robot instance, matching :attr:`ModelDescription.identifier`.
    """

    label: Optional[str] = document_field(RobotKey.LABEL, default=None)
    """
    The robot's display name.
    """


# %% objects


class ObjectKey(StrEnum):
    """
    The keys of one free object of a scene.
    """

    IDENTIFIER = "id"
    """
    The object's identifier.
    """

    KEY = "key"
    """
    The object's key in the trajectory's object poses.
    """

    SPAWN = "spawn"
    """
    The object's pose before the run.
    """

    COLOR = "color"
    """
    The object's colour as a CSS hexadecimal colour.
    """

    HEIGHT = "height"
    """
    The object's height in metres.
    """

    MESH = "mesh"
    """
    The object's mesh file, relative to the bundle.
    """

    MATERIAL_LIBRARY = "mtl"
    """
    The material library of an OBJ mesh, relative to the bundle.
    """

    BOX = "box"
    """
    The size of an object drawn as a box.
    """

    URDF = "urdf"
    """
    The object's URDF file, relative to the bundle.
    """

    PRESERVE_MATERIALS = "preserveMaterials"
    """
    Whether the viewer keeps the authored materials of the object's mesh.
    """


@dataclass(kw_only=True)
class ObjectDescription(JsonDocument):
    """
    One object that moves freely in a scene: drawn from a mesh, or as a box.
    """

    identifier: str = document_field(ObjectKey.IDENTIFIER)
    """
    The object's identifier.
    """

    key: str = document_field(ObjectKey.KEY)
    """
    The object's key in the trajectory's object poses.
    """

    spawn: Pose = document_field(ObjectKey.SPAWN)
    """
    The object's pose before the run.
    """

    color: Optional[str] = document_field(ObjectKey.COLOR, default=None)
    """
    The object's colour as a CSS hexadecimal colour, when its shapes have one.
    """

    height: Optional[float] = document_field(ObjectKey.HEIGHT, default=None)
    """
    The object's height in metres.
    """

    mesh: Optional[str] = document_field(ObjectKey.MESH, default=None)
    """
    The object's mesh file, relative to the bundle.
    """

    material_library: Optional[str] = document_field(
        ObjectKey.MATERIAL_LIBRARY, default=None
    )
    """
    The material library of an OBJ mesh, relative to the bundle.
    """

    box: Optional[Vector3] = document_field(ObjectKey.BOX, default=None)
    """
    The size of an object drawn as a box, in metres.
    """

    urdf: Optional[str] = document_field(ObjectKey.URDF, default=None)
    """
    The object's URDF file, relative to the bundle, for an object with collision
    geometry or joints of its own.
    """

    preserve_materials: Optional[bool] = document_field(
        ObjectKey.PRESERVE_MATERIALS, default=None
    )
    """
    Whether the viewer keeps the authored materials of the object's mesh.
    """


# %% recorded run


class SegmentKey(StrEnum):
    """
    The keys of one step of a recorded run on the timeline.
    """

    STEP = "step"
    """
    The step's label.
    """

    ACTION = "action"
    """
    The actions the step performed.
    """

    ARM = "arm"
    """
    The arm the step used.
    """

    START = "start"
    """
    The step's first frame.
    """

    END = "end"
    """
    The step's last frame.
    """

    PICKS = "picks"
    """
    The object the step picked up.
    """

    ATTACH = "attach"
    """
    The frame at which the picked object was attached.
    """

    DETACH = "detach"
    """
    The frame at which the picked object was released.
    """

    PLACE = "place"
    """
    Where the step placed the object.
    """


@dataclass(kw_only=True)
class Segment(JsonDocument):
    """
    One step of a recorded run and the frames it spans.
    """

    step: str = document_field(SegmentKey.STEP)
    """
    The step's label.
    """

    start: int = document_field(SegmentKey.START)
    """
    The step's first frame.
    """

    end: int = document_field(SegmentKey.END)
    """
    The step's last frame.
    """

    action: Optional[str] = document_field(SegmentKey.ACTION, default=None)
    """
    The names of the actions the step performed, as the recorder labelled them.
    """

    arm: Optional[str] = document_field(SegmentKey.ARM, default=None)
    """
    The arm the step used, as the recorder labelled it.
    """

    picks: Optional[str] = document_field(SegmentKey.PICKS, default=None)
    """
    The key of the object the step picked up.
    """

    attach: Optional[int] = document_field(SegmentKey.ATTACH, default=None)
    """
    The frame at which the picked object was attached.
    """

    detach: Optional[int] = document_field(SegmentKey.DETACH, default=None)
    """
    The frame at which the picked object was released.
    """

    place: Optional[Vector3] = document_field(SegmentKey.PLACE, default=None)
    """
    Where the step placed the object.
    """


class PlanNodeKey(StrEnum):
    """
    The keys of one node of an executed plan.
    """

    KIND = "kind"
    """
    The class name of the plan node.
    """

    LABEL = "label"
    """
    The node's description.
    """

    STATUS = "status"
    """
    The node's life-cycle state when the run ended.
    """

    CHILDREN = "children"
    """
    The node's children.
    """

    TARGET = "target"
    """
    The object or place the node acted on.
    """

    ARM = "arm"
    """
    The arm the node used.
    """

    IDENTIFIER = "id"
    """
    The node's identity within the recording.
    """

    PARENT = "parent"
    """
    The identity of the node's parent.
    """

    START = "start"
    """
    The first frame the node ran in.
    """

    END = "end"
    """
    The last frame the node ran in.
    """

    ROBOT = "robot"
    """
    The robot that performed the plan, on the plan's root.
    """

    PARAMETERS = "parameters"
    """
    Every field of the node's designator by name, each as the recorder wrote it.
    """

    CONSTRAINTS = "constraints"
    """
    The constraints attached to the node while it ran.
    """

    PERCEIVED = "perceived"
    """
    The objects a perception step reported.
    """

    REASON = "reason"
    """
    Why a failed node failed.
    """

    IMAGES = "images"
    """
    What a perception step saw.
    """


class PlanConstraintKey(StrEnum):
    """
    The keys of one constraint attached to a node of an executed plan.
    """

    TEXT = "text"
    """
    The constraint as it was written.
    """

    MONITOR = "monitor"
    """
    The monitor class the constraint became.
    """

    OBSERVATION = "observation"
    """
    What the monitor observed last.
    """


@dataclass(kw_only=True)
class PlanConstraint(JsonDocument):
    """
    A constraint attached to a node of an executed plan, with its last observation.
    """

    text: str = document_field(PlanConstraintKey.TEXT)
    """
    The constraint as it was written.
    """

    monitor: str = document_field(PlanConstraintKey.MONITOR)
    """
    The class name of the monitor the constraint became.
    """

    observation: Optional[str] = document_field(
        PlanConstraintKey.OBSERVATION, default=None
    )
    """
    The name of the monitor's last observation value, or None when it never ticked.
    """


class PerceptionImageSource(StrEnum):
    """
    Where an image of what a perception step saw comes from.
    """

    CAMERA = "camera"
    """
    Rendered from the world model through the robot's camera, as in simulation.
    """

    ROBOKUDO = "robokudo"
    """
    Published by a RoboKudo pipeline while it answered the step.
    """


class PerceptionImageKey(StrEnum):
    """
    The keys of a :class:`PerceptionImage`.
    """

    TITLE = "title"
    """
    What the image shows.
    """

    SOURCE = "source"
    """
    Where the image comes from.
    """

    FILE = "file"
    """
    Where the image is.
    """


@dataclass(kw_only=True)
class PerceptionImage(JsonDocument):
    """
    One image of what a perception step saw.
    """

    title: str = document_field(PerceptionImageKey.TITLE)
    """
    What the image shows, for people reading it, such as ``Camera`` or the RoboKudo
    annotator that drew it.
    """

    source: str = document_field(PerceptionImageKey.SOURCE)
    """
    A :class:`PerceptionImageSource` value.
    """

    file: str = document_field(PerceptionImageKey.FILE)
    """
    In a bundle, the PNG file's path in the bundle; in a live plan, the image's key for
    :attr:`~cramera_protocol.live.LiveRoute.PERCEPTION_IMAGE`.
    """


class PlanNodeKind(StrEnum):
    """
    The kinds of plan node a reader of a recorded plan tells apart; the bridge
    translates the planner's node classes into them.
    """

    ACTION = "action"
    """
    A node performing an action designator: one step of the plan.
    """

    MOTION = "motion"
    """
    A node performing a motion designator, part of an action.
    """

    CONDITION = "condition"
    """
    A node checking a condition before or after an action.
    """

    SEQUENCE = "sequence"
    """
    A node performing its children one after another, also repeated or until one
    succeeds.
    """

    PARALLEL = "parallel"
    """
    A node performing its children at once, also until one succeeds.
    """

    MONITOR = "monitor"
    """
    A node watching a condition to pause or cancel its children.
    """

    CODE = "code"
    """
    A node running a piece of code.
    """

    ATTACHMENT = "attachment"
    """
    A node attaching a held object to another body or releasing it.
    """

    UNDERSPECIFIED = "underspecified"
    """
    A node whose action is left to be chosen while the plan runs.
    """

    OTHER = "other"
    """
    Any other node.
    """

    @classmethod
    def of_recorded(cls, kind: str) -> PlanNodeKind:
        """
        :param kind: A kind as a recording names it: a member's value, or the class
            name earlier recordings stored.
        :return: The kind; a class name that is no :class:`LegacyPlanNodeKind` is
            :attr:`OTHER`.
        """
        if kind in {member.value for member in cls}:
            return cls(kind)
        if kind in {member.value for member in LegacyPlanNodeKind}:
            return cls[LegacyPlanNodeKind(kind).name]
        return cls.OTHER


class LegacyPlanNodeKind(StrEnum):
    """
    The planner's class names recordings stored as plan node kinds before the protocol
    named them; frozen, read only to translate such recordings, each member named like
    the :class:`PlanNodeKind` it stands for.
    """

    ACTION = "ActionNode"
    """
    An action node.
    """

    MOTION = "MotionNode"
    """
    A motion node.
    """

    CONDITION = "ConditionNode"
    """
    A condition node.
    """

    SEQUENCE = "SequentialNode"
    """
    A sequential node.
    """

    PARALLEL = "ParallelNode"
    """
    A parallel node.
    """

    ATTACHMENT = "ReAttachNode"
    """
    A node re-attaching an object.
    """


@dataclass(kw_only=True)
class PlanNode(JsonDocument):
    """
    One node of an executed plan, as the plan's recorder saw it.
    """

    kind: PlanNodeKind = document_field(PlanNodeKey.KIND)
    """
    What kind of node it is.
    """

    label: str = document_field(PlanNodeKey.LABEL)
    """
    The node's description.
    """

    status: str = document_field(PlanNodeKey.STATUS)
    """
    The name of the node's native life-cycle value when the run ended.
    """

    children: List[PlanNode] = document_field(
        PlanNodeKey.CHILDREN, default_factory=list
    )
    """
    The node's children, in execution order.
    """

    target: Optional[str] = document_field(PlanNodeKey.TARGET, default=None)
    """
    The object or place the node acted on.
    """

    arm: Optional[str] = document_field(PlanNodeKey.ARM, default=None)
    """
    The arm the node used.
    """

    identifier: Optional[str] = document_field(PlanNodeKey.IDENTIFIER, default=None)
    """
    The node's identity within the recording.
    """

    parent: Optional[str] = document_field(PlanNodeKey.PARENT, default=None)
    """
    The identity of the node's parent, or None for a root.
    """

    start: Optional[int] = document_field(PlanNodeKey.START, default=None)
    """
    The first frame the node or one of its descendants was the deepest running action
    in, or None when it never ran within the recorded frames.
    """

    end: Optional[int] = document_field(PlanNodeKey.END, default=None)
    """
    The last frame the node or one of its descendants was the deepest running action in,
    or None when it never ran within the recorded frames.
    """

    robot: Optional[str] = document_field(PlanNodeKey.ROBOT, default=None)
    """
    The display name of the robot that performed the plan, on the plan's root; None on
    every other node and for a plan recorded without its robot.
    """

    parameters: Dict[str, str] = document_field(
        PlanNodeKey.PARAMETERS, default_factory=dict
    )
    """
    Every field of the node's designator by name, rendered as the recorder wrote it:

    an enumeration member by its name, an object by its key, a pose by its position;
    empty for a node without a designator and in recordings written before.
    """

    constraints: List[PlanConstraint] = document_field(
        PlanNodeKey.CONSTRAINTS, default_factory=list
    )
    """
    The constraints attached to the node while it ran, with their last observations.
    """

    perceived: Optional[List[str]] = document_field(PlanNodeKey.PERCEIVED, default=None)
    """
    For a perception step: the objects it reported, by their keys, else their names,
    empty when it reported none; None for every other node and in recordings written
    before.
    """

    reason: Optional[str] = document_field(PlanNodeKey.REASON, default=None)
    """
    Why the node failed, as coraplex worded it; None for a node that did not fail.
    """

    images: Optional[List[PerceptionImage]] = document_field(
        PlanNodeKey.IMAGES, default=None
    )
    """
    For a perception step: the images of what it saw, empty when none were taken; None
    for every other node and in recordings written before.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    Further keys a recorder wrote; readers of this version do not interpret them.
    """

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read a node, translating the class name earlier recordings stored as its kind;
        see :meth:`JsonDocument.read_at`.
        """
        if isinstance(data, dict) and isinstance(data.get(PlanNodeKey.KIND), str):
            data = {
                **data,
                PlanNodeKey.KIND: PlanNodeKind.of_recorded(data[PlanNodeKey.KIND]),
            }
        return super().read_at(data, location)


class PlannedActionKey(StrEnum):
    """
    The keys of one action of a recorded plan, as the earliest recordings listed them.
    """

    ACTION = "action"
    """
    The action's name.
    """

    ARM = "arm"
    """
    The arm the action used.
    """

    TARGET = "target"
    """
    The object or place the action worked on.
    """


@dataclass(kw_only=True)
class PlannedAction(JsonDocument):
    """
    One action of a recorded plan in the flat list the earliest recordings wrote.
    """

    action: str = document_field(PlannedActionKey.ACTION)
    """
    The action's name.
    """

    arm: Optional[str] = document_field(PlannedActionKey.ARM, default=None)
    """
    The arm the action used.
    """

    target: Optional[str] = document_field(PlannedActionKey.TARGET, default=None)
    """
    The object or place the action worked on.
    """


class DetectedEventKey(StrEnum):
    """
    The keys of one event a detector saw during a run.
    """

    NAME = "name"
    """
    The event's name.
    """

    EVENT_TYPE = "eventType"
    """
    The event's class name.
    """

    TIMESTAMP = "timestamp"
    """
    When the event happened.
    """

    TRACKED_OBJECT = "trackedObject"
    """
    The object the event is about.
    """

    WITH_OBJECT = "withObject"
    """
    The second object of a relation event.
    """


@dataclass(kw_only=True)
class DetectedEvent(JsonDocument):
    """
    One event a detector saw during a recorded run.
    """

    name: str = document_field(DetectedEventKey.NAME)
    """
    The event's name.
    """

    event_type: str = document_field(DetectedEventKey.EVENT_TYPE)
    """
    The event's class name in the detector package.
    """

    timestamp: str = document_field(DetectedEventKey.TIMESTAMP)
    """
    When the event happened, as an ISO 8601 date and time.
    """

    tracked_object: Optional[str] = document_field(
        DetectedEventKey.TRACKED_OBJECT, default=None
    )
    """
    The object the event is about.
    """

    with_object: Optional[str] = document_field(
        DetectedEventKey.WITH_OBJECT, default=None
    )
    """
    The second object of a relation event.
    """


# %% placing objects by hand


class PlaceTargetKey(StrEnum):
    """
    The keys of the area where a viewer user may place the picked object.
    """

    POSITION = "position"
    """
    The default place position on the floor plane.
    """

    LEGACY_POSITION = "pos"
    """
    The key the earliest recordings used for :attr:`POSITION`.
    """

    HEIGHT = "z"
    """
    The height of the placing surface.
    """

    BOUNDS = "bounds"
    """
    The area the place position may be moved within.
    """


@dataclass(kw_only=True)
class PlaceTarget(JsonDocument):
    """
    Where the recorded run placed its object, and how far a viewer user may move it.
    """

    position: List[float] = document_field(
        PlaceTargetKey.POSITION, legacy_keys=(PlaceTargetKey.LEGACY_POSITION,)
    )
    """
    The default place position, as x and y in metres.
    """

    height: float = document_field(PlaceTargetKey.HEIGHT)
    """
    The height of the placing surface in metres.
    """

    bounds: FloorRectangle = document_field(PlaceTargetKey.BOUNDS)
    """
    The area the place position may be moved within.
    """


# %% presentation


class CameraKey(StrEnum):
    """
    The keys of a scene's initial view.
    """

    POSITION = "position"
    """
    Where the camera stands.
    """

    TARGET = "target"
    """
    What the camera looks at.
    """

    FIELD_OF_VIEW = "fov"
    """
    The vertical field of view in degrees.
    """

    FAR = "far"
    """
    The far clipping distance in metres.
    """


@dataclass(kw_only=True)
class Camera(JsonDocument):
    """
    The view a scene opens with.
    """

    position: Vector3 = document_field(CameraKey.POSITION)
    """
    Where the camera stands.
    """

    target: Vector3 = document_field(CameraKey.TARGET)
    """
    What the camera looks at.
    """

    field_of_view: Optional[float] = document_field(
        CameraKey.FIELD_OF_VIEW, default=None
    )
    """
    The vertical field of view in degrees, or None for the viewer's own.
    """

    far: Optional[float] = document_field(CameraKey.FAR, default=None)
    """
    The far clipping distance in metres, or None for the viewer's own.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    Camera settings written by plugins.
    """


class RenderingKey(StrEnum):
    """
    The keys of a scene's renderer settings.
    """

    EXPOSURE = "exposure"
    """
    The tone-mapping exposure.
    """

    AMBIENT_OCCLUSION = "ambientOcclusion"
    """
    Whether ambient occlusion is drawn.
    """

    GROUND_PLANE = "groundPlane"
    """
    Whether the viewer draws its ground plane.
    """

    SHADOW_BOUNDS = "shadowBounds"
    """
    The box the key light's shadow covers.
    """

    ENVIRONMENT = "environment"
    """
    The scene's lights.
    """


@dataclass(kw_only=True)
class Rendering(JsonDocument):
    """
    How a scene asks to be drawn.
    """

    exposure: Optional[float] = document_field(RenderingKey.EXPOSURE, default=None)
    """
    The tone-mapping exposure, or None for the viewer's own.
    """

    ambient_occlusion: Optional[bool] = document_field(
        RenderingKey.AMBIENT_OCCLUSION, default=None
    )
    """
    Whether ambient occlusion is drawn, or None for the viewer's choice.
    """

    ground_plane: Optional[bool] = document_field(
        RenderingKey.GROUND_PLANE, default=None
    )
    """
    Whether the viewer draws its ground plane, or None for the viewer's choice.
    """

    shadow_bounds: Optional[Bounds] = document_field(
        RenderingKey.SHADOW_BOUNDS, default=None
    )
    """
    The box the key light's shadow covers.
    """

    environment: Optional[str] = document_field(RenderingKey.ENVIRONMENT, default=None)
    """
    The lighting file of the scene, relative to the bundle.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    Renderer settings written by plugins.
    """


# %% provenance


class SourceKey(StrEnum):
    """
    The keys of where a converted scene came from.
    """

    USD = "usd"
    """
    The converted stage.
    """

    CONVERTER = "converter"
    """
    The version of the converter.
    """

    LAYERS = "layers"
    """
    The digest of the stage's layers.
    """


@dataclass(kw_only=True)
class SceneSource(JsonDocument):
    """
    The stage a converted scene was made from.
    """

    usd: str = document_field(SourceKey.USD)
    """
    The path of the converted stage.
    """

    converter: str = document_field(SourceKey.CONVERTER)
    """
    The version of the converter that wrote the bundle.
    """

    layers: str = document_field(SourceKey.LAYERS)
    """
    The SHA-256 digest of the stage's layers.
    """


# %% scene


class SceneKey(StrEnum):
    """
    The keys of ``scene.json``.
    """

    NAME = "name"
    """
    The bundle's name.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The protocol version the bundle was written with.
    """

    FRAMES_PER_SECOND = "framesPerSecond"
    """
    How many trajectory frames make one second.
    """

    LEGACY_FRAMES_PER_SECOND = "fps"
    """
    The key the earliest recordings used for :attr:`FRAMES_PER_SECOND`.
    """

    TRAJECTORY = "trajectory"
    """
    The trajectory file.
    """

    STATECHARTS = "statecharts"
    """
    The statecharts file.
    """

    MODELS = "models"
    """
    The kinematic models.
    """

    ROBOT = "robot"
    """
    The robot.
    """

    OBJECTS = "objects"
    """
    The free objects.
    """

    SEGMENTS = "segments"
    """
    The steps of the recorded run.
    """

    PLAN_TREES = "planTrees"
    """
    The executed plans.
    """

    ACTIONS = "actions"
    """
    The flat action list of the earliest recordings.
    """

    DETECTED_EVENTS = "detectedEvents"
    """
    The events detectors saw.
    """

    MISSING_ASSETS = "missingAssets"
    """
    The files the writer could not include.
    """

    PLACE_TARGET = "placeTarget"
    """
    Where the picked object may be placed by hand.
    """

    DRAG_BOUNDS = "dragBounds"
    """
    The area objects may be dragged within.
    """

    TASK = "task"
    """
    The task the bundle shows.
    """

    ROBOT_NAME = "robotName"
    """
    The robot's display name.
    """

    ENVIRONMENT_NAME = "environmentName"
    """
    The environment's display name.
    """

    CAMERA = "camera"
    """
    The initial view.
    """

    RENDERING = "rendering"
    """
    The renderer settings.
    """

    BACKGROUND = "background"
    """
    The background image.
    """

    SOURCE = "source"
    """
    Where a converted scene came from.
    """

    BUNDLE_SIGNATURE = "bundleSignature"
    """
    The identity of the world a live bundle was made from.
    """

    WORLD_BOUND = "worldBound"
    """
    Whether a live bundle follows a running world.
    """


@dataclass(kw_only=True)
class SceneDescription(JsonDocument):
    """
    The content of ``scene.json``.
    """

    name: str = document_field(SceneKey.NAME)
    """
    The bundle's name, which is also its directory name.
    """

    format_version: ProtocolVersion = document_field(
        SceneKey.FORMAT_VERSION, default=UNVERSIONED
    )
    """
    The protocol version the bundle was written with.
    """

    frames_per_second: Optional[float] = document_field(
        SceneKey.FRAMES_PER_SECOND,
        legacy_keys=(SceneKey.LEGACY_FRAMES_PER_SECOND,),
        default=None,
    )
    """
    How many trajectory frames make one second.
    """

    trajectory: Optional[str] = document_field(SceneKey.TRAJECTORY, default=None)
    """
    The trajectory file, relative to the bundle.
    """

    statecharts: Optional[str] = document_field(SceneKey.STATECHARTS, default=None)
    """
    The statecharts file, relative to the bundle.
    """

    models: List[ModelDescription] = document_field(
        SceneKey.MODELS, default_factory=list
    )
    """
    The kinematic models the scene shows.
    """

    robot: Optional[RobotDescription] = document_field(SceneKey.ROBOT, default=None)
    """
    The scene's robot, or None for a scene without one.
    """

    objects: List[ObjectDescription] = document_field(
        SceneKey.OBJECTS, default_factory=list
    )
    """
    The objects that move freely.
    """

    segments: List[Segment] = document_field(SceneKey.SEGMENTS, default_factory=list)
    """
    The steps of the recorded run.
    """

    plan_trees: List[PlanNode] = document_field(
        SceneKey.PLAN_TREES, default_factory=list
    )
    """
    The roots of the executed plans.
    """

    actions: List[PlannedAction] = document_field(
        SceneKey.ACTIONS, default_factory=list
    )
    """
    The flat action list of the earliest recordings.
    """

    detected_events: List[DetectedEvent] = document_field(
        SceneKey.DETECTED_EVENTS, default_factory=list
    )
    """
    The events detectors saw during the run.
    """

    missing_assets: List[str] = document_field(
        SceneKey.MISSING_ASSETS, default_factory=list
    )
    """
    The files the writer could not include.
    """

    place_target: Optional[PlaceTarget] = document_field(
        SceneKey.PLACE_TARGET, default=None
    )
    """
    Where the picked object may be placed by hand.
    """

    drag_bounds: Optional[FloorRectangle] = document_field(
        SceneKey.DRAG_BOUNDS, default=None
    )
    """
    The area objects may be dragged within.
    """

    task: Optional[str] = document_field(SceneKey.TASK, default=None)
    """
    The task the bundle shows, as the scene picker labels it.
    """

    robot_name: Optional[str] = document_field(SceneKey.ROBOT_NAME, default=None)
    """
    The robot's display name.
    """

    environment_name: Optional[str] = document_field(
        SceneKey.ENVIRONMENT_NAME, default=None
    )
    """
    The environment's display name; bundles of the same environment share it.
    """

    camera: Optional[Camera] = document_field(SceneKey.CAMERA, default=None)
    """
    The initial view.
    """

    rendering: Optional[Rendering] = document_field(SceneKey.RENDERING, default=None)
    """
    The renderer settings.
    """

    background: Optional[str] = document_field(SceneKey.BACKGROUND, default=None)
    """
    The background image, relative to the bundle.
    """

    source: Optional[SceneSource] = document_field(SceneKey.SOURCE, default=None)
    """
    Where a converted scene came from.
    """

    bundle_signature: Optional[str] = document_field(
        SceneKey.BUNDLE_SIGNATURE, default=None
    )
    """
    The identity of the world a live bundle was made from.
    """

    world_bound: Optional[bool] = document_field(SceneKey.WORLD_BOUND, default=None)
    """
    Whether a live bundle follows a running world.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    Scene content written by plugins.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)
