"""
Liquid in the laboratory's vessels: a reduced free-surface model driven by the vessels'
measured motion.

Each vessel holds a volume whose surface stays a plane: gravity and the vessel's
acceleration tilt it, a damped oscillation lets it slosh. When the surface rises above
the lowest point of the rim, liquid flows out there and flies as separate portions; a
portion that falls through another vessel's opening is caught, one that reaches the
worktop or the floor becomes a puddle. Every millilitre is accounted for. Pressure,
wetting, mixing in space and chemistry are not modelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil, pi, sqrt

import numpy as np
from typing_extensions import Dict, List, Mapping, Optional

from cramera_laboratory.exceptions import (
    NonFiniteValue,
    UnknownObject,
    ValueOutOfRange,
)
from cramera_laboratory.geometry import RigidPose, vector_of
from cramera_protocol.laboratory.layout import LinearColor
from cramera_protocol.laboratory.physics import (
    Droplet,
    LiquidState,
    Puddle,
    VesselInterior,
    VesselLiquid,
)

MILLILITRES_PER_CUBIC_METRE = 1_000_000.0
"""
How many millilitres a cubic metre holds.
"""

UP = np.array([0.0, 0.0, 1.0])
"""
The laboratory's upward direction.
"""

BISECTION_STEPS = 28
"""
How many halvings locate a free surface; enough for sub-micrometre precision in a
vessel.
"""

LEVEL_SURFACE = 1e-10
"""
How small a surface normal's horizontal part may be to count as level.
"""

LARGEST_DIVISOR = 1e-12
"""
The smallest distance a crossing is computed over, against division by zero.
"""


class Quantity(StrEnum):
    """
    The quantities liquid requests give.
    """

    VOLUME = "liquid volume"
    """
    An amount of liquid.
    """

    DURATION = "liquid duration"
    """
    A span of simulated time.
    """


class ObjectRole(StrEnum):
    """
    What an object was asked to be.
    """

    VESSEL = "vessel"
    """
    An object that holds liquid.
    """


# %% vessel interior


@dataclass
class VesselShape:
    """
    The inside of a vessel in its own frame: a half sphere at the bottom under a
    cylinder that is open at the rim, its axis the frame's z axis.
    """

    radius: float = 0.0077
    """
    The inner radius, in metres.
    """

    bottom: float = 0.0013
    """
    The lowest inner point above the vessel's origin, in metres.
    """

    rim: float = 0.149
    """
    The rim's height above the vessel's origin, in metres.
    """

    integration_order: int = 64
    """
    How many Gauss–Legendre nodes integrate each of the two parts.
    """

    heights: np.ndarray = field(init=False, repr=False)
    """
    The heights of the integrated cross sections.
    """

    radii: np.ndarray = field(init=False, repr=False)
    """
    The inner radius at each height.
    """

    weights: np.ndarray = field(init=False, repr=False)
    """
    The volume each full cross section stands for, in millilitres.
    """

    def __post_init__(self) -> None:
        nodes, weights = np.polynomial.legendre.leggauss(self.integration_order)
        bottom_heights = self.bottom + (nodes + 1) * self.radius / 2
        wall_heights = self.center + (nodes + 1) * (self.rim - self.center) / 2
        self.heights = np.concatenate((bottom_heights, wall_heights))
        self.radii = np.concatenate(
            (
                np.sqrt(self.radius**2 - (bottom_heights - self.center) ** 2),
                np.full_like(nodes, self.radius),
            )
        )
        lengths = np.concatenate(
            (weights * self.radius / 2, weights * (self.rim - self.center) / 2)
        )
        self.weights = lengths * pi * self.radii**2 * MILLILITRES_PER_CUBIC_METRE

    @property
    def center(self) -> float:
        """
        The height of the bottom sphere's centre.
        """
        return self.bottom + self.radius

    @property
    def capacity(self) -> float:
        """
        The volume up to the rim, in millilitres.
        """
        return (
            pi * self.radius**2 * (self.rim - self.center) + 2 * pi * self.radius**3 / 3
        ) * MILLILITRES_PER_CUBIC_METRE

    def upright_volume(self, height: float) -> float:
        """
        :param height: A level in the vessel's frame.
        :return: The volume below it while the vessel stands upright, in millilitres.
        """
        cap_height = min(max(height - self.bottom, 0.0), self.radius)
        cap = pi * cap_height**2 * (self.radius - cap_height / 3)
        cylinder = pi * self.radius**2 * max(0.0, min(height, self.rim) - self.center)
        return (cap + cylinder) * MILLILITRES_PER_CUBIC_METRE

    def volume_below(self, normal: np.ndarray, offset: float) -> float:
        """
        :param normal: A unit plane normal in the vessel's frame.
        :param offset: The plane's offset along the normal.
        :return: The inner volume on the plane's lower side, in millilitres.
        """
        horizontal = float(np.linalg.norm(normal[:2]))
        if horizontal < LEVEL_SURFACE:
            if normal[2] >= 0:
                return self.upright_volume(offset)
            return self.capacity - self.upright_volume(-offset)
        cut = np.clip(
            (offset - normal[2] * self.heights) / (horizontal * self.radii), -1.0, 1.0
        )
        fractions = (
            np.arcsin(cut) + cut * np.sqrt(np.maximum(0.0, 1 - cut**2)) + pi / 2
        ) / pi
        return float(self.weights @ fractions)

    def surface_offset(self, normal: np.ndarray, volume: float) -> float:
        """
        :param normal: The surface's unit normal in the vessel's frame.
        :param volume: The volume held, in millilitres.
        :return: The offset of the plane that holds exactly that volume below it.
        """
        horizontal = float(np.linalg.norm(normal[:2]))
        ends = (normal[2] * self.bottom, normal[2] * self.rim)
        lower = min(ends) - horizontal * self.radius
        upper = max(ends) + horizontal * self.radius
        if volume <= 0:
            return float(lower)
        if volume >= self.capacity:
            return float(upper)
        for _ in range(BISECTION_STEPS):
            middle = (lower + upper) / 2
            if self.volume_below(normal, middle) < volume:
                lower = middle
            else:
                upper = middle
        return float((lower + upper) / 2)

    def lowest_lip(self, normal: np.ndarray) -> np.ndarray:
        """
        :param normal: The surface's unit normal in the vessel's frame.
        :return: The rim point a rising surface reaches first.
        """
        horizontal = float(np.linalg.norm(normal[:2]))
        radial = (
            -self.radius * normal[:2] / horizontal
            if horizontal > LEVEL_SURFACE
            else np.zeros(2)
        )
        return np.array([*radial, self.rim])

    def document(self) -> VesselInterior:
        """
        :return: The interior as the browser reads it.
        """
        return VesselInterior(
            radius=self.radius, bottom=self.bottom, rim=self.rim, capacity=self.capacity
        )


# %% parameters


@dataclass(frozen=True)
class LiquidParameters:
    """
    The liquid model's settings, in SI units.
    """

    gravity: float = 9.81
    """
    The downward acceleration, in metres per second squared.
    """

    maximum_step: float = 0.02
    """
    The longest integration step, in seconds.
    """

    maximum_duration: float = 1.0
    """
    The longest span one call advances, in seconds.
    """

    slosh_frequency: float = 14.0
    """
    The angular frequency of the surface's damped tilt oscillation, in radians per
    second.
    """

    slosh_damping: float = 5.0
    """
    The decay rate of the surface's tilting speed, per second.
    """

    acceleration_limit: float = 20.0
    """
    The largest vessel acceleration per axis the surface follows, in metres per second
    squared.
    """

    velocity_limit: float = 2.0
    """
    The largest vessel speed per axis passed on to outflowing liquid, in metres per
    second.
    """

    slope_limit: float = 1.5
    """
    The largest surface slope against the horizontal.
    """

    discharge: float = 0.32
    """
    The share of the opening's full flow that overflow reaches.
    """

    worktop_height: float = 0.9
    """
    The height of the worktop surface, in metres.
    """

    worktop_half_width: float = 0.9
    """
    Half the worktop's extent along x, in metres.
    """

    worktop_half_depth: float = 0.375
    """
    Half the worktop's extent along y, in metres.
    """

    puddle_merge_distance: float = 0.03
    """
    How close a landing portion must be to a puddle to join it, in metres.
    """

    puddle_lift: float = 0.0005
    """
    How far above its surface a puddle is drawn, in metres.
    """


# %% initial fills


@dataclass(frozen=True)
class InitialFill:
    """
    What a vessel holds when the laboratory starts.
    """

    level: float
    """
    The height the upright liquid reaches in the vessel's frame, in metres; the
    interior's bottom for an empty vessel.
    """

    color: LinearColor
    """
    The liquid's colour.
    """


class LaboratoryVessel(StrEnum):
    """
    The glass vessels of the laboratory.
    """

    CLEAR = "tube_clear"
    """
    The empty clear vessel.
    """

    AMBER = "tube_amber"
    """
    The vessel of amber liquid.
    """

    TEAL = "tube_teal"
    """
    The vessel of teal liquid.
    """

    RESERVE = "tube_reserve"
    """
    The empty reserve vessel.
    """


CLEAR_LIQUID = LinearColor(0.22, 0.65, 0.86)
"""
The colour liquid poured into an empty vessel starts mixing from.
"""

AMBER_LIQUID = LinearColor(0.82, 0.32, 0.055)
"""
The amber sample's colour.
"""

TEAL_LIQUID = LinearColor(0.12, 0.56, 0.52)
"""
The teal sample's colour.
"""

AMBER_LEVEL = 0.074
"""
The height the amber sample reaches in its vessel, in metres.
"""

TEAL_LEVEL = 0.095
"""
The height the teal sample reaches in its vessel, in metres.
"""


def laboratory_fills(shape: VesselShape) -> Dict[str, InitialFill]:
    """
    :param shape: The vessels' interior.
    :return: What each vessel of the laboratory holds at the start.
    """
    return {
        LaboratoryVessel.CLEAR: InitialFill(shape.bottom, CLEAR_LIQUID),
        LaboratoryVessel.AMBER: InitialFill(AMBER_LEVEL, AMBER_LIQUID),
        LaboratoryVessel.TEAL: InitialFill(TEAL_LEVEL, TEAL_LIQUID),
        LaboratoryVessel.RESERVE: InitialFill(shape.bottom, CLEAR_LIQUID),
    }


# %% state


@dataclass
class VesselContent:
    """
    The liquid in one vessel and its free surface.
    """

    volume: float
    """
    The amount held, in millilitres.
    """

    color: np.ndarray
    """
    The liquid's linear colour, mixed by volume.
    """

    pose: RigidPose
    """
    The vessel's measured pose.
    """

    normal: np.ndarray
    """
    The surface's upward unit normal in the vessel's frame.
    """

    offset: float
    """
    The surface plane's offset along the normal, in metres.
    """

    slope: np.ndarray = field(default_factory=lambda: np.zeros(2))
    """
    The surface's slope along the laboratory's x and y axes.
    """

    slope_velocity: np.ndarray = field(default_factory=lambda: np.zeros(2))
    """
    How fast the slope changes, per second.
    """

    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    """
    The vessel's measured velocity, in metres per second.
    """

    def accept(self, volume: float, color: np.ndarray, capacity: float) -> float:
        """
        Take in as much liquid as fits.

        :param volume: The liquid offered, in millilitres.
        :param color: Its colour.
        :param capacity: The vessel's capacity, in millilitres.
        :return: The amount taken, in millilitres.
        """
        accepted = min(volume, max(0.0, capacity - self.volume))
        if accepted <= 0:
            return 0.0
        total = self.volume + accepted
        self.color = (self.color * self.volume + color * accepted) / total
        self.volume = total
        return accepted


@dataclass
class LiquidPortion:
    """
    A portion of liquid in flight.
    """

    source: str
    """
    The vessel it left.
    """

    position: np.ndarray
    """
    Where it is, in metres.
    """

    velocity: np.ndarray
    """
    How fast it moves, in metres per second.
    """

    volume: float
    """
    Its amount, in millilitres.
    """

    color: np.ndarray
    """
    Its colour.
    """

    emitted_at: float
    """
    When it left its vessel, in seconds of liquid time.
    """


@dataclass
class LiquidPool:
    """
    Spilled liquid lying on a surface.
    """

    position: np.ndarray
    """
    Its centre, in metres.
    """

    volume: float
    """
    Its amount, in millilitres.
    """

    color: np.ndarray
    """
    Its colour, mixed by volume.
    """

    def accept(self, portion: LiquidPortion) -> None:
        """
        :param portion: A portion landing on the puddle.
        """
        total = self.volume + portion.volume
        self.color = (self.color * self.volume + portion.color * portion.volume) / total
        self.position[:2] = (
            self.position[:2] * self.volume + portion.position[:2] * portion.volume
        ) / total
        self.volume = total


# %% model


@dataclass
class LaboratoryLiquid:
    """
    The liquid of every vessel, the portions in flight and the puddles.
    """

    fills: Mapping[str, InitialFill]
    """
    What each vessel holds at the start, by the vessel's key.
    """

    shape: VesselShape = field(default_factory=VesselShape)
    """
    The interior every vessel shares.
    """

    parameters: LiquidParameters = field(default_factory=LiquidParameters)
    """
    The model's settings.
    """

    vessels: Dict[str, VesselContent] = field(init=False, default_factory=dict)
    """
    The liquid in each vessel.
    """

    portions: List[LiquidPortion] = field(init=False, default_factory=list)
    """
    The liquid in flight.
    """

    pools: List[LiquidPool] = field(init=False, default_factory=list)
    """
    The spilled liquid.
    """

    supplied: float = field(init=False, default=0.0)
    """
    How much liquid entered the laboratory since the last reset, in millilitres.
    """

    time: float = field(init=False, default=0.0)
    """
    The liquid time since the last reset, in seconds.
    """

    def reset(self, poses: Mapping[str, RigidPose]) -> None:
        """
        Restore every vessel's initial fill and clear what flies and lies.

        :param poses: The vessels' measured poses.
        """
        self.vessels = {
            key: self.content(fill, poses[key]) for key, fill in self.fills.items()
        }
        self.portions = []
        self.pools = []
        self.time = 0.0
        self.supplied = sum(content.volume for content in self.vessels.values())

    def content(self, fill: InitialFill, pose: RigidPose) -> VesselContent:
        """
        :param fill: A vessel's initial fill.
        :param pose: The vessel's pose.
        :return: The vessel's liquid, level under gravity.
        """
        volume = self.shape.upright_volume(fill.level)
        normal = pose.rotation.T @ UP
        return VesselContent(
            volume=volume,
            color=np.array(fill.color.to_json()),
            pose=pose,
            normal=normal,
            offset=self.shape.surface_offset(normal, volume),
        )

    def vessel(self, key: str) -> VesselContent:
        """
        :param key: A vessel's key.
        :return: Its liquid.
        :raises UnknownObject: When no vessel has the key.
        """
        if key not in self.vessels:
            raise UnknownObject(key, ObjectRole.VESSEL)
        return self.vessels[key]

    def fill(self, key: str, volume: float) -> None:
        """
        Set what a vessel holds; the difference enters or leaves the laboratory.

        :param key: The vessel's key.
        :param volume: The amount it holds afterwards, in millilitres.
        :raises UnknownObject: When no vessel has the key.
        :raises NonFiniteValue: When the volume is not finite.
        :raises ValueOutOfRange: When the volume is negative or exceeds the capacity.
        """
        content = self.vessel(key)
        if not np.isfinite(volume):
            raise NonFiniteValue(Quantity.VOLUME)
        if not 0 <= volume <= self.shape.capacity:
            raise ValueOutOfRange(Quantity.VOLUME, volume, 0.0, self.shape.capacity)
        self.supplied += volume - content.volume
        content.volume = float(volume)
        content.offset = self.shape.surface_offset(content.normal, content.volume)

    def supply(self, key: str, volume: float, color: np.ndarray) -> float:
        """
        Pour new liquid into a vessel, as a dispenser does.

        :param key: The vessel's key.
        :param volume: The amount offered, in millilitres.
        :param color: Its colour.
        :return: The amount the vessel took, in millilitres.
        """
        content = self.vessel(key)
        accepted = content.accept(volume, color, self.shape.capacity)
        self.supplied += accepted
        content.offset = self.shape.surface_offset(content.normal, content.volume)
        return accepted

    def step(self, duration: float, poses: Mapping[str, RigidPose]) -> None:
        """
        Advance the liquid while the vessels moved to new measured poses.

        :param duration: The simulated time since the previous step, in seconds.
        :param poses: The vessels' measured poses now.
        :raises ValueOutOfRange: When the duration is negative or too long.
        """
        if not 0 <= duration <= self.parameters.maximum_duration:
            raise ValueOutOfRange(
                Quantity.DURATION, duration, 0.0, self.parameters.maximum_duration
            )
        if duration == 0:
            return
        previous = {key: content.pose for key, content in self.vessels.items()}
        steps = max(1, ceil(duration / self.parameters.maximum_step))
        for index in range(steps):
            fraction = (index + 1) / steps
            between = {
                key: pose.moved_to(
                    previous[key].position * (1 - fraction) + pose.position * fraction
                )
                for key, pose in ((key, poses[key]) for key in self.vessels)
            }
            self.advance(duration / steps, between)

    def advance(self, duration: float, poses: Mapping[str, RigidPose]) -> None:
        """
        :param duration: One integration step, in seconds.
        :param poses: The vessels' poses at its end.
        """
        previous = {key: content.pose for key, content in self.vessels.items()}
        for key, content in self.vessels.items():
            self.move_surface(content, poses[key], duration)
            self.overflow(key, content, duration)
        flying = []
        for portion in self.portions:
            start = portion.position.copy()
            portion.position += portion.velocity * duration
            portion.position[2] -= self.parameters.gravity * duration**2 / 2
            portion.velocity[2] -= self.parameters.gravity * duration
            self.catch(portion, start, previous)
            if portion.volume <= 0 or self.land(portion, start):
                continue
            flying.append(portion)
        self.portions = flying
        for content in self.vessels.values():
            content.offset = self.shape.surface_offset(content.normal, content.volume)
        self.time += duration

    def move_surface(
        self, content: VesselContent, pose: RigidPose, duration: float
    ) -> None:
        """
        Tilt a vessel's surface by its measured acceleration.

        :param content: The vessel's liquid.
        :param pose: The vessel's new pose.
        :param duration: The step, in seconds.
        """
        parameters = self.parameters
        velocity = np.clip(
            (pose.position - content.pose.position) / duration,
            -parameters.velocity_limit,
            parameters.velocity_limit,
        )
        acceleration = np.clip(
            (velocity - content.velocity) / duration,
            -parameters.acceleration_limit,
            parameters.acceleration_limit,
        )
        target = np.clip(
            acceleration[:2]
            / max(parameters.gravity + acceleration[2], parameters.gravity / 2),
            -parameters.slope_limit,
            parameters.slope_limit,
        )
        content.slope_velocity += (
            parameters.slosh_frequency**2 * (target - content.slope)
            - 2 * parameters.slosh_damping * content.slope_velocity
        ) * duration
        content.slope = np.clip(
            content.slope + content.slope_velocity * duration,
            -parameters.slope_limit,
            parameters.slope_limit,
        )
        world_normal = np.array([*content.slope, 1.0])
        world_normal /= np.linalg.norm(world_normal)
        content.pose = pose
        content.velocity = velocity
        content.normal = pose.rotation.T @ world_normal
        content.offset = self.shape.surface_offset(content.normal, content.volume)

    def overflow(self, key: str, content: VesselContent, duration: float) -> None:
        """
        Let liquid above the lowest rim point flow out as a new portion.

        :param key: The vessel's key.
        :param content: The vessel's liquid.
        :param duration: The step, in seconds.
        """
        if content.volume <= 0:
            return
        lip = self.shape.lowest_lip(content.normal)
        lip_offset = float(content.normal @ lip)
        retained = self.shape.volume_below(content.normal, lip_offset)
        excess = max(0.0, content.volume - retained)
        head = max(0.0, content.offset - lip_offset)
        speed = sqrt(2 * self.parameters.gravity * head)
        flow = (
            self.parameters.discharge
            * pi
            * self.shape.radius**2
            * speed
            * MILLILITRES_PER_CUBIC_METRE
        )
        emitted = min(excess, flow * duration)
        if emitted <= 0:
            return
        direction = lip.copy()
        direction[2] = 0.0
        direction /= max(float(np.linalg.norm(direction)), self.shape.radius)
        velocity = content.velocity + content.pose.rotation @ direction * speed / 2
        content.volume -= emitted
        self.portions.append(
            LiquidPortion(
                source=key,
                position=content.pose.point_in_world(lip),
                velocity=velocity.copy(),
                volume=emitted,
                color=content.color.copy(),
                emitted_at=self.time,
            )
        )

    def catch(
        self,
        portion: LiquidPortion,
        start: np.ndarray,
        previous: Mapping[str, RigidPose],
    ) -> None:
        """
        Let another vessel take a portion that fell through its opening.

        :param portion: The portion, already moved.
        :param start: Where it was before the step.
        :param previous: The vessels' poses before the step.
        """
        for key, content in self.vessels.items():
            if key == portion.source or portion.volume <= 0:
                continue
            before = previous[key].point_in_body(start)
            after = content.pose.point_in_body(portion.position)
            if before[2] <= self.shape.rim or after[2] > self.shape.rim:
                continue
            fraction = (before[2] - self.shape.rim) / (before[2] - after[2])
            crossing = before + (after - before) * fraction
            if np.linalg.norm(crossing[:2]) > self.shape.radius:
                continue
            portion.volume -= content.accept(
                portion.volume, portion.color, self.shape.capacity
            )

    def land(self, portion: LiquidPortion, start: np.ndarray) -> bool:
        """
        Turn a portion that reached the worktop or the floor into a puddle.

        :param portion: The portion, already moved.
        :param start: Where it was before the step.
        :return: Whether it landed.
        """
        parameters = self.parameters
        for height in (parameters.worktop_height, 0.0):
            if start[2] < height or portion.position[2] > height:
                continue
            fraction = (start[2] - height) / max(
                start[2] - portion.position[2], LARGEST_DIVISOR
            )
            crossing = start + (portion.position - start) * fraction
            if height > 0 and (
                abs(crossing[0]) > parameters.worktop_half_width
                or abs(crossing[1]) > parameters.worktop_half_depth
            ):
                continue
            portion.position = crossing
            portion.position[2] = height + parameters.puddle_lift
            pool = self.nearest_pool(portion.position)
            if pool is None:
                self.pools.append(
                    LiquidPool(
                        portion.position.copy(), portion.volume, portion.color.copy()
                    )
                )
            else:
                pool.accept(portion)
            return True
        return False

    def nearest_pool(self, position: np.ndarray) -> Optional[LiquidPool]:
        """
        :param position: Where a portion lands.
        :return: The first puddle close enough to join, None when there is none.
        """
        for pool in self.pools:
            if (
                np.linalg.norm(pool.position - position)
                <= self.parameters.puddle_merge_distance
            ):
                return pool
        return None

    def state(self) -> LiquidState:
        """
        :return: Where the liquid is, as the browser reads it.
        """
        return LiquidState(
            time=self.time,
            vessels={
                key: VesselLiquid(
                    volume=content.volume,
                    color=LinearColor(*(float(value) for value in content.color)),
                    normal=vector_of(content.normal),
                    offset=content.offset,
                )
                for key, content in self.vessels.items()
            },
            droplets=[
                Droplet(
                    source=portion.source,
                    position=vector_of(portion.position),
                    velocity=vector_of(portion.velocity),
                    volume=portion.volume,
                    color=LinearColor(*(float(value) for value in portion.color)),
                    emitted_at=portion.emitted_at,
                )
                for portion in self.portions
            ],
            puddles=[
                Puddle(
                    position=vector_of(pool.position),
                    volume=pool.volume,
                    color=LinearColor(*(float(value) for value in pool.color)),
                )
                for pool in self.pools
            ],
            supplied=self.supplied,
        )

    def total(self) -> float:
        """
        :return: The liquid in vessels, in flight and spilled, in millilitres.
        """
        return (
            sum(content.volume for content in self.vessels.values())
            + sum(portion.volume for portion in self.portions)
            + sum(pool.volume for pool in self.pools)
        )
