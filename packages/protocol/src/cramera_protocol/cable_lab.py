"""
The cable lab: the configuration of a simulated composite cable, the commands of its
friction gripper and the geometry and forces the simulation measures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.geometry import NumberArray, Pose, Vector3

# %% limits

MINIMUM_SEGMENT_COUNT = 2
"""
The fewest rigid elements a cable has.
"""

MAXIMUM_SEGMENT_COUNT = 100
"""
The most rigid elements a cable has.
"""

MAXIMUM_CABLE_LENGTH = 2.0
"""
The longest cable, in metres.
"""

MAXIMUM_RADIUS = 0.05
"""
The thickest cable's radius, in metres.
"""

MAXIMUM_MASS = 10.0
"""
The heaviest cable, in kilograms.
"""

CONTACT_DIMENSIONS = (1, 3, 4, 6)
"""
The contact dimensionalities MuJoCo supports.
"""

# %% routes


class CableLabRoute(StrEnum):
    """
    The routes of the cable lab plugin, below ``/api/plugins/cable-lab/``.
    """

    STATE = "state"
    """
    The measured cable, gripper and contacts.
    """

    START = "start"
    """
    Builds a cable from a :class:`CableConfiguration` and starts its simulation.
    """

    COMMAND = "command"
    """
    Applies one :class:`GripperCommand`.
    """

    RESET = "reset"
    """
    Builds the last cable again and starts it from its initial pose.
    """

    STOP = "stop"
    """
    Stops the simulation.
    """


class CableLabFile(StrEnum):
    """
    The cable lab's browser page.
    """

    PAGE = "cable-lab.html"
    """
    The full-window lab, in the plugin's browser files.
    """


# %% number arrays


@dataclass(frozen=True)
class RgbaColor(NumberArray):
    """
    A colour with opacity, each channel from 0 to 1.
    """

    red: float
    """
    The red channel.
    """

    green: float
    """
    The green channel.
    """

    blue: float
    """
    The blue channel.
    """

    alpha: float
    """
    The opacity.
    """

    @classmethod
    def length(cls) -> int:
        return 4


@dataclass(frozen=True)
class ContactFriction(NumberArray):
    """
    MuJoCo's three friction coefficients of a contact.
    """

    sliding: float
    """
    The sliding friction coefficient.
    """

    torsional: float
    """
    The torsional friction coefficient.
    """

    rolling: float
    """
    The rolling friction coefficient.
    """

    @classmethod
    def length(cls) -> int:
        return 3


@dataclass(frozen=True)
class SolverReference(NumberArray):
    """
    MuJoCo's contact reference: how fast and how damped a penetration is resolved.
    """

    time_constant: float
    """
    The time constant, in seconds.
    """

    damping_ratio: float
    """
    The damping ratio.
    """

    @classmethod
    def length(cls) -> int:
        return 2


@dataclass(frozen=True)
class SolverImpedance(NumberArray):
    """
    MuJoCo's contact impedance: how stiff a contact is over its penetration depth.
    """

    minimum: float
    """
    The impedance at no penetration.
    """

    maximum: float
    """
    The impedance at full penetration.
    """

    width: float
    """
    The penetration over which the impedance changes, in metres.
    """

    midpoint: float
    """
    Where along that width the impedance curve turns.
    """

    power: float
    """
    The exponent of the impedance curve.
    """

    @classmethod
    def length(cls) -> int:
        return 5

    def is_valid(self) -> bool:
        """
        :return: Whether MuJoCo accepts the impedance.
        """
        return (
            0 < self.minimum <= self.maximum < 1
            and self.width > 0
            and 0 < self.midpoint < 1
            and self.power >= 1
        )


# %% configuration


class CableConfigurationKey(StrEnum):
    """
    The keys of a cable configuration.
    """

    SEGMENT_COUNT = "segmentCount"
    """
    The number of rigid elements.
    """

    SEGMENT_LENGTH = "segmentLength"
    """
    Each element's length.
    """

    RADIUS = "radius"
    """
    The cable's radius.
    """

    MASS = "mass"
    """
    The cable's total mass.
    """

    COLOR = "color"
    """
    The cable's colour.
    """

    BEND = "bend"
    """
    The bending modulus.
    """

    TWIST = "twist"
    """
    The twisting modulus.
    """

    ANCHORED = "anchored"
    """
    Whether the first point is pinned.
    """

    ANCHOR_OFFSET = "anchorOffset"
    """
    Where the first point starts.
    """

    ANCHOR_ROTATION = "anchorRotation"
    """
    The cable's initial direction.
    """

    FRICTION = "friction"
    """
    The contact friction.
    """

    CONTACT_DIMENSION = "contactDimension"
    """
    MuJoCo's contact dimensionality.
    """

    SOLVER_REFERENCE = "solverReference"
    """
    MuJoCo's contact reference.
    """

    SOLVER_IMPEDANCE = "solverImpedance"
    """
    MuJoCo's contact impedance.
    """


@dataclass
class InvalidCableConfiguration(ProtocolError):
    """
    A cable configuration the lab cannot build.
    """

    key: CableConfigurationKey
    """
    The key whose value does not fit.
    """

    reason: str
    """
    What fits.
    """

    def message(self) -> str:
        return f"The cable's {self.key.value} is invalid: {self.reason}"


@dataclass(kw_only=True)
class CableConfiguration(JsonDocument):
    """
    The geometry, mass, elasticity, placement and contact settings of a cable; every key
    is optional, so an empty object asks for the default cable.
    """

    segment_count: int = document_field(CableConfigurationKey.SEGMENT_COUNT, default=10)
    """
    The number of rigid capsule elements.
    """

    segment_length: float = document_field(
        CableConfigurationKey.SEGMENT_LENGTH, default=0.03
    )
    """
    Each element's length, in metres.
    """

    radius: float = document_field(CableConfigurationKey.RADIUS, default=0.005)
    """
    The capsules' radius, in metres.
    """

    mass: float = document_field(CableConfigurationKey.MASS, default=0.1)
    """
    The whole cable's mass, in kilograms.
    """

    color: RgbaColor = document_field(
        CableConfigurationKey.COLOR,
        default_factory=lambda: RgbaColor(1.0, 0.0, 0.0, 1.0),
    )
    """
    The colour of the physical capsules.
    """

    bend: float = document_field(CableConfigurationKey.BEND, default=1e5)
    """
    The bending modulus, in pascals.
    """

    twist: float = document_field(CableConfigurationKey.TWIST, default=1e5)
    """
    The twisting modulus, in pascals.
    """

    anchored: bool = document_field(CableConfigurationKey.ANCHORED, default=True)
    """
    Whether a ball joint pins the first point to the anchor frame.
    """

    anchor_offset: Vector3 = document_field(
        CableConfigurationKey.ANCHOR_OFFSET,
        default_factory=lambda: Vector3(0.0, 0.0, 0.0),
    )
    """
    Where the first point starts in the anchor frame, in metres.
    """

    anchor_rotation: Vector3 = document_field(
        CableConfigurationKey.ANCHOR_ROTATION,
        default_factory=lambda: Vector3(0.0, 0.0, 0.0),
    )
    """
    The cable's initial roll, pitch and yaw in the anchor frame, in radians; without
    rotation the cable runs along the anchor's x axis.
    """

    friction: ContactFriction = document_field(
        CableConfigurationKey.FRICTION,
        default_factory=lambda: ContactFriction(1.0, 0.005, 0.0001),
    )
    """
    The friction of the cable's and the pads' contacts.
    """

    contact_dimension: int = document_field(
        CableConfigurationKey.CONTACT_DIMENSION, default=6
    )
    """
    MuJoCo's contact dimensionality: 1, 3, 4 or 6.
    """

    solver_reference: SolverReference = document_field(
        CableConfigurationKey.SOLVER_REFERENCE,
        default_factory=lambda: SolverReference(0.005, 1.0),
    )
    """
    How fast and how damped contacts are resolved.
    """

    solver_impedance: SolverImpedance = document_field(
        CableConfigurationKey.SOLVER_IMPEDANCE,
        default_factory=lambda: SolverImpedance(0.95, 0.99, 0.001, 0.5, 2.0),
    )
    """
    How stiff contacts are over their penetration depth.
    """

    def __post_init__(self) -> None:
        self.require(
            MINIMUM_SEGMENT_COUNT <= self.segment_count <= MAXIMUM_SEGMENT_COUNT,
            CableConfigurationKey.SEGMENT_COUNT,
            f"from {MINIMUM_SEGMENT_COUNT} to {MAXIMUM_SEGMENT_COUNT} elements",
        )
        for key, value, maximum in (
            (CableConfigurationKey.SEGMENT_LENGTH, self.segment_length, math.inf),
            (CableConfigurationKey.RADIUS, self.radius, MAXIMUM_RADIUS),
            (CableConfigurationKey.MASS, self.mass, MAXIMUM_MASS),
        ):
            self.require(
                math.isfinite(value) and 0 < value <= maximum,
                key,
                f"positive and at most {maximum}",
            )
        self.require(
            self.length() <= MAXIMUM_CABLE_LENGTH,
            CableConfigurationKey.SEGMENT_LENGTH,
            f"a cable of at most {MAXIMUM_CABLE_LENGTH} m",
        )
        for key, value in (
            (CableConfigurationKey.BEND, self.bend),
            (CableConfigurationKey.TWIST, self.twist),
        ):
            self.require(math.isfinite(value) and value >= 0, key, "finite, 0 or more")
        for key, numbers in (
            (CableConfigurationKey.ANCHOR_OFFSET, self.anchor_offset),
            (CableConfigurationKey.ANCHOR_ROTATION, self.anchor_rotation),
            (CableConfigurationKey.SOLVER_REFERENCE, self.solver_reference),
        ):
            self.require(
                all(math.isfinite(value) for value in numbers.to_json()),
                key,
                "finite numbers",
            )
        self.require(
            all(0 <= value <= 1 for value in self.color.to_json()),
            CableConfigurationKey.COLOR,
            "channels from 0 to 1",
        )
        self.require(
            all(
                math.isfinite(value) and value >= 0 for value in self.friction.to_json()
            ),
            CableConfigurationKey.FRICTION,
            "finite coefficients, 0 or more",
        )
        self.require(
            self.contact_dimension in CONTACT_DIMENSIONS,
            CableConfigurationKey.CONTACT_DIMENSION,
            f"one of {CONTACT_DIMENSIONS}",
        )
        self.require(
            self.solver_reference.time_constant > 0,
            CableConfigurationKey.SOLVER_REFERENCE,
            "a positive time constant",
        )
        self.require(
            self.solver_impedance.is_valid(),
            CableConfigurationKey.SOLVER_IMPEDANCE,
            "0 < minimum <= maximum < 1, a positive width, a midpoint between 0 and "
            "1 and a power of 1 or more",
        )

    @staticmethod
    def require(condition: bool, key: CableConfigurationKey, reason: str) -> None:
        """
        :param condition: Whether the value fits.
        :param key: The key of the value.
        :param reason: What fits.
        :raises InvalidCableConfiguration: When the condition does not hold.
        """
        if not condition:
            raise InvalidCableConfiguration(key, reason)

    def length(self) -> float:
        """
        :return: The cable's length, in metres.
        """
        return self.segment_count * self.segment_length


# %% gripper commands


class GripperAction(StrEnum):
    """
    The operations of the cable lab's parallel friction gripper.
    """

    PINCH = "pinch"
    """
    Closes the pads with force-limited actuators.
    """

    RELEASE = "release"
    """
    Opens the pads.
    """

    LIFT = "lift"
    """
    Raises the gripper's target.
    """

    LOWER = "lower"
    """
    Lowers the gripper's target.
    """

    MOVE = "move"
    """
    Sets the gripper's target position.
    """


class GripperCommandKey(StrEnum):
    """
    The keys of a gripper command.
    """

    ACTION = "action"
    """
    A :class:`GripperAction` value.
    """

    POSITION = "position"
    """
    The target position of a move.
    """


@dataclass
class InvalidGripperCommand(ProtocolError):
    """
    A move without a position, or another action with one.
    """

    action: GripperAction
    """
    The command's action.
    """

    def message(self) -> str:
        if self.action is GripperAction.MOVE:
            return "A gripper move needs a finite position."
        return f"The gripper action {self.action.value!r} takes no position."


@dataclass(kw_only=True)
class GripperCommand(JsonDocument):
    """
    One operation of the gripper; only a move names a position.
    """

    action: GripperAction = document_field(GripperCommandKey.ACTION)
    """
    The operation.
    """

    position: Optional[Vector3] = document_field(
        GripperCommandKey.POSITION, default=None
    )
    """
    The gripper's target in the world, in metres, for a move.
    """

    def __post_init__(self) -> None:
        moving = self.action is GripperAction.MOVE
        if moving != (self.position is not None):
            raise InvalidGripperCommand(self.action)
        if moving and not all(
            math.isfinite(value) for value in self.position.to_json()
        ):
            raise InvalidGripperCommand(self.action)


# %% measured state


class SimulationLifecycle(StrEnum):
    """
    Whether the cable lab's simulation runs.
    """

    IDLE = "idle"
    """
    No simulation advances.
    """

    RUNNING = "running"
    """
    The simulation advances in the background.
    """

    FAILED = "failed"
    """
    The simulation could not start or stopped by itself.
    """


class GraspState(StrEnum):
    """
    What the pads' contacts tell about the pinch.
    """

    OPEN = "open"
    """
    The pads are commanded open.
    """

    CONTACT = "contact"
    """
    One pad touches the cable.
    """

    HOLDING = "holding"
    """
    Both pads touch the cable and it hardly moves against them.
    """

    SLIPPING = "slipping"
    """
    The closed pads hold no two-sided contact, or the cable moves against them.
    """


class CableLabKey(StrEnum):
    """
    The keys of the cable lab's measured state and its parts.
    """

    LIFECYCLE = "lifecycle"
    """
    A :class:`SimulationLifecycle` value.
    """

    ERROR = "error"
    """
    Why the simulation failed.
    """

    SIMULATION_TIME = "simulationTime"
    """
    The simulated time.
    """

    CONFIGURATION = "configuration"
    """
    The configuration of the built cable.
    """

    SEGMENTS = "segments"
    """
    The physical capsules.
    """

    POINTS = "points"
    """
    The semantic points.
    """

    GRIPPER = "gripper"
    """
    The gripper.
    """

    CONTACTS = "contacts"
    """
    The cable's contacts.
    """

    ANCHOR = "anchor"
    """
    The cable's first point.
    """

    GRASP = "grasp"
    """
    The pinch.
    """

    WARNINGS = "warnings"
    """
    Diagnostics.
    """

    SUPPORT = "support"
    """
    The rail the cable starts on.
    """

    NAME = "name"
    """
    A body's or a point's name.
    """

    START = "start"
    """
    A capsule's first end.
    """

    END = "end"
    """
    A capsule's second end.
    """

    POSITION = "position"
    """
    A position.
    """

    POSE = "pose"
    """
    A box's pose.
    """

    SIZE = "size"
    """
    A box's full size.
    """

    OPENING = "opening"
    """
    The distance between the pads' inner faces.
    """

    PADS = "pads"
    """
    The gripper's pads.
    """

    NORMAL_FORCE = "normalForce"
    """
    A compressive force.
    """

    FRICTION_FORCE = "frictionForce"
    """
    A tangential force.
    """

    BODY_A = "bodyA"
    """
    A contact's first body.
    """

    BODY_B = "bodyB"
    """
    A contact's second body.
    """

    ENABLED = "enabled"
    """
    Whether the anchor pins the cable.
    """

    STATE = "state"
    """
    A :class:`GraspState` value.
    """

    CONTACT_COUNT = "contactCount"
    """
    The number of force-bearing pad contacts.
    """


@dataclass(kw_only=True)
class CableSegment(JsonDocument):
    """
    One physical capsule of the cable, by the ends of its centre line.
    """

    name: str = document_field(CableLabKey.NAME)
    """
    The capsule's body name.
    """

    start: Vector3 = document_field(CableLabKey.START)
    """
    The centre line's first end, in metres.
    """

    end: Vector3 = document_field(CableLabKey.END)
    """
    The centre line's second end, in metres.
    """


@dataclass(kw_only=True)
class CablePoint(JsonDocument):
    """
    One semantic point of the cable, where its world body is.
    """

    name: str = document_field(CableLabKey.NAME)
    """
    The point's body name in the semantic world.
    """

    position: Vector3 = document_field(CableLabKey.POSITION)
    """
    The point's position, in metres.
    """


@dataclass(kw_only=True)
class OrientedBox(JsonDocument):
    """
    A box at a pose.
    """

    pose: Pose = document_field(CableLabKey.POSE)
    """
    The box centre's pose.
    """

    size: Vector3 = document_field(CableLabKey.SIZE)
    """
    The box's full size, in metres.
    """


@dataclass(kw_only=True)
class GripperObservation(JsonDocument):
    """
    The measured gripper.
    """

    position: Vector3 = document_field(CableLabKey.POSITION)
    """
    The carriage's position, in metres.
    """

    opening: float = document_field(CableLabKey.OPENING)
    """
    The distance between the pads' inner faces, in metres.
    """

    pads: List[OrientedBox] = document_field(CableLabKey.PADS)
    """
    The two pads.
    """


@dataclass(kw_only=True)
class CableContact(JsonDocument):
    """
    One contact of the cable with its measured forces.
    """

    position: Vector3 = document_field(CableLabKey.POSITION)
    """
    Where the bodies touch, in metres.
    """

    normal_force: float = document_field(CableLabKey.NORMAL_FORCE)
    """
    The compressive force, in newtons.
    """

    friction_force: float = document_field(CableLabKey.FRICTION_FORCE)
    """
    The tangential force's magnitude, in newtons.
    """

    body_a: str = document_field(CableLabKey.BODY_A)
    """
    The first body's name.
    """

    body_b: str = document_field(CableLabKey.BODY_B)
    """
    The second body's name.
    """


@dataclass(kw_only=True)
class AnchorObservation(JsonDocument):
    """
    The cable's first point.
    """

    position: Vector3 = document_field(CableLabKey.POSITION)
    """
    Where the first point is, in metres.
    """

    enabled: bool = document_field(CableLabKey.ENABLED)
    """
    Whether a ball joint pins it.
    """


@dataclass(kw_only=True)
class GraspObservation(JsonDocument):
    """
    The pinch, from the pads' measured contacts.
    """

    state: GraspState = document_field(CableLabKey.STATE)
    """
    What the contacts tell.
    """

    normal_force: float = document_field(CableLabKey.NORMAL_FORCE)
    """
    The pads' summed compressive force on the cable, in newtons.
    """

    friction_force: float = document_field(CableLabKey.FRICTION_FORCE)
    """
    The pads' summed tangential force on the cable, in newtons.
    """

    contact_count: int = document_field(CableLabKey.CONTACT_COUNT)
    """
    The number of force-bearing pad contacts.
    """


@dataclass(kw_only=True)
class CableLabState(JsonDocument):
    """
    The cable lab's lifecycle and, once a cable is built, what its simulation measures.
    """

    lifecycle: SimulationLifecycle = document_field(CableLabKey.LIFECYCLE)
    """
    Whether the simulation runs.
    """

    error: Optional[str] = document_field(CableLabKey.ERROR, default=None)
    """
    Why the simulation failed.
    """

    simulation_time: Optional[float] = document_field(
        CableLabKey.SIMULATION_TIME, default=None
    )
    """
    The simulated time, in seconds; None without a cable.
    """

    configuration: Optional[CableConfiguration] = document_field(
        CableLabKey.CONFIGURATION, default=None
    )
    """
    The configuration the cable was built from; None without a cable.
    """

    segments: List[CableSegment] = document_field(
        CableLabKey.SEGMENTS, default_factory=list
    )
    """
    The physical capsules.
    """

    points: List[CablePoint] = document_field(CableLabKey.POINTS, default_factory=list)
    """
    The semantic points, one per capsule.
    """

    gripper: Optional[GripperObservation] = document_field(
        CableLabKey.GRIPPER, default=None
    )
    """
    The measured gripper.
    """

    contacts: List[CableContact] = document_field(
        CableLabKey.CONTACTS, default_factory=list
    )
    """
    Every contact of the cable.
    """

    anchor: Optional[AnchorObservation] = document_field(
        CableLabKey.ANCHOR, default=None
    )
    """
    The cable's first point.
    """

    grasp: Optional[GraspObservation] = document_field(CableLabKey.GRASP, default=None)
    """
    The pinch.
    """

    warnings: List[str] = document_field(CableLabKey.WARNINGS, default_factory=list)
    """
    MuJoCo's numerical warnings.
    """

    support: Optional[OrientedBox] = document_field(CableLabKey.SUPPORT, default=None)
    """
    The rail the cable starts on.
    """

    def is_commandable(self) -> bool:
        """
        :return: Whether the gripper takes commands: a cable is simulated.
        """
        return self.lifecycle is SimulationLifecycle.RUNNING
