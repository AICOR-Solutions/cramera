"""
The laboratory plugin's routes, the commands a person sends to the contact simulation
and the state the simulation measures.

Every answer of a simulation route is a :class:`SimulationAnswer`. Positions are in
metres in the laboratory's frame, z up; forces in newtons; volumes in millilitres.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.laboratory.knowledge import ManualEdition, OperatingKnowledge
from cramera_protocol.laboratory.layout import CornerBox, LinearColor, Quaternion

# %% plugin


class LaboratoryName(StrEnum):
    """
    The names under which the laboratory is installed.
    """

    PLUGIN = "laboratory"
    """
    The plugin's name, which is also its route segment and its side panel's identity.
    """


class LaboratoryFile(StrEnum):
    """
    The browser files of the laboratory, relative to its web directory.
    """

    MODULE = "index.js"
    """
    The module the viewer registers.
    """


class LaboratoryRoute(StrEnum):
    """
    The laboratory's routes, below ``/api/plugins/laboratory/``.
    """

    LABORATORIES = "laboratories"
    """
    The laboratories the plugin ships and whether they are installed.
    """

    INSTALL = "install"
    """
    Copies a laboratory into the local scenes, so the viewer shows it.
    """

    DEVICES = "devices"
    """
    The independent laboratory devices.
    """

    DEVICE_FILES = "device-files/"
    """
    The files of the device folders: ``device-files/<device>/<file>``.
    """

    STATE = "physics/state"
    """
    The contact simulation's state.
    """

    START = "physics/start"
    """
    Starts the contact simulation of a laboratory.
    """

    STOP = "physics/stop"
    """
    Stops the contact simulation.
    """

    RESET = "physics/reset"
    """
    Restores the laboratory's initial state.
    """

    TARGET = "physics/target"
    """
    Pulls an object towards a target with a bounded force.
    """

    RELEASE = "physics/release"
    """
    Lets go of the pulled object.
    """

    LIQUID = "physics/liquid"
    """
    Fills a vessel with an amount of liquid.
    """

    TARE = "physics/scale/tare"
    """
    Takes the scale's settled load as its zero.
    """

    CENTRIFUGE = "physics/centrifuge"
    """
    Operates the centrifuge.
    """

    MANUAL = "physics/manual"
    """
    Gives the centrifuge another operating manual.
    """

    REFRIGERATOR = "physics/refrigerator"
    """
    Opens or closes the refrigerator's door.
    """

    DRAWER = "physics/drawer"
    """
    Opens or closes the bench drawer.
    """

    DISPENSER = "physics/dispenser"
    """
    Operates the dispensing station.
    """

    INSTRUMENT = "physics/instrument"
    """
    Moves an instrument of the expanded laboratory to its rest or inspection pose.
    """

    TRANSFER_STATE = "transfer/state"
    """
    Whether the PR2 vessel transfer demo runs, and the recording it saved.
    """

    TRANSFER_START = "transfer/start"
    """
    Runs the PR2 vessel transfer demo.
    """

    TRANSFER_STOP = "transfer/stop"
    """
    Ends a running PR2 vessel transfer demo.
    """


# %% catalog


class LaboratoryEntryKey(StrEnum):
    """
    The keys of one laboratory the plugin ships.
    """

    NAME = "name"
    """
    The laboratory's bundle name.
    """

    TITLE = "title"
    """
    The laboratory's display name.
    """

    INSTALLED = "installed"
    """
    Whether the viewer's local scenes hold the laboratory.
    """

    INSTRUMENTS = "instruments"
    """
    How many instruments of the expanded collection it holds.
    """


@dataclass(kw_only=True)
class LaboratoryEntry(JsonDocument):
    """
    One laboratory the plugin ships.
    """

    name: str = document_field(LaboratoryEntryKey.NAME)
    """
    The laboratory's bundle name.
    """

    title: str = document_field(LaboratoryEntryKey.TITLE)
    """
    The laboratory's display name.
    """

    installed: bool = document_field(LaboratoryEntryKey.INSTALLED)
    """
    Whether the viewer's local scenes hold the laboratory under its name.
    """

    instruments: int = document_field(LaboratoryEntryKey.INSTRUMENTS)
    """
    How many instruments of the expanded collection it holds.
    """


class LaboratoryCatalogKey(StrEnum):
    """
    The keys of the answer to :attr:`LaboratoryRoute.LABORATORIES`.
    """

    LABORATORIES = "laboratories"
    """
    The laboratories.
    """

    PHYSICS_AVAILABLE = "physicsAvailable"
    """
    Whether the contact simulation can run here.
    """


@dataclass(kw_only=True)
class LaboratoryCatalog(JsonDocument):
    """
    The laboratories the plugin ships.
    """

    laboratories: List[LaboratoryEntry] = document_field(
        LaboratoryCatalogKey.LABORATORIES
    )
    """
    The laboratories.
    """

    physics_available: bool = document_field(LaboratoryCatalogKey.PHYSICS_AVAILABLE)
    """
    Whether the contact simulation can run: whether MuJoCo is installed.
    """


class LaboratoryChoiceKey(StrEnum):
    """
    The keys of a request naming a laboratory.
    """

    LABORATORY = "laboratory"
    """
    The laboratory's bundle name.
    """


@dataclass(kw_only=True)
class LaboratoryChoice(JsonDocument):
    """
    The request to :attr:`LaboratoryRoute.INSTALL` and :attr:`LaboratoryRoute.START`.
    """

    laboratory: str = document_field(LaboratoryChoiceKey.LABORATORY)
    """
    The laboratory's bundle name.
    """


class InstalledLaboratoryKey(StrEnum):
    """
    The keys of the answer to :attr:`LaboratoryRoute.INSTALL`.
    """

    SCENE = "scene"
    """
    The bundle the viewer shows the laboratory as.
    """


@dataclass(kw_only=True)
class InstalledLaboratory(JsonDocument):
    """
    Where an installed laboratory is shown.
    """

    scene: str = document_field(InstalledLaboratoryKey.SCENE)
    """
    The name of the bundle the viewer shows the laboratory as.
    """


# %% devices


class DeviceEntryKey(StrEnum):
    """
    The keys of one independent device.
    """

    NAME = "name"
    """
    The device's folder name.
    """

    TITLE = "title"
    """
    The device's display name.
    """

    DESCRIPTION = "description"
    """
    The device's URDF, relative to the device folder.
    """

    MOVING_JOINTS = "movingJoints"
    """
    How many joints of the device move.
    """


@dataclass(kw_only=True)
class DeviceEntry(JsonDocument):
    """
    One independently loadable device.
    """

    name: str = document_field(DeviceEntryKey.NAME)
    """
    The device's folder name.
    """

    title: str = document_field(DeviceEntryKey.TITLE)
    """
    The device's display name.
    """

    description: str = document_field(DeviceEntryKey.DESCRIPTION)
    """
    The device's URDF, relative to the device folder.
    """

    moving_joints: int = document_field(DeviceEntryKey.MOVING_JOINTS)
    """
    How many joints of the device move.
    """


class DeviceCatalogKey(StrEnum):
    """
    The keys of the answer to :attr:`LaboratoryRoute.DEVICES`.
    """

    DEVICES = "devices"
    """
    The devices.
    """


@dataclass(kw_only=True)
class DeviceCatalog(JsonDocument):
    """
    The independent laboratory devices.
    """

    devices: List[DeviceEntry] = document_field(DeviceCatalogKey.DEVICES)
    """
    The devices, by name.
    """


# %% commands


@dataclass(kw_only=True)
class EmptyRequest(JsonDocument):
    """
    The request of a route that takes no parameters: an empty object.
    """


class TargetRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.TARGET`.
    """

    KEY = "key"
    """
    The object to pull.
    """

    POSITION = "position"
    """
    Where to pull it.
    """

    ORIENTATION = "orientation"
    """
    How to turn it.
    """


@dataclass(kw_only=True)
class TargetRequest(JsonDocument):
    """
    Pulls a free object towards a pose with a bounded spring force, as a hand would.
    """

    key: str = document_field(TargetRequestKey.KEY)
    """
    The object's key.
    """

    position: Vector3 = document_field(TargetRequestKey.POSITION)
    """
    Where to pull the object's origin.
    """

    orientation: Optional[Quaternion] = document_field(
        TargetRequestKey.ORIENTATION, default=None
    )
    """
    How to turn the object; None keeps it upright.
    """


class LiquidRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.LIQUID`.
    """

    KEY = "key"
    """
    The vessel.
    """

    VOLUME = "volumeMl"
    """
    The amount it holds afterwards.
    """


@dataclass(kw_only=True)
class LiquidRequest(JsonDocument):
    """
    Sets the amount of liquid a vessel holds.
    """

    key: str = document_field(LiquidRequestKey.KEY)
    """
    The vessel's key.
    """

    volume: float = document_field(LiquidRequestKey.VOLUME)
    """
    The amount the vessel holds afterwards, in millilitres.
    """


class OpeningAction(StrEnum):
    """
    What a door, lid or drawer request asks for.
    """

    OPEN = "open"
    """
    Move to the open stop.
    """

    CLOSE = "close"
    """
    Move to the closed stop.
    """


class OpeningRequestKey(StrEnum):
    """
    The keys of the requests to :attr:`LaboratoryRoute.REFRIGERATOR` and
    :attr:`LaboratoryRoute.DRAWER`.
    """

    ACTION = "action"
    """
    A :class:`OpeningAction` value.
    """


@dataclass(kw_only=True)
class OpeningRequest(JsonDocument):
    """
    Opens or closes a door or drawer through its force-limited drive.
    """

    action: OpeningAction = document_field(OpeningRequestKey.ACTION)
    """
    What to do.
    """


class CentrifugeAction(StrEnum):
    """
    What a centrifuge request asks for.
    """

    OPEN = "open"
    """
    Open the lid of the stopped rotor.
    """

    CLOSE = "close"
    """
    Close the lid.
    """

    SECURE = "secure"
    """
    Clamp a vessel seated in a holder.
    """

    RELEASE = "release"
    """
    Unclamp a holder of the stopped rotor.
    """

    START = "start"
    """
    Run a timed cycle of the balanced rotor.
    """

    STOP = "stop"
    """
    Brake the rotor.
    """


class CentrifugeRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.CENTRIFUGE`.
    """

    ACTION = "action"
    """
    A :class:`CentrifugeAction` value.
    """

    SLOT = "slot"
    """
    The holder to clamp or unclamp.
    """

    KEY = "key"
    """
    The vessel to clamp.
    """

    SPEED = "rpm"
    """
    The speed of a cycle.
    """

    DURATION = "duration"
    """
    The length of a cycle.
    """


@dataclass(kw_only=True)
class CentrifugeRequest(JsonDocument):
    """
    One centrifuge operation.

    :attr:`CentrifugeAction.SECURE` takes a slot and a key,
    :attr:`CentrifugeAction.RELEASE` a slot, :attr:`CentrifugeAction.START` an optional
    speed and duration, the others nothing.
    """

    action: CentrifugeAction = document_field(CentrifugeRequestKey.ACTION)
    """
    What to do.
    """

    slot: Optional[str] = document_field(CentrifugeRequestKey.SLOT, default=None)
    """
    The holder to clamp or unclamp.
    """

    key: Optional[str] = document_field(CentrifugeRequestKey.KEY, default=None)
    """
    The vessel to clamp.
    """

    speed: Optional[float] = document_field(CentrifugeRequestKey.SPEED, default=None)
    """
    The speed of a cycle, in revolutions per minute; None takes the default.
    """

    duration: Optional[float] = document_field(
        CentrifugeRequestKey.DURATION, default=None
    )
    """
    The length of a cycle at speed, in simulated seconds; None takes the default.
    """


class ManualRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.MANUAL`.
    """

    EDITION = "edition"
    """
    A shipped edition.
    """

    DOCUMENT = "document"
    """
    A manual's Markdown text.
    """


@dataclass(kw_only=True)
class ManualRequest(JsonDocument):
    """
    Gives the centrifuge another manual: a shipped edition or a text, exactly one.
    """

    edition: Optional[ManualEdition] = document_field(
        ManualRequestKey.EDITION, default=None
    )
    """
    A shipped edition.
    """

    document: Optional[str] = document_field(ManualRequestKey.DOCUMENT, default=None)
    """
    A manual's Markdown text.
    """


class DispenserAction(StrEnum):
    """
    What a dispensing station request asks for.
    """

    DISPENSE = "dispense"
    """
    Start a dose into the vessel under the nozzle.
    """

    STOP = "stop"
    """
    Stop the flow, keeping what was delivered.
    """

    RESUME = "resume"
    """
    Deliver the rest of a stopped dose.
    """

    REFILL = "refill"
    """
    Fill a reagent reservoir up again.
    """


class DispenserRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.DISPENSER`.
    """

    ACTION = "action"
    """
    A :class:`DispenserAction` value.
    """

    KEY = "key"
    """
    The receiving vessel.
    """

    CHANNEL = "source"
    """
    The reagent channel.
    """

    VOLUME = "volumeMl"
    """
    The dose.
    """


@dataclass(kw_only=True)
class DispenserRequest(JsonDocument):
    """
    One operation of the dispensing station.

    :attr:`DispenserAction.DISPENSE` takes a vessel, a channel and an optional dose,
    :attr:`DispenserAction.REFILL` a channel, the others nothing.
    """

    action: DispenserAction = document_field(DispenserRequestKey.ACTION)
    """
    What to do.
    """

    key: Optional[str] = document_field(DispenserRequestKey.KEY, default=None)
    """
    The receiving vessel's key.
    """

    channel: Optional[str] = document_field(DispenserRequestKey.CHANNEL, default=None)
    """
    The reagent channel's identifier.
    """

    volume: Optional[float] = document_field(DispenserRequestKey.VOLUME, default=None)
    """
    The dose in millilitres; None takes the default dose.
    """


class InstrumentPose(StrEnum):
    """
    The poses an instrument of the expanded laboratory is moved to.
    """

    REST = "rest"
    """
    Closed and at rest.
    """

    INSPECTION = "inspection"
    """
    Opened for inspection.
    """


class InstrumentRequestKey(StrEnum):
    """
    The keys of the request to :attr:`LaboratoryRoute.INSTRUMENT`.
    """

    INSTRUMENT = "instrument"
    """
    The instrument.
    """

    POSE = "pose"
    """
    An :class:`InstrumentPose` value.
    """


@dataclass(kw_only=True)
class InstrumentRequest(JsonDocument):
    """
    Moves every joint of an instrument to its rest or inspection position through its
    force-limited drives.
    """

    instrument: str = document_field(InstrumentRequestKey.INSTRUMENT)
    """
    The instrument's identifier.
    """

    pose: InstrumentPose = document_field(InstrumentRequestKey.POSE)
    """
    Where to move it.
    """


# %% contacts and target


class MeasuredContactKey(StrEnum):
    """
    The keys of one measured contact.
    """

    POSITION = "position"
    """
    Where the bodies touch.
    """

    NORMAL = "normal"
    """
    The contact normal from the first body towards the second.
    """

    FORCE = "force"
    """
    The normal force.
    """

    FIRST_BODY = "bodyA"
    """
    The first body.
    """

    SECOND_BODY = "bodyB"
    """
    The second body.
    """


@dataclass(kw_only=True)
class MeasuredContact(JsonDocument):
    """
    One contact the solver pushes apart with a positive force.
    """

    position: Vector3 = document_field(MeasuredContactKey.POSITION)
    """
    Where the bodies touch.
    """

    normal: Vector3 = document_field(MeasuredContactKey.NORMAL)
    """
    The unit contact normal from the first body towards the second.
    """

    force: float = document_field(MeasuredContactKey.FORCE)
    """
    The normal force, in newtons.
    """

    first_body: str = document_field(MeasuredContactKey.FIRST_BODY)
    """
    The first body's name.
    """

    second_body: str = document_field(MeasuredContactKey.SECOND_BODY)
    """
    The second body's name.
    """


class PullTargetKey(StrEnum):
    """
    The keys of the pose an object is pulled towards.
    """

    KEY = "key"
    """
    The pulled object.
    """

    POSITION = "position"
    """
    Where it is pulled.
    """

    ORIENTATION = "orientation"
    """
    How it is turned.
    """


@dataclass(kw_only=True)
class PullTarget(JsonDocument):
    """
    The pose an object is pulled towards.
    """

    key: str = document_field(PullTargetKey.KEY)
    """
    The pulled object's key.
    """

    position: Vector3 = document_field(PullTargetKey.POSITION)
    """
    Where its origin is pulled.
    """

    orientation: Quaternion = document_field(PullTargetKey.ORIENTATION)
    """
    How it is turned, a unit quaternion.
    """


# %% liquid


class VesselLiquidKey(StrEnum):
    """
    The keys of the liquid in one vessel.
    """

    VOLUME = "volumeMl"
    """
    The amount held.
    """

    COLOR = "color"
    """
    The liquid's colour.
    """

    NORMAL = "normal"
    """
    The surface's upward normal in the vessel's frame.
    """

    OFFSET = "offset"
    """
    The surface plane's offset along its normal.
    """


@dataclass(kw_only=True)
class VesselLiquid(JsonDocument):
    """
    The liquid in one vessel: its amount, its colour and its free surface.
    """

    volume: float = document_field(VesselLiquidKey.VOLUME)
    """
    The amount held, in millilitres.
    """

    color: LinearColor = document_field(VesselLiquidKey.COLOR)
    """
    The liquid's colour, mixed by volume.
    """

    normal: Vector3 = document_field(VesselLiquidKey.NORMAL)
    """
    The free surface's upward unit normal in the vessel's frame.
    """

    offset: float = document_field(VesselLiquidKey.OFFSET)
    """
    The free surface is the plane of the points whose product with :attr:`normal` is
    this offset, in metres.
    """


class DropletKey(StrEnum):
    """
    The keys of one portion of liquid in flight.
    """

    SOURCE = "source"
    """
    The vessel it left.
    """

    POSITION = "position"
    """
    Where it is.
    """

    VELOCITY = "velocity"
    """
    How fast it moves.
    """

    VOLUME = "volumeMl"
    """
    Its amount.
    """

    COLOR = "color"
    """
    Its colour.
    """

    EMITTED_AT = "emittedAt"
    """
    When it left its vessel.
    """


@dataclass(kw_only=True)
class Droplet(JsonDocument):
    """
    A portion of liquid in flight.
    """

    source: str = document_field(DropletKey.SOURCE)
    """
    The key of the vessel it left.
    """

    position: Vector3 = document_field(DropletKey.POSITION)
    """
    Where it is.
    """

    velocity: Vector3 = document_field(DropletKey.VELOCITY)
    """
    How fast it moves, in metres per second.
    """

    volume: float = document_field(DropletKey.VOLUME)
    """
    Its amount, in millilitres.
    """

    color: LinearColor = document_field(DropletKey.COLOR)
    """
    Its colour.
    """

    emitted_at: float = document_field(DropletKey.EMITTED_AT)
    """
    When it left its vessel, in simulated seconds of the liquid model.
    """


class PuddleKey(StrEnum):
    """
    The keys of one puddle.
    """

    POSITION = "position"
    """
    Its centre.
    """

    VOLUME = "volumeMl"
    """
    Its amount.
    """

    COLOR = "color"
    """
    Its colour.
    """


@dataclass(kw_only=True)
class Puddle(JsonDocument):
    """
    Spilled liquid lying on the worktop or the floor.
    """

    position: Vector3 = document_field(PuddleKey.POSITION)
    """
    Its centre on the surface.
    """

    volume: float = document_field(PuddleKey.VOLUME)
    """
    Its amount, in millilitres.
    """

    color: LinearColor = document_field(PuddleKey.COLOR)
    """
    Its colour, mixed by volume.
    """


class LiquidStateKey(StrEnum):
    """
    The keys of the liquid model's state.
    """

    TIME = "time"
    """
    How long the liquid has been simulated.
    """

    VESSELS = "vessels"
    """
    The liquid in each vessel.
    """

    DROPLETS = "droplets"
    """
    The liquid in flight.
    """

    PUDDLES = "puddles"
    """
    The spilled liquid.
    """

    SUPPLIED = "suppliedMl"
    """
    How much liquid entered the laboratory.
    """


@dataclass(kw_only=True)
class LiquidState(JsonDocument):
    """
    Where all liquid of the laboratory is.

    Its vessels, droplets and puddles together always hold :attr:`supplied`.
    """

    time: float = document_field(LiquidStateKey.TIME)
    """
    How long the liquid has been simulated since the last reset, in seconds.
    """

    vessels: Dict[str, VesselLiquid] = document_field(LiquidStateKey.VESSELS)
    """
    The liquid in each vessel, by the vessel's key.
    """

    droplets: List[Droplet] = document_field(LiquidStateKey.DROPLETS)
    """
    The liquid in flight.
    """

    puddles: List[Puddle] = document_field(LiquidStateKey.PUDDLES)
    """
    The spilled liquid.
    """

    supplied: float = document_field(LiquidStateKey.SUPPLIED)
    """
    How much liquid the vessels started with plus what filling and dosing added, in
    millilitres.
    """


# %% instruments


class ScaleReadingKey(StrEnum):
    """
    The keys of the scale's reading.
    """

    GRAMS = "grams"
    """
    The shown mass.
    """

    TARE = "tareGrams"
    """
    The load taken as zero.
    """

    STABLE = "stable"
    """
    Whether the reading has settled.
    """

    FORCE = "forceNewtons"
    """
    The measured downward force on the pan.
    """

    OBJECTS = "objects"
    """
    The bodies pressing on the pan.
    """


@dataclass(kw_only=True)
class ScaleReading(JsonDocument):
    """
    What the scale measures from the contact forces on its pan.
    """

    grams: float = document_field(ScaleReadingKey.GRAMS)
    """
    The shown mass, the filtered load less the tare, in grams.
    """

    tare: float = document_field(ScaleReadingKey.TARE)
    """
    The load taken as zero, in grams.
    """

    stable: bool = document_field(ScaleReadingKey.STABLE)
    """
    Whether the reading has settled, which taring requires.
    """

    force: float = document_field(ScaleReadingKey.FORCE)
    """
    The measured downward force on the pan, in newtons.
    """

    objects: List[str] = document_field(ScaleReadingKey.OBJECTS)
    """
    The bodies pressing on the pan, by name.
    """


class RotorHolderKey(StrEnum):
    """
    The keys of one rotor holder's state.
    """

    IDENTIFIER = "id"
    """
    The holder.
    """

    POSITION = "position"
    """
    Where a seated vessel's bottom rests now.
    """

    KEY = "key"
    """
    The clamped vessel.
    """

    GRAMS = "grams"
    """
    The clamped vessel's mass.
    """


@dataclass(kw_only=True)
class RotorHolder(JsonDocument):
    """
    One holder of the turning rotor.
    """

    identifier: str = document_field(RotorHolderKey.IDENTIFIER)
    """
    The holder's name.
    """

    position: Vector3 = document_field(RotorHolderKey.POSITION)
    """
    Where a seated vessel's bottom rests at the rotor's measured angle.
    """

    key: Optional[str] = document_field(RotorHolderKey.KEY, default=None)
    """
    The clamped vessel's key; None for a free holder.
    """

    grams: float = document_field(RotorHolderKey.GRAMS)
    """
    The clamped vessel's mass with its liquid, in grams; zero for a free holder.
    """


class CentrifugeStateKey(StrEnum):
    """
    The keys of the centrifuge's state.
    """

    SPEED = "rpm"
    """
    The measured rotor speed.
    """

    TARGET_SPEED = "targetRpm"
    """
    The speed asked for.
    """

    RELATIVE_FORCE = "rcf"
    """
    The relative centrifugal force at the holders.
    """

    LID_OPEN = "lidOpen"
    """
    Whether the lid is fully open.
    """

    LID_CLOSED = "lidClosed"
    """
    Whether the lid is closed.
    """

    RUNNING = "running"
    """
    Whether the rotor turns or is driven.
    """

    BALANCED = "balanced"
    """
    Whether the clamped samples are balanced.
    """

    REMAINING = "remainingSeconds"
    """
    The time left of the cycle.
    """

    HOLDERS = "slots"
    """
    The rotor's holders.
    """

    KNOWLEDGE = "knowledge"
    """
    The operating manual and whether the rotor may start.
    """


@dataclass(kw_only=True)
class CentrifugeState(JsonDocument):
    """
    What the centrifuge measures.
    """

    speed: float = document_field(CentrifugeStateKey.SPEED)
    """
    The measured rotor speed, in revolutions per minute.
    """

    target_speed: float = document_field(CentrifugeStateKey.TARGET_SPEED)
    """
    The speed asked for, in revolutions per minute.
    """

    relative_force: float = document_field(CentrifugeStateKey.RELATIVE_FORCE)
    """
    The centrifugal acceleration at the holders' radius as a multiple of gravity.
    """

    lid_open: bool = document_field(CentrifugeStateKey.LID_OPEN)
    """
    Whether the measured lid is fully open, which loading requires.
    """

    lid_closed: bool = document_field(CentrifugeStateKey.LID_CLOSED)
    """
    Whether the measured lid is closed, which a run requires.
    """

    running: bool = document_field(CentrifugeStateKey.RUNNING)
    """
    Whether the rotor turns or is driven.
    """

    balanced: bool = document_field(CentrifugeStateKey.BALANCED)
    """
    Whether every clamped sample has an opposite sample of equal mass and nothing loose
    lies in the chamber.
    """

    remaining: float = document_field(CentrifugeStateKey.REMAINING)
    """
    The time left of the cycle at speed, in simulated seconds.
    """

    holders: List[RotorHolder] = document_field(CentrifugeStateKey.HOLDERS)
    """
    The rotor's holders.
    """

    knowledge: OperatingKnowledge = document_field(CentrifugeStateKey.KNOWLEDGE)
    """
    The operating manual and whether the rotor may start.
    """


class TemperatureSource(StrEnum):
    """
    Where a temperature comes from.
    """

    SIMULATED = "simulated"
    """
    A reduced heat exchange model driven by simulated time and the door's angle.
    """


class StoragePositionKey(StrEnum):
    """
    The keys of one refrigerator storage position's state.
    """

    IDENTIFIER = "id"
    """
    The position.
    """

    KEY = "key"
    """
    The vessel stored there.
    """


@dataclass(kw_only=True)
class StoragePosition(JsonDocument):
    """
    One storage position and the vessel standing in it.
    """

    identifier: str = document_field(StoragePositionKey.IDENTIFIER)
    """
    The position's name.
    """

    key: Optional[str] = document_field(StoragePositionKey.KEY, default=None)
    """
    The key of the upright, supported vessel standing there; None for an empty position.
    """


class RefrigeratorStateKey(StrEnum):
    """
    The keys of the refrigerator's state.
    """

    DOOR_OPEN = "doorOpen"
    """
    Whether the door is fully open.
    """

    DOOR_CLOSED = "doorClosed"
    """
    Whether the door is closed.
    """

    TEMPERATURE = "temperatureC"
    """
    The cabinet's temperature.
    """

    TEMPERATURE_SOURCE = "temperatureModel"
    """
    Where the temperature comes from.
    """

    POSITIONS = "slots"
    """
    The storage positions.
    """


@dataclass(kw_only=True)
class RefrigeratorState(JsonDocument):
    """
    What the sample refrigerator measures.
    """

    door_open: bool = document_field(RefrigeratorStateKey.DOOR_OPEN)
    """
    Whether the measured door is fully open, which taking samples out requires.
    """

    door_closed: bool = document_field(RefrigeratorStateKey.DOOR_CLOSED)
    """
    Whether the measured door is closed.
    """

    temperature: float = document_field(RefrigeratorStateKey.TEMPERATURE)
    """
    The cabinet's temperature, in degrees Celsius.
    """

    temperature_source: TemperatureSource = document_field(
        RefrigeratorStateKey.TEMPERATURE_SOURCE
    )
    """
    Where the temperature comes from.
    """

    positions: List[StoragePosition] = document_field(RefrigeratorStateKey.POSITIONS)
    """
    The storage positions.
    """


class BenchDrawerStateKey(StrEnum):
    """
    The keys of the drawer's state.
    """

    POSITION = "position"
    """
    How far the drawer is out.
    """

    TARGET = "targetPosition"
    """
    Where its drive holds it.
    """

    OPEN = "open"
    """
    Whether it is fully open.
    """

    CLOSED = "closed"
    """
    Whether it is closed.
    """


@dataclass(kw_only=True)
class DrawerState(JsonDocument):
    """
    What the bench drawer measures.
    """

    position: float = document_field(BenchDrawerStateKey.POSITION)
    """
    How far the drawer is out, in metres.
    """

    target: float = document_field(BenchDrawerStateKey.TARGET)
    """
    Where its force-limited drive holds it, in metres.
    """

    fully_open: bool = document_field(BenchDrawerStateKey.OPEN)
    """
    Whether it reached its outer stop.
    """

    closed: bool = document_field(BenchDrawerStateKey.CLOSED)
    """
    Whether it reached its inner stop.
    """


class RackPositionKey(StrEnum):
    """
    The keys of one slot of the moving rack.
    """

    IDENTIFIER = "id"
    """
    The slot.
    """

    POSE = "pose"
    """
    Where a vessel's bottom stands in the slot now.
    """

    KEY = "key"
    """
    The vessel standing in the slot.
    """


@dataclass(kw_only=True)
class RackPosition(JsonDocument):
    """
    One slot of the rack where the rack stands now.
    """

    identifier: str = document_field(RackPositionKey.IDENTIFIER)
    """
    The slot's name.
    """

    pose: Pose = document_field(RackPositionKey.POSE)
    """
    Where a vessel's bottom stands in the slot.
    """

    key: Optional[str] = document_field(RackPositionKey.KEY, default=None)
    """
    The key of the upright vessel the rack supports in the slot; None for an empty slot.
    """


class RackStateKey(StrEnum):
    """
    The keys of the rack's state.
    """

    POSE = "pose"
    """
    Where the rack stands.
    """

    SUPPORTS = "supportBodies"
    """
    The bodies carrying its weight.
    """

    SLOTS = "slots"
    """
    Its slots.
    """


@dataclass(kw_only=True)
class RackState(JsonDocument):
    """
    What the movable rack measures.
    """

    pose: Pose = document_field(RackStateKey.POSE)
    """
    Where the rack stands.
    """

    supports: List[str] = document_field(RackStateKey.SUPPORTS)
    """
    The bodies that carry a share of its weight, by name; empty while it is lifted.
    """

    slots: List[RackPosition] = document_field(RackStateKey.SLOTS)
    """
    Its slots.
    """


class DispenserState(StrEnum):
    """
    What the dispensing station's pump does.
    """

    IDLE = "idle"
    """
    It stands still.
    """

    DISPENSING = "dispensing"
    """
    It delivers a dose.
    """

    COMPLETE = "complete"
    """
    It delivered the whole dose.
    """

    BLOCKED = "blocked"
    """
    A measured condition stopped the dose.
    """


class ReservoirKey(StrEnum):
    """
    The keys of one reagent reservoir's state.
    """

    IDENTIFIER = "id"
    """
    The channel.
    """

    VOLUME = "volumeMl"
    """
    What the reservoir holds.
    """


@dataclass(kw_only=True)
class ReservoirLevel(JsonDocument):
    """
    What one reagent reservoir holds.
    """

    identifier: str = document_field(ReservoirKey.IDENTIFIER)
    """
    The channel's identifier.
    """

    volume: float = document_field(ReservoirKey.VOLUME)
    """
    What the reservoir holds, in millilitres.
    """


class DoseKey(StrEnum):
    """
    The keys of the dispensing station's state.
    """

    STATE = "state"
    """
    What the pump does.
    """

    CHANNEL = "source"
    """
    The channel of the current dose.
    """

    KEY = "key"
    """
    The vessel of the current dose.
    """

    REQUESTED = "requestedMl"
    """
    The dose asked for.
    """

    DELIVERED = "deliveredMl"
    """
    What was delivered of it.
    """

    BLOCKED_BY = "error"
    """
    Why the dose stopped.
    """

    RESERVOIRS = "reservoirs"
    """
    The reagent reservoirs.
    """


@dataclass(kw_only=True)
class DispenserStatus(JsonDocument):
    """
    What the dispensing station measures.
    """

    state: DispenserState = document_field(DoseKey.STATE)
    """
    What the pump does.
    """

    channel: Optional[str] = document_field(DoseKey.CHANNEL, default=None)
    """
    The channel of the current or last dose.
    """

    key: Optional[str] = document_field(DoseKey.KEY, default=None)
    """
    The vessel of the current or last dose.
    """

    requested: float = document_field(DoseKey.REQUESTED)
    """
    The dose asked for, in millilitres.
    """

    delivered: float = document_field(DoseKey.DELIVERED)
    """
    What was delivered of it, in millilitres.
    """

    blocked_by: Optional[str] = document_field(DoseKey.BLOCKED_BY, default=None)
    """
    Why the dose stopped, while the pump is blocked.
    """

    reservoirs: List[ReservoirLevel] = document_field(DoseKey.RESERVOIRS)
    """
    The reagent reservoirs.
    """


# %% simulation


class SimulationState(StrEnum):
    """
    Whether the contact simulation runs.
    """

    IDLE = "idle"
    """
    No simulation runs.
    """

    RUNNING = "running"
    """
    The simulation advances in real time.
    """

    FAILED = "failed"
    """
    The simulation could not start or stopped with an error.
    """


class SnapshotKey(StrEnum):
    """
    The keys of one measured state of the contact simulation.
    """

    TIME = "time"
    """
    The simulated time.
    """

    ENERGY = "energy"
    """
    The kinetic and potential energy.
    """

    APPLIED_FORCE = "appliedForce"
    """
    The force pulling the target object.
    """

    MAXIMUM_APPLIED_FORCE = "maximumAppliedForce"
    """
    The largest pulling force so far.
    """

    MAXIMUM_CONTACT_FORCE = "maximumContactForce"
    """
    The largest contact force so far.
    """

    OBJECTS = "objects"
    """
    The free objects' poses.
    """

    BODY_POSES = "bodyPoses"
    """
    The poses of free links of the environment.
    """

    JOINTS = "joints"
    """
    The positions of the environment's moving joints.
    """

    TARGET = "target"
    """
    The pose an object is pulled towards.
    """

    CONTACTS = "contacts"
    """
    The contacts.
    """

    LIQUID = "liquid"
    """
    The liquid.
    """

    SCALE = "scale"
    """
    The scale's reading.
    """

    CENTRIFUGE = "centrifuge"
    """
    The centrifuge's state.
    """

    REFRIGERATOR = "refrigerator"
    """
    The refrigerator's state.
    """

    DRAWER = "drawer"
    """
    The drawer's state.
    """

    RACK = "rack"
    """
    The rack's state.
    """

    DISPENSER = "pipetting"
    """
    The dispensing station's state.
    """


@dataclass(kw_only=True)
class SimulationSnapshot(JsonDocument):
    """
    What the contact simulation measures at one instant.

    Instruments the laboratory lacks are None.
    """

    time: float = document_field(SnapshotKey.TIME)
    """
    The simulated time since the last reset, in seconds.
    """

    energy: float = document_field(SnapshotKey.ENERGY)
    """
    The kinetic and potential energy, in joules.
    """

    applied_force: float = document_field(SnapshotKey.APPLIED_FORCE)
    """
    The force pulling the target object, in newtons.
    """

    maximum_applied_force: float = document_field(SnapshotKey.MAXIMUM_APPLIED_FORCE)
    """
    The largest pulling force since the last reset, in newtons.
    """

    maximum_contact_force: float = document_field(SnapshotKey.MAXIMUM_CONTACT_FORCE)
    """
    The largest single contact force since the last reset, in newtons.
    """

    objects: Dict[str, Pose] = document_field(SnapshotKey.OBJECTS)
    """
    The free objects' poses, by key.
    """

    body_poses: Dict[str, Pose] = document_field(
        SnapshotKey.BODY_POSES, default_factory=dict
    )
    """
    The poses of the environment's freely moving links, such as the rack, by link name.
    """

    joints: Dict[str, float] = document_field(SnapshotKey.JOINTS)
    """
    The positions of the environment's moving joints, by joint name.
    """

    target: Optional[PullTarget] = document_field(SnapshotKey.TARGET, default=None)
    """
    The pose an object is pulled towards; None while nothing is pulled.
    """

    contacts: List[MeasuredContact] = document_field(SnapshotKey.CONTACTS)
    """
    The contacts the solver pushes apart.
    """

    liquid: LiquidState = document_field(SnapshotKey.LIQUID)
    """
    Where the liquid is.
    """

    scale: Optional[ScaleReading] = document_field(SnapshotKey.SCALE, default=None)
    """
    The scale's reading.
    """

    centrifuge: Optional[CentrifugeState] = document_field(
        SnapshotKey.CENTRIFUGE, default=None
    )
    """
    The centrifuge's state.
    """

    refrigerator: Optional[RefrigeratorState] = document_field(
        SnapshotKey.REFRIGERATOR, default=None
    )
    """
    The refrigerator's state.
    """

    drawer: Optional[DrawerState] = document_field(SnapshotKey.DRAWER, default=None)
    """
    The drawer's state.
    """

    rack: Optional[RackState] = document_field(SnapshotKey.RACK, default=None)
    """
    The rack's state.
    """

    dispenser: Optional[DispenserStatus] = document_field(
        SnapshotKey.DISPENSER, default=None
    )
    """
    The dispensing station's state.
    """


class SimulationAnswerKey(StrEnum):
    """
    The keys of every answer of a simulation route.
    """

    STATE = "state"
    """
    Whether the simulation runs.
    """

    ERROR = "error"
    """
    Why it failed.
    """

    LABORATORY = "laboratory"
    """
    The laboratory simulated.
    """

    SCENE = "scene"
    """
    The bundle showing the simulation.
    """

    SNAPSHOT = "snapshot"
    """
    What the simulation measures.
    """


@dataclass(kw_only=True)
class SimulationAnswer(JsonDocument):
    """
    The contact simulation's state, the answer of every simulation route.
    """

    state: SimulationState = document_field(SimulationAnswerKey.STATE)
    """
    Whether the simulation runs.
    """

    error: Optional[str] = document_field(SimulationAnswerKey.ERROR, default=None)
    """
    Why the simulation failed; None unless :attr:`state` is
    :attr:`SimulationState.FAILED`.
    """

    laboratory: Optional[str] = document_field(
        SimulationAnswerKey.LABORATORY, default=None
    )
    """
    The laboratory simulated; None before the first start.
    """

    scene: Optional[str] = document_field(SimulationAnswerKey.SCENE, default=None)
    """
    The bundle the viewer shows the simulation in; None before the first start.
    """

    snapshot: Optional[SimulationSnapshot] = document_field(
        SimulationAnswerKey.SNAPSHOT, default=None
    )
    """
    What the simulation measures; None while none exists.
    """


# %% controls written into the simulation's bundle


class VesselInteriorKey(StrEnum):
    """
    The keys of the vessel interior every liquid uses.
    """

    RADIUS = "radius"
    """
    The inner radius.
    """

    BOTTOM = "bottom"
    """
    The lowest inner point above the vessel's origin.
    """

    RIM = "rim"
    """
    The open rim's height above the vessel's origin.
    """

    CAPACITY = "capacityMl"
    """
    The volume up to the rim.
    """


@dataclass(kw_only=True)
class VesselInterior(JsonDocument):
    """
    The inside of a vessel: a cylinder on a half sphere, open at the rim.
    """

    radius: float = document_field(VesselInteriorKey.RADIUS)
    """
    The inner radius, in metres; also the radius of the rounded bottom.
    """

    bottom: float = document_field(VesselInteriorKey.BOTTOM)
    """
    The lowest inner point above the vessel's origin, in metres.
    """

    rim: float = document_field(VesselInteriorKey.RIM)
    """
    The open rim's height above the vessel's origin, in metres.
    """

    capacity: float = document_field(VesselInteriorKey.CAPACITY)
    """
    The volume up to the rim, in millilitres.
    """


class ReagentKey(StrEnum):
    """
    The keys of one reagent of the dispensing station.
    """

    IDENTIFIER = "id"
    """
    The channel.
    """

    LABEL = "label"
    """
    The reagent's name.
    """

    COLOR = "color"
    """
    The reagent's colour.
    """

    CAPACITY = "capacityMl"
    """
    The reservoir's volume.
    """


@dataclass(kw_only=True)
class Reagent(JsonDocument):
    """
    One reagent of the dispensing station.
    """

    identifier: str = document_field(ReagentKey.IDENTIFIER)
    """
    The channel's identifier.
    """

    label: str = document_field(ReagentKey.LABEL)
    """
    The reagent's name.
    """

    color: LinearColor = document_field(ReagentKey.COLOR)
    """
    The reagent's colour.
    """

    capacity: float = document_field(ReagentKey.CAPACITY)
    """
    The reservoir's volume, in millilitres.
    """


class DoseLimitsKey(StrEnum):
    """
    The keys of the dispensing station's limits.
    """

    REAGENTS = "reagents"
    """
    The reagents.
    """

    MINIMUM = "minimumMl"
    """
    The smallest dose.
    """

    MAXIMUM = "maximumMl"
    """
    The largest dose.
    """

    DEFAULT = "defaultMl"
    """
    The dose when none is given.
    """

    FLOW_RATE = "flowRateMl"
    """
    How fast the pump delivers.
    """


@dataclass(kw_only=True)
class DoseLimits(JsonDocument):
    """
    The dispensing station's reagents and limits.
    """

    reagents: List[Reagent] = document_field(DoseLimitsKey.REAGENTS)
    """
    The reagents.
    """

    minimum: float = document_field(DoseLimitsKey.MINIMUM)
    """
    The smallest dose, in millilitres.
    """

    maximum: float = document_field(DoseLimitsKey.MAXIMUM)
    """
    The largest dose, in millilitres.
    """

    default: float = document_field(DoseLimitsKey.DEFAULT)
    """
    The dose when a request gives none, in millilitres.
    """

    flow_rate: float = document_field(DoseLimitsKey.FLOW_RATE)
    """
    How fast the pump delivers, in millilitres per simulated second.
    """


class CycleLimitsKey(StrEnum):
    """
    The keys of the centrifuge's cycle limits.
    """

    DEFAULT_SPEED = "defaultRpm"
    """
    The speed when none is given.
    """

    MAXIMUM_SPEED = "maximumRpm"
    """
    The highest speed.
    """

    DEFAULT_DURATION = "defaultDuration"
    """
    The length when none is given.
    """

    MINIMUM_DURATION = "minimumDuration"
    """
    The shortest cycle.
    """

    MAXIMUM_DURATION = "maximumDuration"
    """
    The longest cycle.
    """


@dataclass(kw_only=True)
class CycleLimits(JsonDocument):
    """
    The limits of a centrifuge cycle.
    """

    default_speed: float = document_field(CycleLimitsKey.DEFAULT_SPEED)
    """
    The speed when a request gives none, in revolutions per minute.
    """

    maximum_speed: float = document_field(CycleLimitsKey.MAXIMUM_SPEED)
    """
    The highest speed, in revolutions per minute.
    """

    default_duration: float = document_field(CycleLimitsKey.DEFAULT_DURATION)
    """
    The length when a request gives none, in simulated seconds.
    """

    minimum_duration: float = document_field(CycleLimitsKey.MINIMUM_DURATION)
    """
    The shortest cycle, in simulated seconds.
    """

    maximum_duration: float = document_field(CycleLimitsKey.MAXIMUM_DURATION)
    """
    The longest cycle, in simulated seconds.
    """


class ContactPhysicsKey(StrEnum):
    """
    The keys of the controls written into a simulation's bundle, the value of
    :attr:`~cramera_protocol.laboratory.layout.LaboratorySceneKey.CONTACT_PHYSICS`.
    """

    LABORATORY = "laboratory"
    """
    The laboratory simulated.
    """

    OBJECTS = "objects"
    """
    The objects a person may pull.
    """

    VESSELS = "vessels"
    """
    The objects that hold liquid.
    """

    BOUNDS = "bounds"
    """
    Where targets may lie.
    """

    MAXIMUM_FORCE = "maximumForce"
    """
    The strongest pull.
    """

    INTERIOR = "interior"
    """
    The vessels' inside.
    """

    DOSES = "doses"
    """
    The dispensing station's limits.
    """

    CYCLES = "cycles"
    """
    The centrifuge's cycle limits.
    """


@dataclass(kw_only=True)
class ContactPhysicsControls(JsonDocument):
    """
    What the browser needs to operate a contact simulation, written into the bundle that
    shows it.
    """

    laboratory: str = document_field(ContactPhysicsKey.LABORATORY)
    """
    The name of the laboratory simulated.
    """

    objects: List[str] = document_field(ContactPhysicsKey.OBJECTS)
    """
    The keys of the objects a person may pull.
    """

    vessels: List[str] = document_field(ContactPhysicsKey.VESSELS)
    """
    The keys of the objects that hold liquid.
    """

    bounds: CornerBox = document_field(ContactPhysicsKey.BOUNDS)
    """
    Where pull targets may lie.
    """

    maximum_force: float = document_field(ContactPhysicsKey.MAXIMUM_FORCE)
    """
    The strongest pull, in newtons, gravity compensation included.
    """

    interior: VesselInterior = document_field(ContactPhysicsKey.INTERIOR)
    """
    The inside of every vessel.
    """

    doses: Optional[DoseLimits] = document_field(ContactPhysicsKey.DOSES, default=None)
    """
    The dispensing station's limits; None without a station.
    """

    cycles: Optional[CycleLimits] = document_field(
        ContactPhysicsKey.CYCLES, default=None
    )
    """
    The centrifuge's cycle limits; None without a centrifuge.
    """
