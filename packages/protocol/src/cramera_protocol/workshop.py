"""
The woodworking workshop: the description a workshop bundle carries in ``scene.json``,
and the commands and measured state of its contact simulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, FrozenSet, List, Mapping, Optional

from cramera_protocol.document import JsonDocument, document_field, extension_field
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.geometry import Pose, Vector3

SMALLEST_QUATERNION_NORM = 1e-6
"""
The smallest length a commanded orientation quaternion may have to be normalized.
"""

# %% routes


class WorkshopRoute(StrEnum):
    """
    The routes of the workshop plugin, below ``/api/plugins/workshop/``.
    """

    STATE = "state"
    """
    The measured state of the contact simulation.
    """

    COMMAND = "command"
    """
    Applies one :class:`WorkshopCommand` and answers the state after it.
    """


# %% scene description


class WorkshopSceneKey(StrEnum):
    """
    The keys a workshop bundle adds to ``scene.json``.
    """

    WORKSHOP = "workshop"
    """
    The :class:`WorkshopDescription`.
    """

    ASSET_RIGHTS = "assetRights"
    """
    The :class:`AssetRights` of the bundle's original assets.
    """


class WorkshopPartKind(StrEnum):
    """
    The kinds of independently movable workshop bodies.
    """

    SCREW = "screw"
    """
    A wood screw, its origin at the tip and its shaft along local z.
    """

    NAIL = "nail"
    """
    A nail, its origin at the tip and its shaft along local z.
    """

    STORAGE_BOX = "storage_box"
    """
    A storage box on the shelf.
    """

    ASSEMBLY = "assembly"
    """
    The wooden workpiece with the pilot hole.
    """

    DRIVER = "driver"
    """
    The screwdriver.
    """


class WorkshopView(StrEnum):
    """
    The named camera views of the workshop.
    """

    OVERVIEW = "overview"
    """
    The whole workshop.
    """

    BENCH = "bench"
    """
    The workbench.
    """

    DRAWERS = "drawers"
    """
    The drawer cabinet.
    """


class DrawerKey(StrEnum):
    """
    The keys of one drawer of the workshop.
    """

    IDENTIFIER = "id"
    """
    The drawer's identifier.
    """

    LABEL = "label"
    """
    The drawer's display name.
    """

    JOINT = "joint"
    """
    The drawer's prismatic joint.
    """

    LINK = "link"
    """
    The drawer's link.
    """

    HANDLE = "handle"
    """
    The drawer's handle frame.
    """

    ORIGIN = "origin"
    """
    The drawer joint's origin.
    """

    OPEN = "open"
    """
    The joint position of the open drawer.
    """


@dataclass(kw_only=True)
class DrawerDescription(JsonDocument):
    """
    One drawer of the cabinet.
    """

    identifier: str = document_field(DrawerKey.IDENTIFIER)
    """
    The drawer's identifier.
    """

    label: str = document_field(DrawerKey.LABEL)
    """
    The drawer's display name.
    """

    joint: str = document_field(DrawerKey.JOINT)
    """
    The name of the drawer's prismatic joint in the environment model.
    """

    link: str = document_field(DrawerKey.LINK)
    """
    The name of the drawer's link.
    """

    handle: str = document_field(DrawerKey.HANDLE)
    """
    The name of the drawer's handle frame.
    """

    origin: Vector3 = document_field(DrawerKey.ORIGIN)
    """
    Where the drawer's joint sits in the environment, in metres.
    """

    open: float = document_field(DrawerKey.OPEN)
    """
    The joint position of the open drawer, in metres.
    """


class WorkshopBodyKey(StrEnum):
    """
    The keys of the movable bodies the workshop describes.
    """

    KEY = "key"
    """
    The body's key, which is also its object key in the scene.
    """

    LABEL = "label"
    """
    The body's display name.
    """

    KIND = "kind"
    """
    A :class:`WorkshopPartKind` value.
    """

    HOME = "home"
    """
    The body's pose before anything moved it.
    """

    BENCH_POSE = "benchPose"
    """
    Where a box is set down on the workbench.
    """

    HANDLE = "handle"
    """
    The frame of a box's carry handle.
    """


@dataclass(kw_only=True)
class PartDescription(JsonDocument):
    """
    One loose fastener.
    """

    key: str = document_field(WorkshopBodyKey.KEY)
    """
    The fastener's object key.
    """

    label: str = document_field(WorkshopBodyKey.LABEL)
    """
    The fastener's display name.
    """

    kind: WorkshopPartKind = document_field(WorkshopBodyKey.KIND)
    """
    Whether it is a screw or a nail.
    """

    home: Pose = document_field(WorkshopBodyKey.HOME)
    """
    The fastener's pose in its box before anything moved it.
    """


@dataclass(kw_only=True)
class BoxDescription(JsonDocument):
    """
    One box that holds fasteners or stands on the shelf.
    """

    key: str = document_field(WorkshopBodyKey.KEY)
    """
    The box's object key.
    """

    label: str = document_field(WorkshopBodyKey.LABEL)
    """
    The box's display name.
    """

    kind: Optional[WorkshopPartKind] = document_field(
        WorkshopBodyKey.KIND, default=None
    )
    """
    The kind of a storage box; None for a box of fasteners.
    """

    home: Pose = document_field(WorkshopBodyKey.HOME)
    """
    The box's pose before anything moved it.
    """

    bench_pose: Optional[Pose] = document_field(
        WorkshopBodyKey.BENCH_POSE, default=None
    )
    """
    Where the box is set down on the workbench, for a box a robot fetches.
    """

    handle: str = document_field(WorkshopBodyKey.HANDLE)
    """
    The frame of the box's carry handle.
    """


class AssemblyKey(StrEnum):
    """
    The keys of the workpiece with the pilot hole.
    """

    POSE = "pose"
    """
    The workpiece's pose in its jig.
    """

    SOCKET_POSE = "socketPose"
    """
    The pilot hole's pose in the world.
    """

    LOCAL_SOCKET = "localSocket"
    """
    The pilot hole's pose in the workpiece.
    """

    SOCKET_FRAME = "socketFrame"
    """
    The pilot hole's frame.
    """

    LOCAL_MOUTH = "localMouth"
    """
    The pilot hole's entrance in the workpiece.
    """

    MAXIMUM_DEPTH = "maximumDepth"
    """
    How deep a screw tip goes before its head seats.
    """


@dataclass(kw_only=True)
class AssemblyDescription(JsonDocument):
    """
    The wooden workpiece a screw is driven into.
    """

    key: str = document_field(WorkshopBodyKey.KEY)
    """
    The workpiece's object key.
    """

    label: str = document_field(WorkshopBodyKey.LABEL)
    """
    The workpiece's display name.
    """

    kind: WorkshopPartKind = document_field(WorkshopBodyKey.KIND)
    """
    :attr:`WorkshopPartKind.ASSEMBLY`.
    """

    home: Pose = document_field(WorkshopBodyKey.HOME)
    """
    The workpiece's pose before anything moved it.
    """

    pose: Pose = document_field(AssemblyKey.POSE)
    """
    The workpiece's pose in its jig.
    """

    socket_pose: Pose = document_field(AssemblyKey.SOCKET_POSE)
    """
    The pilot hole's pose in the world.
    """

    local_socket: Pose = document_field(AssemblyKey.LOCAL_SOCKET)
    """
    The pilot hole's pose in the workpiece.
    """

    socket_frame: str = document_field(AssemblyKey.SOCKET_FRAME)
    """
    The name of the pilot hole's frame.
    """

    local_mouth: Vector3 = document_field(AssemblyKey.LOCAL_MOUTH)
    """
    The pilot hole's entrance in the workpiece, on its local z axis, in metres.
    """

    maximum_depth: float = document_field(AssemblyKey.MAXIMUM_DEPTH)
    """
    How far below the entrance a screw tip goes before the head seats, in metres.
    """


class DriverKey(StrEnum):
    """
    The keys of the screwdriver.
    """

    BIT_TIP = "bitTip"
    """
    The blade's tip in the driver.
    """

    AXIS = "axis"
    """
    The driving axis in the driver.
    """

    GRASP = "grasp"
    """
    Where a hand holds the driver.
    """

    BLADE_SIZE = "bladeSize"
    """
    The blade's size.
    """

    BLADE_DIRECTION = "bladeDirection"
    """
    The blade's width direction.
    """

    BIT_FRAME = "bitFrame"
    """
    The blade tip's frame.
    """

    GRASP_FRAME = "graspFrame"
    """
    The grasp frame.
    """


@dataclass(kw_only=True)
class DriverDescription(JsonDocument):
    """
    The screwdriver.
    """

    key: str = document_field(WorkshopBodyKey.KEY)
    """
    The driver's object key.
    """

    label: str = document_field(WorkshopBodyKey.LABEL)
    """
    The driver's display name.
    """

    kind: WorkshopPartKind = document_field(WorkshopBodyKey.KIND)
    """
    :attr:`WorkshopPartKind.DRIVER`.
    """

    home: Pose = document_field(WorkshopBodyKey.HOME)
    """
    The driver's pose in its cradle.
    """

    bit_tip: Vector3 = document_field(DriverKey.BIT_TIP)
    """
    The blade's tip in the driver's frame, in metres.
    """

    axis: Vector3 = document_field(DriverKey.AXIS)
    """
    The direction that drives a screw in, in the driver's frame.
    """

    grasp: Vector3 = document_field(DriverKey.GRASP)
    """
    Where a hand holds the driver, in the driver's frame, in metres.
    """

    blade_size: Vector3 = document_field(DriverKey.BLADE_SIZE)
    """
    The blade's size, in metres.
    """

    blade_direction: Vector3 = document_field(DriverKey.BLADE_DIRECTION)
    """
    The blade's width direction in the driver's frame.
    """

    bit_frame: str = document_field(DriverKey.BIT_FRAME)
    """
    The name of the blade tip's frame.
    """

    grasp_frame: str = document_field(DriverKey.GRASP_FRAME)
    """
    The name of the grasp frame.
    """


class ScrewKey(StrEnum):
    """
    The keys of the screws' shared dimensions.
    """

    HEAD_TOP = "headTop"
    """
    The head's top above the tip.
    """

    SLOT_SIZE = "slotSize"
    """
    The head slot's size.
    """

    THREAD_PITCH = "threadPitch"
    """
    The thread's advance per turn.
    """


@dataclass(kw_only=True)
class ScrewDescription(JsonDocument):
    """
    The dimensions every screw of the workshop shares.
    """

    head_top: float = document_field(ScrewKey.HEAD_TOP)
    """
    The head's top above the tip, in metres.
    """

    slot_size: Vector3 = document_field(ScrewKey.SLOT_SIZE)
    """
    The head slot's length, width and depth, in metres.
    """

    thread_pitch: float = document_field(ScrewKey.THREAD_PITCH)
    """
    The thread's advance per turn, in metres.
    """


class WorkbenchBoundsKey(StrEnum):
    """
    The keys of the area manipulated bodies stay in.
    """

    MINIMUM = "min"
    """
    The corner with the smallest x and y.
    """

    MAXIMUM = "max"
    """
    The corner with the largest x and y.
    """


@dataclass(kw_only=True)
class WorkbenchBounds(JsonDocument):
    """
    The floor area manipulated bodies stay above.
    """

    minimum: List[float] = document_field(WorkbenchBoundsKey.MINIMUM)
    """
    The smallest x and y, in metres.
    """

    maximum: List[float] = document_field(WorkbenchBoundsKey.MAXIMUM)
    """
    The largest x and y, in metres.
    """


class CameraViewKey(StrEnum):
    """
    The keys of a named camera view.
    """

    POSITION = "position"
    """
    Where the camera stands.
    """

    TARGET = "target"
    """
    What the camera looks at.
    """


@dataclass(kw_only=True)
class CameraView(JsonDocument):
    """
    A camera position and the point it looks at.
    """

    position: Vector3 = document_field(CameraViewKey.POSITION)
    """
    Where the camera stands, in metres.
    """

    target: Vector3 = document_field(CameraViewKey.TARGET)
    """
    What the camera looks at, in metres.
    """


class WorkshopKey(StrEnum):
    """
    The keys of the workshop description.
    """

    DRAWERS = "drawers"
    """
    The drawers.
    """

    PARTS = "parts"
    """
    The loose fasteners.
    """

    BINS = "bins"
    """
    The boxes.
    """

    ASSEMBLY = "assembly"
    """
    The workpiece.
    """

    DRIVER = "driver"
    """
    The screwdriver.
    """

    SCREW = "screw"
    """
    The screws' dimensions.
    """

    LIFT_HEIGHT = "liftHeight"
    """
    The height bodies are carried at.
    """

    BOUNDS = "bounds"
    """
    The area bodies stay above.
    """

    CAMERAS = "cameras"
    """
    The named camera views.
    """

    DEMO_SCENE = "demoScene"
    """
    The bundle of the recorded robot demo.
    """


@dataclass(kw_only=True)
class WorkshopDescription(JsonDocument):
    """
    What a workshop bundle describes besides its models and objects.
    """

    drawers: List[DrawerDescription] = document_field(WorkshopKey.DRAWERS)
    """
    The drawers of the cabinet.
    """

    parts: List[PartDescription] = document_field(WorkshopKey.PARTS)
    """
    The loose fasteners.
    """

    bins: List[BoxDescription] = document_field(WorkshopKey.BINS)
    """
    The boxes.
    """

    assembly: AssemblyDescription = document_field(WorkshopKey.ASSEMBLY)
    """
    The workpiece with the pilot hole.
    """

    driver: DriverDescription = document_field(WorkshopKey.DRIVER)
    """
    The screwdriver.
    """

    screw: ScrewDescription = document_field(WorkshopKey.SCREW)
    """
    The screws' shared dimensions.
    """

    lift_height: float = document_field(WorkshopKey.LIFT_HEIGHT)
    """
    The height bodies are carried at above the workbench, in metres.
    """

    bounds: WorkbenchBounds = document_field(WorkshopKey.BOUNDS)
    """
    The floor area manipulated bodies stay above.
    """

    cameras: Dict[str, CameraView] = document_field(WorkshopKey.CAMERAS)
    """
    The camera views by :class:`WorkshopView` value.
    """

    demo_scene: Optional[str] = document_field(WorkshopKey.DEMO_SCENE, default=None)
    """
    The name of the bundle recording the robot demo in this workshop, if any.
    """

    def screws(self) -> List[str]:
        """
        :return: The object keys of the screws, in the description's order.
        """
        return [part.key for part in self.parts if part.kind is WorkshopPartKind.SCREW]

    def movable_keys(self) -> List[str]:
        """
        :return: The object keys of every body the description names as movable.
        """
        return (
            [part.key for part in self.parts]
            + [box.key for box in self.bins]
            + [self.assembly.key, self.driver.key]
        )

    @classmethod
    def of_scene(cls, extensions: Mapping[str, Any]) -> Optional[WorkshopDescription]:
        """
        :param extensions: The plugin content of a scene description.
        :return: The workshop the scene describes, or None for another scene.
        """
        data = extensions.get(WorkshopSceneKey.WORKSHOP)
        return None if data is None else cls.from_json(data)


class AssetRightsKey(StrEnum):
    """
    The keys of the rights of a bundle's original assets.
    """

    PRINCIPAL_AUTHOR = "principalAuthor"
    """
    Who designed the assets.
    """

    INSTITUTION = "institution"
    """
    The institution the assets were made at.
    """

    COPYRIGHT = "copyright"
    """
    The copyright notice.
    """

    LICENSE = "license"
    """
    The licence identifier.
    """

    PERMISSION_NOTICE = "permissionNotice"
    """
    What reuse needs.
    """

    PRIOR_LICENSE_NOTICE = "priorLicenseNotice"
    """
    Which rights remain unaffected.
    """

    LICENSE_FILE = "licenseFile"
    """
    The licence file, relative to the bundle.
    """

    NOTICE_FILE = "noticeFile"
    """
    The notice file, relative to the bundle.
    """


@dataclass(kw_only=True)
class AssetRights(JsonDocument):
    """
    Who made a bundle's original assets and on which terms they may be reused.
    """

    principal_author: str = document_field(AssetRightsKey.PRINCIPAL_AUTHOR)
    """
    Who designed the assets.
    """

    institution: str = document_field(AssetRightsKey.INSTITUTION)
    """
    The institution the assets were made at.
    """

    copyright: str = document_field(AssetRightsKey.COPYRIGHT)
    """
    The copyright notice.
    """

    license: str = document_field(AssetRightsKey.LICENSE)
    """
    The licence identifier, such as ``LicenseRef-AICOR-Workshop-Assets``.
    """

    permission_notice: str = document_field(AssetRightsKey.PERMISSION_NOTICE)
    """
    What reuse, modification and redistribution need.
    """

    prior_license_notice: str = document_field(AssetRightsKey.PRIOR_LICENSE_NOTICE)
    """
    Which existing rights and permissions remain unaffected.
    """

    license_file: str = document_field(AssetRightsKey.LICENSE_FILE)
    """
    The licence file, relative to the bundle.
    """

    notice_file: str = document_field(AssetRightsKey.NOTICE_FILE)
    """
    The notice file, relative to the bundle.
    """

    @classmethod
    def of_scene(cls, extensions: Mapping[str, Any]) -> Optional[AssetRights]:
        """
        :param extensions: The plugin content of a scene description.
        :return: The rights the scene names, or None for a scene without them.
        """
        data = extensions.get(WorkshopSceneKey.ASSET_RIGHTS)
        return None if data is None else cls.from_json(data)


class WorkshopSemanticsKey(StrEnum):
    """
    The keys of a workshop bundle's ``semantics.json``.
    """

    HANDLES = "handles"
    """
    The frames a hand grasps.
    """


@dataclass(kw_only=True)
class WorkshopSemantics(JsonDocument):
    """
    The content of a workshop bundle's ``semantics.json``.
    """

    handles: List[str] = document_field(WorkshopSemanticsKey.HANDLES)
    """
    The names of the links a hand grasps: drawer and box handles.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The units, the up axis, the pilot hole and a copy of the workshop description, which
    building a world does not read.
    """


# %% commands


class WorkshopAction(StrEnum):
    """
    The operations of the workshop's contact simulation.
    """

    START = "start"
    """
    Builds the simulation if needed and lets time pass.
    """

    PAUSE = "pause"
    """
    Releases any held body and stops time.
    """

    RESET = "reset"
    """
    Puts every body back where it started.
    """

    GRAB = "grab"
    """
    Holds one body with a force-limited spring.
    """

    MOVE = "move"
    """
    Moves the held body's spring target.
    """

    RELEASE = "release"
    """
    Lets go of the held body.
    """

    DRAWER = "drawer"
    """
    Sets a drawer motor's target.
    """

    DRIVE = "drive"
    """
    Turns the held screwdriver.
    """


class DriveDirection(StrEnum):
    """
    Which way the screwdriver turns.
    """

    FORWARD = "forward"
    """
    Drives the screw in.
    """

    REVERSE = "reverse"
    """
    Withdraws the screw.
    """

    STOP = "stop"
    """
    Holds the driver still.
    """


class WorkshopCommandKey(StrEnum):
    """
    The keys of a workshop command.
    """

    ACTION = "action"
    """
    A :class:`WorkshopAction` value.
    """

    OBJECT = "object"
    """
    The body grabbed or moved.
    """

    POSE = "pose"
    """
    The held body's new spring target.
    """

    JOINT = "joint"
    """
    The drawer joint.
    """

    POSITION = "position"
    """
    The drawer joint's target.
    """

    DIRECTION = "direction"
    """
    A :class:`DriveDirection` value.
    """


COMMAND_ARGUMENTS: Mapping[WorkshopAction, FrozenSet[WorkshopCommandKey]] = {
    WorkshopAction.GRAB: frozenset({WorkshopCommandKey.OBJECT}),
    WorkshopAction.MOVE: frozenset(
        {WorkshopCommandKey.OBJECT, WorkshopCommandKey.POSE}
    ),
    WorkshopAction.DRAWER: frozenset(
        {WorkshopCommandKey.JOINT, WorkshopCommandKey.POSITION}
    ),
    WorkshopAction.DRIVE: frozenset({WorkshopCommandKey.DIRECTION}),
}
"""
The keys each action takes besides :attr:`WorkshopCommandKey.ACTION`; an action not
listed takes none.
"""


@dataclass
class InvalidWorkshopCommand(ProtocolError):
    """
    A workshop command whose keys do not fit its action, or whose numbers are not
    finite.
    """

    action: WorkshopAction
    """
    The command's action.
    """

    reason: str
    """
    What does not fit.
    """

    def message(self) -> str:
        return f"The workshop command {self.action.value!r} is invalid: {self.reason}"


@dataclass(kw_only=True)
class WorkshopCommand(JsonDocument):
    """
    One operation of the contact simulation, with exactly the keys its action takes.
    """

    action: WorkshopAction = document_field(WorkshopCommandKey.ACTION)
    """
    The operation.
    """

    object_key: Optional[str] = document_field(WorkshopCommandKey.OBJECT, default=None)
    """
    The object key of the body to grab or move.
    """

    pose: Optional[Pose] = document_field(WorkshopCommandKey.POSE, default=None)
    """
    The held body's new spring target; its quaternion needs not be normalized.
    """

    joint: Optional[str] = document_field(WorkshopCommandKey.JOINT, default=None)
    """
    The drawer joint whose motor target changes.
    """

    position: Optional[float] = document_field(
        WorkshopCommandKey.POSITION, default=None
    )
    """
    The drawer joint's target, in metres.
    """

    direction: Optional[DriveDirection] = document_field(
        WorkshopCommandKey.DIRECTION, default=None
    )
    """
    Which way the held screwdriver turns.
    """

    def __post_init__(self) -> None:
        given = {
            key
            for key, value in (
                (WorkshopCommandKey.OBJECT, self.object_key),
                (WorkshopCommandKey.POSE, self.pose),
                (WorkshopCommandKey.JOINT, self.joint),
                (WorkshopCommandKey.POSITION, self.position),
                (WorkshopCommandKey.DIRECTION, self.direction),
            )
            if value is not None
        }
        expected = COMMAND_ARGUMENTS.get(self.action, frozenset())
        if given != expected:
            raise InvalidWorkshopCommand(
                self.action,
                f"it takes {sorted(expected)} and was given {sorted(given)}",
            )
        if self.object_key == "":
            raise InvalidWorkshopCommand(self.action, "the object key is empty")
        if self.pose is not None and not self.has_finite_pose():
            raise InvalidWorkshopCommand(
                self.action, "the pose needs finite numbers and a nonzero quaternion"
            )
        if self.position is not None and not math.isfinite(self.position):
            raise InvalidWorkshopCommand(self.action, "the position is not finite")

    def has_finite_pose(self) -> bool:
        """
        :return: Whether the pose's numbers are finite and its quaternion has a length
            that can be normalized.
        """
        values = self.pose.to_json()
        return all(math.isfinite(value) for value in values) and (
            math.hypot(*values[3:]) >= SMALLEST_QUATERNION_NORM
        )


# %% measured state


class ThreadState(StrEnum):
    """
    The phases of the ideal thread between a screw and the pilot hole.
    """

    FREE = "free"
    """
    No screw sits in the pilot hole.
    """

    SEATED = "seated"
    """
    A screw sits at the pilot hole's entrance.
    """

    DRIVING = "driving"
    """
    The driver turns the seated screw.
    """

    STOPPED = "stopped"
    """
    The screw is partly driven and the driver rests.
    """

    LIMIT = "limit"
    """
    The screw reached the end of its travel.
    """


class ContactKey(StrEnum):
    """
    The keys of one measured contact.
    """

    BODY_A = "bodyA"
    """
    The first body.
    """

    BODY_B = "bodyB"
    """
    The second body.
    """

    POSITION = "position"
    """
    Where the bodies touch.
    """

    NORMAL = "normal"
    """
    The contact normal.
    """

    FORCE = "force"
    """
    The normal force.
    """

    DISTANCE = "distance"
    """
    The signed distance between the bodies.
    """


@dataclass(kw_only=True)
class MeasuredContact(JsonDocument):
    """
    A contact the solver resolved, with its measured force.
    """

    body_a: str = document_field(ContactKey.BODY_A)
    """
    The name of the first body.
    """

    body_b: str = document_field(ContactKey.BODY_B)
    """
    The name of the second body.
    """

    position: Vector3 = document_field(ContactKey.POSITION)
    """
    Where the bodies touch, in metres.
    """

    normal: Vector3 = document_field(ContactKey.NORMAL)
    """
    The contact normal, from the first body to the second.
    """

    force: float = document_field(ContactKey.FORCE)
    """
    The normal force, in newtons.
    """

    distance: float = document_field(ContactKey.DISTANCE)
    """
    The signed distance between the bodies, negative when they overlap, in metres.
    """


class ThreadKey(StrEnum):
    """
    The keys of the ideal thread's state.
    """

    ENGAGED = "engaged"
    """
    Whether the driver's blade is engaged in the screw's slot.
    """

    SCREW = "screw"
    """
    The screw the thread is about.
    """

    DRIVER = "driver"
    """
    The screwdriver.
    """

    DEPTH = "depth"
    """
    The measured insertion depth.
    """

    TURNS = "turns"
    """
    The measured driver turns since capture.
    """

    PITCH = "pitch"
    """
    The thread's advance per turn.
    """

    STATE = "state"
    """
    A :class:`ThreadState` value.
    """

    DRIVER_TARGET_POSE = "driverTargetPose"
    """
    The driver pose that seats the blade in the screw's slot.
    """

    SOCKET_POSE = "socketPose"
    """
    The pilot hole's entrance.
    """

    SCREW_TARGET_POSE = "screwTargetPose"
    """
    The screw pose just above the pilot hole's entrance.
    """


@dataclass(kw_only=True)
class ThreadObservation(JsonDocument):
    """
    The measured state of the ideal thread.
    """

    engaged: bool = document_field(ThreadKey.ENGAGED)
    """
    Whether the driver's blade is engaged in the seated screw's slot.
    """

    screw: str = document_field(ThreadKey.SCREW)
    """
    The seated screw, else the held screw, else the first screw.
    """

    driver: str = document_field(ThreadKey.DRIVER)
    """
    The screwdriver's object key.
    """

    depth: float = document_field(ThreadKey.DEPTH)
    """
    How far the seated screw's tip is below the entrance, in metres; 0 without one.
    """

    turns: float = document_field(ThreadKey.TURNS)
    """
    The measured driver turns since the screw was captured.
    """

    pitch: float = document_field(ThreadKey.PITCH)
    """
    The thread's advance per turn, in metres.
    """

    state: ThreadState = document_field(ThreadKey.STATE)
    """
    The thread's phase.
    """

    driver_target_pose: Pose = document_field(ThreadKey.DRIVER_TARGET_POSE)
    """
    The driver pose that seats its blade in :attr:`screw`'s slot.
    """

    socket_pose: Pose = document_field(ThreadKey.SOCKET_POSE)
    """
    The pilot hole's entrance, its z axis pointing out of the hole.
    """

    screw_target_pose: Pose = document_field(ThreadKey.SCREW_TARGET_POSE)
    """
    The screw pose just above the entrance, from which the thread captures it.
    """


class WorkshopStateKey(StrEnum):
    """
    The keys of the workshop's measured state.
    """

    OBJECTS = "objects"
    """
    The movable bodies' poses.
    """

    JOINTS = "joints"
    """
    The drawer joints' positions.
    """

    HELD = "held"
    """
    The held body.
    """

    TARGET = "target"
    """
    The held body's spring target.
    """

    CONTACTS = "contacts"
    """
    The measured contacts.
    """

    TIME = "time"
    """
    The simulated time.
    """

    THREAD = "thread"
    """
    The ideal thread's state.
    """

    RUNNING = "running"
    """
    Whether time passes.
    """

    AVAILABLE = "available"
    """
    Whether the simulation takes commands.
    """

    ERROR = "error"
    """
    Why the simulation stopped.
    """


@dataclass(kw_only=True)
class WorkshopState(JsonDocument):
    """
    The measured state of the workshop's contact simulation.
    """

    objects: Dict[str, Pose] = document_field(
        WorkshopStateKey.OBJECTS, default_factory=dict
    )
    """
    The measured pose of every movable body by object key.
    """

    joints: Dict[str, float] = document_field(
        WorkshopStateKey.JOINTS, default_factory=dict
    )
    """
    The measured position of every drawer joint, in metres.
    """

    held: Optional[str] = document_field(WorkshopStateKey.HELD, default=None)
    """
    The object key of the body the spring holds, or None.
    """

    target: Optional[Pose] = document_field(WorkshopStateKey.TARGET, default=None)
    """
    The held body's spring target, or None.
    """

    contacts: List[MeasuredContact] = document_field(
        WorkshopStateKey.CONTACTS, default_factory=list
    )
    """
    The contacts with the largest forces.
    """

    time: float = document_field(WorkshopStateKey.TIME, default=0.0)
    """
    The simulated time, in seconds.
    """

    thread: Optional[ThreadObservation] = document_field(
        WorkshopStateKey.THREAD, default=None
    )
    """
    The ideal thread's state, or None before the simulation is built.
    """

    running: bool = document_field(WorkshopStateKey.RUNNING, default=False)
    """
    Whether time passes.
    """

    available: bool = document_field(WorkshopStateKey.AVAILABLE, default=True)
    """
    Whether the simulation takes commands.
    """

    error: Optional[str] = document_field(WorkshopStateKey.ERROR, default=None)
    """
    Why the simulation stopped, until it is reset.
    """
