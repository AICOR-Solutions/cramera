"""
The authored laboratory as a scene bundle describes it: the keys a laboratory adds to
``scene.json`` beside the scene description's own, with the rack, the vessels, the
instruments and the camera presets they declare.

Positions are in metres in the laboratory's frame, z up; angles are in radians.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.bundle.scene import Camera
from cramera_protocol.document import JsonDocument, document_field, extension_field
from cramera_protocol.geometry import NumberArray, Pose, Vector3

# %% values


@dataclass(frozen=True)
class PlanarSize(NumberArray):
    """
    The width and height of a flat rectangle in metres, such as an instrument display.
    """

    width: float
    """
    The rectangle's width.
    """

    height: float
    """
    The rectangle's height.
    """

    @classmethod
    def length(cls) -> int:
        return 2


@dataclass(frozen=True)
class Quaternion(NumberArray):
    """
    An orientation as a unit quaternion, written as ``[qx, qy, qz, qw]``.
    """

    qx: float
    """
    The x component.
    """

    qy: float
    """
    The y component.
    """

    qz: float
    """
    The z component.
    """

    qw: float
    """
    The scalar component.
    """

    @classmethod
    def length(cls) -> int:
        return 4


@dataclass(frozen=True)
class LinearColor(NumberArray):
    """
    A colour as linear red, green and blue components between zero and one.
    """

    red: float
    """
    The red component.
    """

    green: float
    """
    The green component.
    """

    blue: float
    """
    The blue component.
    """

    @classmethod
    def length(cls) -> int:
        return 3


# %% scene keys


class LaboratorySceneKey(StrEnum):
    """
    The keys a laboratory adds to ``scene.json``.
    """

    LABORATORY = "laboratory"
    """
    The bench: rack, vessels, stopper, drawer, cameras and the bench instruments.
    """

    INSTRUMENTS = "medicalLab"
    """
    The instrument collection of the expanded laboratory room.
    """

    CONTACT_PHYSICS = "contactPhysics"
    """
    The contact simulation's controls, written into the bundle a simulation shows.
    """

    VALIDATION = "validation"
    """
    Which kinds of execution the bundle was checked with.
    """

    ASSET_RIGHTS = "assetRights"
    """
    The authorship and the terms of the laboratory's assets.
    """

    NAVIGATION = "navigation"
    """
    The floor geometry a mobile robot may drive on.
    """


# %% rack and vessels


class RackSlotKey(StrEnum):
    """
    The keys of one rack slot.
    """

    IDENTIFIER = "id"
    """
    The slot's name, such as ``A1``.
    """

    POSE = "pose"
    """
    The pose of a vessel's bottom standing in the slot.
    """


@dataclass(kw_only=True)
class RackSlot(JsonDocument):
    """
    One opening of the sample rack.
    """

    identifier: str = document_field(RackSlotKey.IDENTIFIER)
    """
    The slot's name.
    """

    pose: Pose = document_field(RackSlotKey.POSE)
    """
    The pose of a vessel's bottom standing in the slot, in the laboratory's frame.
    """


class VesselPlacementKey(StrEnum):
    """
    The keys of one vessel's initial placement.
    """

    KEY = "key"
    """
    The vessel's object key.
    """

    SLOT = "slot"
    """
    The rack slot it starts in.
    """


@dataclass(kw_only=True)
class VesselPlacement(JsonDocument):
    """
    The rack slot a vessel starts in.
    """

    key: str = document_field(VesselPlacementKey.KEY)
    """
    The vessel's object key.
    """

    slot: str = document_field(VesselPlacementKey.SLOT)
    """
    The identifier of the rack slot.
    """


class StopperKey(StrEnum):
    """
    The keys of the stopper's description.
    """

    KEY = "key"
    """
    The stopper's object key.
    """

    HOME = "home"
    """
    Where the stopper lies when it closes no vessel.
    """

    TUBE_HEIGHT = "tubeHeight"
    """
    The height of the vessels it closes.
    """

    INSERTION_DEPTH = "insertionDepth"
    """
    How deep it sits below a vessel's rim.
    """


@dataclass(kw_only=True)
class StopperLayout(JsonDocument):
    """
    The removable stopper.
    """

    key: str = document_field(StopperKey.KEY)
    """
    The stopper's object key.
    """

    home: Pose = document_field(StopperKey.HOME)
    """
    Where the stopper lies when it closes no vessel.
    """

    tube_height: float = document_field(StopperKey.TUBE_HEIGHT)
    """
    The height of the vessels it closes, in metres.
    """

    insertion_depth: float = document_field(StopperKey.INSERTION_DEPTH)
    """
    How deep it sits below a vessel's rim, in metres.
    """


class RackKey(StrEnum):
    """
    The keys of the rack's description.
    """

    DRAWER_OFFSET = "drawerOffset"
    """
    Where the rack stands relative to the drawer floor's centre when it is prepared
    inside the drawer.
    """


@dataclass(kw_only=True)
class RackLayout(JsonDocument):
    """
    The movable sample rack.
    """

    drawer_offset: Vector3 = document_field(RackKey.DRAWER_OFFSET)
    """
    Where the rack stands relative to the drawer floor's centre when it is prepared
    inside the drawer.
    """


class BenchDrawerKey(StrEnum):
    """
    The keys of the drawer's description.
    """

    JOINT = "joint"
    """
    The drawer's prismatic joint.
    """

    OPEN = "open"
    """
    How far the drawer travels when fully open.
    """


@dataclass(kw_only=True)
class DrawerLayout(JsonDocument):
    """
    The bench drawer.
    """

    joint: str = document_field(BenchDrawerKey.JOINT)
    """
    The name of the drawer's prismatic joint.
    """

    open_position: float = document_field(BenchDrawerKey.OPEN)
    """
    How far the drawer travels when fully open, in metres.
    """


# %% scale


class ScaleHolderKey(StrEnum):
    """
    The keys of the vessel holder on the scale's pan.
    """

    INNER_RADIUS = "innerRadius"
    """
    The radius of the holder's opening.
    """

    OUTER_RADIUS = "outerRadius"
    """
    The holder's outer radius.
    """

    HEIGHT = "height"
    """
    The holder's height.
    """

    SEGMENTS = "segments"
    """
    How many segments the ring is built from.
    """


@dataclass(kw_only=True)
class ScaleHolder(JsonDocument):
    """
    The open ring on the scale's pan that keeps a round-bottomed vessel upright.
    """

    inner_radius: float = document_field(ScaleHolderKey.INNER_RADIUS)
    """
    The radius of the holder's opening, in metres.
    """

    outer_radius: float = document_field(ScaleHolderKey.OUTER_RADIUS)
    """
    The holder's outer radius, in metres.
    """

    height: float = document_field(ScaleHolderKey.HEIGHT)
    """
    The holder's height, in metres.
    """

    segments: int = document_field(ScaleHolderKey.SEGMENTS)
    """
    How many segments the ring and its collision surfaces are built from.
    """


class ScaleKey(StrEnum):
    """
    The keys of the scale's description.
    """

    PAN_POSITION = "panPosition"
    """
    The centre of the weighing pan's surface.
    """

    PAN_RADIUS = "panRadius"
    """
    The weighing pan's radius.
    """

    DISPLAY_POSITION = "displayPosition"
    """
    The centre of the scale's display.
    """

    DISPLAY_SIZE = "displaySize"
    """
    The size of the scale's display.
    """

    HOLDER = "holder"
    """
    The vessel holder on the pan.
    """


@dataclass(kw_only=True)
class ScaleLayout(JsonDocument):
    """
    The laboratory scale.
    """

    pan_position: Vector3 = document_field(ScaleKey.PAN_POSITION)
    """
    The centre of the weighing pan's surface.
    """

    pan_radius: float = document_field(ScaleKey.PAN_RADIUS)
    """
    The weighing pan's radius, in metres.
    """

    display_position: Vector3 = document_field(ScaleKey.DISPLAY_POSITION)
    """
    The centre of the scale's display.
    """

    display_size: PlanarSize = document_field(ScaleKey.DISPLAY_SIZE)
    """
    The size of the scale's display.
    """

    holder: ScaleHolder = document_field(ScaleKey.HOLDER)
    """
    The vessel holder on the pan.
    """


# %% centrifuge


class CentrifugeSlotKey(StrEnum):
    """
    The keys of one rotor holder.
    """

    IDENTIFIER = "id"
    """
    The holder's name, such as ``C1``.
    """

    OPPOSITE = "opposite"
    """
    The holder on the rotor's opposite side.
    """

    POSITION = "position"
    """
    Where a seated vessel's bottom rests, in the rotor's frame.
    """

    WORLD_POSITION = "worldPosition"
    """
    The same position in the laboratory's frame with the rotor at rest.
    """


@dataclass(kw_only=True)
class CentrifugeSlotLayout(JsonDocument):
    """
    One holder of the centrifuge's rotor.
    """

    identifier: str = document_field(CentrifugeSlotKey.IDENTIFIER)
    """
    The holder's name.
    """

    opposite: str = document_field(CentrifugeSlotKey.OPPOSITE)
    """
    The holder on the rotor's opposite side, which must carry the same mass.
    """

    position: Vector3 = document_field(CentrifugeSlotKey.POSITION)
    """
    Where a seated vessel's bottom rests, in the rotor's frame.
    """

    world_position: Vector3 = document_field(CentrifugeSlotKey.WORLD_POSITION)
    """
    The same position in the laboratory's frame with the rotor at rest.
    """


class CentrifugeKey(StrEnum):
    """
    The keys of the centrifuge's description.
    """

    BODY = "body"
    """
    The housing's link.
    """

    ROTOR_BODY = "rotorBody"
    """
    The rotor's link.
    """

    LID_BODY = "lidBody"
    """
    The lid's link.
    """

    ROTOR_JOINT = "rotorJoint"
    """
    The rotor's continuous joint.
    """

    LID_JOINT = "lidJoint"
    """
    The lid's hinge.
    """

    ORIGIN = "origin"
    """
    The housing's position.
    """

    ROTOR_ORIGIN = "rotorOrigin"
    """
    The rotor's position relative to the housing.
    """

    LID_ORIGIN = "lidOrigin"
    """
    The lid hinge's position relative to the housing.
    """

    OPEN_ANGLE = "openAngle"
    """
    The lid's opening angle.
    """

    MAXIMUM_SPEED = "maximumRpm"
    """
    The highest rotor speed the instrument allows.
    """

    CHAMBER_RADIUS = "chamberRadius"
    """
    The radius of the rotor chamber.
    """

    CHAMBER_HEIGHT = "chamberHeight"
    """
    The upper edge of the rotor chamber in the rotor's frame.
    """

    SLOTS = "slots"
    """
    The rotor's holders.
    """


@dataclass(kw_only=True)
class CentrifugeLayout(JsonDocument):
    """
    The bench centrifuge with its hinged lid and its rotor of four holders.
    """

    body: str = document_field(CentrifugeKey.BODY)
    """
    The housing's link.
    """

    rotor_body: str = document_field(CentrifugeKey.ROTOR_BODY)
    """
    The rotor's link.
    """

    lid_body: str = document_field(CentrifugeKey.LID_BODY)
    """
    The lid's link.
    """

    rotor_joint: str = document_field(CentrifugeKey.ROTOR_JOINT)
    """
    The rotor's continuous joint.
    """

    lid_joint: str = document_field(CentrifugeKey.LID_JOINT)
    """
    The lid's hinge.
    """

    origin: Vector3 = document_field(CentrifugeKey.ORIGIN)
    """
    The housing's position.
    """

    rotor_origin: Vector3 = document_field(CentrifugeKey.ROTOR_ORIGIN)
    """
    The rotor's position relative to the housing.
    """

    lid_origin: Vector3 = document_field(CentrifugeKey.LID_ORIGIN)
    """
    The lid hinge's position relative to the housing.
    """

    open_angle: float = document_field(CentrifugeKey.OPEN_ANGLE)
    """
    The lid's opening angle, in radians.
    """

    maximum_speed: float = document_field(CentrifugeKey.MAXIMUM_SPEED)
    """
    The highest rotor speed the instrument allows, in revolutions per minute.
    """

    chamber_radius: float = document_field(CentrifugeKey.CHAMBER_RADIUS)
    """
    The radius of the rotor chamber, in metres.
    """

    chamber_height: float = document_field(CentrifugeKey.CHAMBER_HEIGHT)
    """
    The upper edge of the rotor chamber in the rotor's frame, in metres.
    """

    slots: List[CentrifugeSlotLayout] = document_field(CentrifugeKey.SLOTS)
    """
    The rotor's holders.
    """


# %% pipetting station


class DispenserChannelKey(StrEnum):
    """
    The keys of one channel of the dispensing station.
    """

    IDENTIFIER = "id"
    """
    The channel's name.
    """

    NOZZLE_POSITION = "nozzlePosition"
    """
    Where the channel's liquid leaves the nozzle.
    """

    LIQUID_MESH = "liquidMesh"
    """
    The mesh showing the channel's reservoir content.
    """

    LIQUID_BOTTOM = "liquidBottom"
    """
    The reservoir content's bottom above the station's origin.
    """

    LIQUID_HEIGHT = "liquidHeight"
    """
    The height of a full reservoir's content.
    """


@dataclass(kw_only=True)
class DispenserChannelLayout(JsonDocument):
    """
    One reagent channel of the dispensing station.
    """

    identifier: str = document_field(DispenserChannelKey.IDENTIFIER)
    """
    The channel's name.
    """

    nozzle_position: Vector3 = document_field(DispenserChannelKey.NOZZLE_POSITION)
    """
    Where the channel's liquid leaves the nozzle.
    """

    liquid_mesh: str = document_field(DispenserChannelKey.LIQUID_MESH)
    """
    The name of the mesh showing the channel's reservoir content.
    """

    liquid_bottom: float = document_field(DispenserChannelKey.LIQUID_BOTTOM)
    """
    The reservoir content's bottom above the station's origin, in metres.
    """

    liquid_height: float = document_field(DispenserChannelKey.LIQUID_HEIGHT)
    """
    The height of a full reservoir's content, in metres.
    """


class DispenserKey(StrEnum):
    """
    The keys of the dispensing station's description.
    """

    BODY = "body"
    """
    The station's link.
    """

    JOINT = "joint"
    """
    The joint fixing the station to the bench.
    """

    ASSET = "asset"
    """
    The station's mesh.
    """

    ORIGIN = "origin"
    """
    The station's position.
    """

    TARGET_POSITION = "targetPosition"
    """
    Where a receiving vessel's bottom must stand.
    """

    NOZZLE_POSITION = "nozzlePosition"
    """
    The common outlet of both channels.
    """

    DISPLAY_POSITION = "displayPosition"
    """
    The centre of the station's display.
    """

    DISPLAY_SIZE = "displaySize"
    """
    The size of the station's display.
    """

    DISPLAY_MESH = "displayMesh"
    """
    The mesh of the station's display.
    """

    CHANNELS = "channels"
    """
    The reagent channels.
    """


@dataclass(kw_only=True)
class DispenserLayout(JsonDocument):
    """
    The stationary two-channel dispensing station.
    """

    body: str = document_field(DispenserKey.BODY)
    """
    The station's link.
    """

    joint: str = document_field(DispenserKey.JOINT)
    """
    The joint fixing the station to the bench.
    """

    asset: str = document_field(DispenserKey.ASSET)
    """
    The station's mesh, relative to the bundle.
    """

    origin: Vector3 = document_field(DispenserKey.ORIGIN)
    """
    The station's position.
    """

    target_position: Vector3 = document_field(DispenserKey.TARGET_POSITION)
    """
    Where a receiving vessel's bottom must stand.
    """

    nozzle_position: Vector3 = document_field(DispenserKey.NOZZLE_POSITION)
    """
    The common outlet of both channels.
    """

    display_position: Vector3 = document_field(DispenserKey.DISPLAY_POSITION)
    """
    The centre of the station's display.
    """

    display_size: PlanarSize = document_field(DispenserKey.DISPLAY_SIZE)
    """
    The size of the station's display.
    """

    display_mesh: str = document_field(DispenserKey.DISPLAY_MESH)
    """
    The name of the display's mesh.
    """

    channels: List[DispenserChannelLayout] = document_field(DispenserKey.CHANNELS)
    """
    The reagent channels.
    """


# %% refrigerator


class StorageSlotKey(StrEnum):
    """
    The keys of one storage position of the sample refrigerator.
    """

    IDENTIFIER = "id"
    """
    The position's name, such as ``R1``.
    """

    POSITION = "position"
    """
    Where a stored vessel's bottom stands, in the laboratory's frame.
    """

    LOCAL_POSITION = "localPosition"
    """
    The same position in the refrigerator's frame.
    """


@dataclass(kw_only=True)
class StorageSlotLayout(JsonDocument):
    """
    One storage position of the sample refrigerator.
    """

    identifier: str = document_field(StorageSlotKey.IDENTIFIER)
    """
    The position's name.
    """

    position: Vector3 = document_field(StorageSlotKey.POSITION)
    """
    Where a stored vessel's bottom stands, in the laboratory's frame.
    """

    local_position: Vector3 = document_field(StorageSlotKey.LOCAL_POSITION)
    """
    The same position in the refrigerator's frame.
    """


class RefrigeratorKey(StrEnum):
    """
    The keys of the sample refrigerator's description.
    """

    BODY = "body"
    """
    The cabinet's link.
    """

    DOOR_BODY = "doorBody"
    """
    The door's link.
    """

    JOINT = "joint"
    """
    The joint fixing the cabinet to the room.
    """

    DOOR_JOINT = "doorJoint"
    """
    The door's hinge.
    """

    ASSET = "asset"
    """
    The cabinet's mesh.
    """

    DOOR_ASSET = "doorAsset"
    """
    The door's mesh.
    """

    ORIGIN = "origin"
    """
    The cabinet's position.
    """

    DOOR_ORIGIN = "doorOrigin"
    """
    The door hinge's position relative to the cabinet.
    """

    DOOR_OPEN = "doorOpen"
    """
    The door's opening angle.
    """

    DIMENSIONS = "dimensions"
    """
    The cabinet's outer size.
    """

    DISPLAY_MESH = "displayMesh"
    """
    The mesh of the temperature display.
    """

    DISPLAY_POSITION = "displayPosition"
    """
    The centre of the temperature display.
    """

    DISPLAY_SIZE = "displaySize"
    """
    The size of the temperature display.
    """

    TARGET_TEMPERATURE = "targetTemperature"
    """
    The temperature the cabinet cools to.
    """

    SLOTS = "slots"
    """
    The storage positions.
    """


@dataclass(kw_only=True)
class RefrigeratorLayout(JsonDocument):
    """
    The sample refrigerator with its hinged glass door.
    """

    body: str = document_field(RefrigeratorKey.BODY)
    """
    The cabinet's link.
    """

    door_body: str = document_field(RefrigeratorKey.DOOR_BODY)
    """
    The door's link.
    """

    joint: str = document_field(RefrigeratorKey.JOINT)
    """
    The joint fixing the cabinet to the room.
    """

    door_joint: str = document_field(RefrigeratorKey.DOOR_JOINT)
    """
    The door's hinge.
    """

    asset: str = document_field(RefrigeratorKey.ASSET)
    """
    The cabinet's mesh, relative to the bundle.
    """

    door_asset: str = document_field(RefrigeratorKey.DOOR_ASSET)
    """
    The door's mesh, relative to the bundle.
    """

    origin: Vector3 = document_field(RefrigeratorKey.ORIGIN)
    """
    The cabinet's position.
    """

    door_origin: Vector3 = document_field(RefrigeratorKey.DOOR_ORIGIN)
    """
    The door hinge's position relative to the cabinet.
    """

    door_open: float = document_field(RefrigeratorKey.DOOR_OPEN)
    """
    The door's opening angle, in radians.
    """

    dimensions: Vector3 = document_field(RefrigeratorKey.DIMENSIONS)
    """
    The cabinet's outer size.
    """

    display_mesh: str = document_field(RefrigeratorKey.DISPLAY_MESH)
    """
    The name of the temperature display's mesh.
    """

    display_position: Vector3 = document_field(RefrigeratorKey.DISPLAY_POSITION)
    """
    The centre of the temperature display.
    """

    display_size: PlanarSize = document_field(RefrigeratorKey.DISPLAY_SIZE)
    """
    The size of the temperature display.
    """

    target_temperature: float = document_field(RefrigeratorKey.TARGET_TEMPERATURE)
    """
    The temperature the cabinet cools to, in degrees Celsius.
    """

    slots: List[StorageSlotLayout] = document_field(RefrigeratorKey.SLOTS)
    """
    The storage positions.
    """


# %% bench


class BenchKey(StrEnum):
    """
    The keys of the bench, the value of :attr:`LaboratorySceneKey.LABORATORY`.
    """

    RACK_SLOTS = "rackSlots"
    """
    The rack's slots.
    """

    TUBES = "tubes"
    """
    The vessels and the slots they start in.
    """

    STOPPER = "stopper"
    """
    The removable stopper.
    """

    DRAWER = "drawer"
    """
    The bench drawer.
    """

    CAMERAS = "cameras"
    """
    The named camera presets.
    """

    RACK = "rack"
    """
    The movable rack.
    """

    SCALE = "scale"
    """
    The laboratory scale.
    """

    CENTRIFUGE = "centrifuge"
    """
    The bench centrifuge.
    """

    DISPENSER = "pipetting"
    """
    The dispensing station.
    """

    REFRIGERATOR = "refrigerator"
    """
    The sample refrigerator.
    """


@dataclass(kw_only=True)
class BenchLayout(JsonDocument):
    """
    The laboratory bench: where the vessels start and the instruments beside them.

    Instruments a bench lacks are None.
    """

    rack_slots: List[RackSlot] = document_field(BenchKey.RACK_SLOTS)
    """
    The rack's slots.
    """

    tubes: List[VesselPlacement] = document_field(BenchKey.TUBES)
    """
    The vessels and the slots they start in.
    """

    stopper: Optional[StopperLayout] = document_field(BenchKey.STOPPER, default=None)
    """
    The removable stopper.
    """

    drawer: Optional[DrawerLayout] = document_field(BenchKey.DRAWER, default=None)
    """
    The bench drawer.
    """

    cameras: Dict[str, Camera] = document_field(BenchKey.CAMERAS, default_factory=dict)
    """
    The camera presets by name.
    """

    rack: Optional[RackLayout] = document_field(BenchKey.RACK, default=None)
    """
    The movable rack.
    """

    scale: Optional[ScaleLayout] = document_field(BenchKey.SCALE, default=None)
    """
    The laboratory scale.
    """

    centrifuge: Optional[CentrifugeLayout] = document_field(
        BenchKey.CENTRIFUGE, default=None
    )
    """
    The bench centrifuge.
    """

    dispenser: Optional[DispenserLayout] = document_field(
        BenchKey.DISPENSER, default=None
    )
    """
    The dispensing station.
    """

    refrigerator: Optional[RefrigeratorLayout] = document_field(
        BenchKey.REFRIGERATOR, default=None
    )
    """
    The sample refrigerator.
    """

    def slot(self, identifier: str) -> RackSlot:
        """
        :param identifier: A slot's name.
        :return: The slot.
        :raises KeyError: When the rack has no such slot.
        """
        return {slot.identifier: slot for slot in self.rack_slots}[identifier]


# %% instrument collection


class InstrumentJointKind(StrEnum):
    """
    The kinds of moving joints an instrument has, as URDF names them.
    """

    REVOLUTE = "revolute"
    """
    A hinge with stops.
    """

    PRISMATIC = "prismatic"
    """
    A slide with stops.
    """

    CONTINUOUS = "continuous"
    """
    A hinge without stops.
    """


class InstrumentJointKey(StrEnum):
    """
    The keys of one moving joint of an instrument.
    """

    NAME = "name"
    """
    The joint's name in the environment's URDF.
    """

    KIND = "type"
    """
    An :class:`InstrumentJointKind` value.
    """

    REST = "rest"
    """
    The joint's position at rest.
    """

    INSPECTION = "inspection"
    """
    The joint's position when the instrument is opened for inspection.
    """

    LOWER = "lower"
    """
    The joint's lower stop.
    """

    UPPER = "upper"
    """
    The joint's upper stop.
    """

    VELOCITY = "velocity"
    """
    The joint's highest speed.
    """

    EFFORT = "effort"
    """
    The joint drive's largest force or torque.
    """


@dataclass(kw_only=True)
class InstrumentJoint(JsonDocument):
    """
    One moving joint of an instrument, with its rest and inspection positions.
    """

    name: str = document_field(InstrumentJointKey.NAME)
    """
    The joint's name in the environment's URDF.
    """

    kind: InstrumentJointKind = document_field(InstrumentJointKey.KIND)
    """
    The kind of joint.
    """

    rest: float = document_field(InstrumentJointKey.REST)
    """
    The joint's position at rest, in radians or metres.
    """

    inspection: float = document_field(InstrumentJointKey.INSPECTION)
    """
    The joint's position when the instrument is opened for inspection.
    """

    lower: float = document_field(InstrumentJointKey.LOWER)
    """
    The joint's lower stop; ignored for a continuous joint.
    """

    upper: float = document_field(InstrumentJointKey.UPPER)
    """
    The joint's upper stop; ignored for a continuous joint.
    """

    velocity: float = document_field(InstrumentJointKey.VELOCITY)
    """
    The joint's highest speed, in radians or metres per second.
    """

    effort: float = document_field(InstrumentJointKey.EFFORT)
    """
    The joint drive's largest torque or force, in newton metres or newtons.
    """


class InstrumentKey(StrEnum):
    """
    The keys of one instrument of the collection.
    """

    IDENTIFIER = "id"
    """
    The instrument's name, which is also its device folder's name.
    """

    LABEL = "label"
    """
    The instrument's display name.
    """

    STATION = "station"
    """
    The workstation the instrument stands at.
    """

    JOINTS = "joints"
    """
    The instrument's moving joints.
    """

    POSE = "pose"
    """
    Where the instrument stands.
    """

    ROOT = "root"
    """
    The instrument's root link in the environment.
    """

    RESOURCE = "resource"
    """
    The instrument's own URDF, relative to the bundle.
    """


@dataclass(kw_only=True)
class Instrument(JsonDocument):
    """
    One instrument of the expanded laboratory.
    """

    identifier: str = document_field(InstrumentKey.IDENTIFIER)
    """
    The instrument's name, which is also its device folder's name.
    """

    label: str = document_field(InstrumentKey.LABEL)
    """
    The instrument's display name.
    """

    station: str = document_field(InstrumentKey.STATION)
    """
    The identifier of the workstation the instrument stands at.
    """

    joints: List[InstrumentJoint] = document_field(InstrumentKey.JOINTS)
    """
    The instrument's moving joints; empty for a passive accessory.
    """

    pose: Pose = document_field(InstrumentKey.POSE)
    """
    Where the instrument stands.
    """

    root: str = document_field(InstrumentKey.ROOT)
    """
    The instrument's root link in the environment.
    """

    resource: str = document_field(InstrumentKey.RESOURCE)
    """
    The instrument's own URDF, relative to the bundle.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The instrument's interaction frames, which the laboratory passes on unchanged.
    """


class WorkstationKey(StrEnum):
    """
    The keys of one workstation of the expanded laboratory.
    """

    IDENTIFIER = "id"
    """
    The workstation's name.
    """

    LABEL = "label"
    """
    The workstation's display name.
    """

    CAMERA = "camera"
    """
    The view of the workstation.
    """


@dataclass(kw_only=True)
class Workstation(JsonDocument):
    """
    One workstation of the expanded laboratory.
    """

    identifier: str = document_field(WorkstationKey.IDENTIFIER)
    """
    The workstation's name.
    """

    label: str = document_field(WorkstationKey.LABEL)
    """
    The workstation's display name.
    """

    camera: Camera = document_field(WorkstationKey.CAMERA)
    """
    The view of the workstation.
    """


class CornerBoxKey(StrEnum):
    """
    The keys of an axis-aligned box given by two corners.
    """

    MINIMUM = "min"
    """
    The corner with the smallest coordinates.
    """

    MAXIMUM = "max"
    """
    The corner with the largest coordinates.
    """


@dataclass(kw_only=True)
class CornerBox(JsonDocument):
    """
    An axis-aligned box given by its two corners.
    """

    minimum: Vector3 = document_field(CornerBoxKey.MINIMUM)
    """
    The corner with the smallest coordinates.
    """

    maximum: Vector3 = document_field(CornerBoxKey.MAXIMUM)
    """
    The corner with the largest coordinates.
    """


class ContactExclusionKey(StrEnum):
    """
    The keys of one pair of mating parts.
    """

    FIRST = "first"
    """
    The first part's link.
    """

    SECOND = "second"
    """
    The second part's link.
    """


@dataclass(kw_only=True)
class ContactExclusion(JsonDocument):
    """
    Two links of one instrument that touch by design, such as a bearing, and whose
    contact the simulation leaves out.
    """

    first: str = document_field(ContactExclusionKey.FIRST)
    """
    The first link.
    """

    second: str = document_field(ContactExclusionKey.SECOND)
    """
    The second link.
    """


class InstrumentCollectionKey(StrEnum):
    """
    The keys of the expanded laboratory's instrument collection.
    """

    TITLE = "title"
    """
    The laboratory's display name.
    """

    INSTRUMENTS = "instruments"
    """
    The instruments.
    """

    BOUNDS = "bounds"
    """
    The region a person may move objects in.
    """

    STATIONS = "stations"
    """
    The workstations.
    """

    CONTACT_EXCLUSIONS = "contactExclusions"
    """
    The mating parts whose contact the simulation leaves out.
    """


@dataclass(kw_only=True)
class InstrumentCollection(JsonDocument):
    """
    The instruments and workstations of the expanded laboratory, the value of
    :attr:`LaboratorySceneKey.INSTRUMENTS`.
    """

    title: str = document_field(InstrumentCollectionKey.TITLE)
    """
    The laboratory's display name.
    """

    instruments: List[Instrument] = document_field(InstrumentCollectionKey.INSTRUMENTS)
    """
    The instruments, in the order they are presented.
    """

    bounds: Optional[CornerBox] = document_field(
        InstrumentCollectionKey.BOUNDS, default=None
    )
    """
    The region a person may move objects in; None keeps the bench's region.
    """

    stations: List[Workstation] = document_field(
        InstrumentCollectionKey.STATIONS, default_factory=list
    )
    """
    The workstations.
    """

    contact_exclusions: List[ContactExclusion] = document_field(
        InstrumentCollectionKey.CONTACT_EXCLUSIONS, default_factory=list
    )
    """
    The mating parts whose contact the simulation leaves out.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The room's dimensions, which the laboratory passes on unchanged.
    """


# %% semantics


class LaboratorySemanticsKey(StrEnum):
    """
    The keys a laboratory adds to ``semantics.json``.
    """

    VESSEL = "tube"
    """
    The dimensions every vessel shares.
    """


class VesselDimensionsKey(StrEnum):
    """
    The keys of the vessels' dimensions.
    """

    HEIGHT = "height"
    """
    The vessel's height.
    """

    OUTER_RADIUS = "outerRadius"
    """
    The glass's outer radius.
    """

    INNER_RADIUS = "innerRadius"
    """
    The glass's inner radius.
    """

    GRASP_HEIGHT = "graspHeight"
    """
    Where above its bottom the vessel is grasped.
    """

    INSERTION_AXIS = "insertionAxis"
    """
    The direction a vessel moves into a rack slot.
    """

    MASS = "massKilograms"
    """
    The empty vessel's mass.
    """


@dataclass(kw_only=True)
class VesselDimensions(JsonDocument):
    """
    The dimensions every vessel of a laboratory shares.
    """

    height: float = document_field(VesselDimensionsKey.HEIGHT)
    """
    The vessel's height, in metres.
    """

    outer_radius: float = document_field(VesselDimensionsKey.OUTER_RADIUS)
    """
    The glass's outer radius, in metres.
    """

    inner_radius: float = document_field(VesselDimensionsKey.INNER_RADIUS)
    """
    The glass's inner radius, in metres.
    """

    grasp_height: float = document_field(VesselDimensionsKey.GRASP_HEIGHT)
    """
    Where above its bottom the vessel is grasped, in metres.
    """

    insertion_axis: Vector3 = document_field(VesselDimensionsKey.INSERTION_AXIS)
    """
    The direction a vessel moves into a rack slot.
    """

    mass: float = document_field(VesselDimensionsKey.MASS)
    """
    The empty vessel's mass, in kilograms.
    """
