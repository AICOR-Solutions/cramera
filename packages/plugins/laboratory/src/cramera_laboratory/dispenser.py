"""
The dispensing station: two reagent reservoirs that empty through a common nozzle into
the vessel standing beneath it.

A dose flows only while the measured receiver stands upright under the nozzle, open,
with room for the liquid; otherwise it stops and says why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from typing_extensions import Dict, FrozenSet, Mapping, Optional

from cramera_laboratory.exceptions import (
    OperationRefused,
    Refusal,
    UnknownObject,
    ValueOutOfRange,
)
from cramera_laboratory.geometry import RigidPose
from cramera_laboratory.liquid import AMBER_LIQUID, TEAL_LIQUID, LaboratoryLiquid
from cramera_protocol.laboratory.layout import (
    DispenserLayout,
    LinearColor,
    StopperLayout,
)
from cramera_protocol.laboratory.physics import (
    DispenserAction,
    DispenserRequest,
    DispenserState,
    DispenserStatus,
    DoseLimits,
    Reagent,
    ReservoirLevel,
)

VOLUME_TOLERANCE = 1e-10
"""
How close two volumes count as equal, in millilitres.
"""

RIM_CLEARANCE_RADII = 2
"""
How many inner radii around the axis a stopper must lie within to close a vessel.
"""


class Quantity(StrEnum):
    """
    The quantities a dispenser request gives.
    """

    DOSE = "dose"
    """
    A dose in millilitres.
    """


class ObjectRole(StrEnum):
    """
    What an object was asked to be.
    """

    CHANNEL = "reagent channel"
    """
    A reservoir's channel.
    """


class ReagentChannel(StrEnum):
    """
    The station's reagent channels.
    """

    AMBER = "amber"
    """
    The amber reagent.
    """

    TEAL = "teal"
    """
    The teal reagent.
    """


class ReagentLabel(StrEnum):
    """
    The reagents' names.
    """

    AMBER = "Amber reagent"
    """
    The amber reagent's name.
    """

    TEAL = "Teal reagent"
    """
    The teal reagent's name.
    """


REAGENT_COLORS: Mapping[str, LinearColor] = {
    ReagentChannel.AMBER: AMBER_LIQUID,
    ReagentChannel.TEAL: TEAL_LIQUID,
}
"""
Each channel's colour.
"""

REAGENT_LABELS: Mapping[str, ReagentLabel] = {
    ReagentChannel.AMBER: ReagentLabel.AMBER,
    ReagentChannel.TEAL: ReagentLabel.TEAL,
}
"""
Each channel's reagent name.
"""

# %% parameters


@dataclass(frozen=True)
class DispenserParameters:
    """
    The pump's limits and the receiver's tolerances.
    """

    minimum: float = 0.1
    """
    The smallest dose, in millilitres.
    """

    maximum: float = 5.0
    """
    The largest dose, in millilitres.
    """

    default: float = 1.0
    """
    The dose when a request gives none, in millilitres.
    """

    flow_rate: float = 1.0
    """
    How fast the pump delivers, in millilitres per simulated second.
    """

    reservoir: float = 50.0
    """
    A full reservoir's volume, in millilitres.
    """

    position_tolerance: float = 0.008
    """
    How far the receiver's bottom may stand from its place, in metres.
    """

    upright_tolerance: float = 0.05
    """
    How far the receiver may lean, in radians.
    """

    minimum_gap: float = 0.002
    """
    The smallest gap between the nozzle and the receiver's rim, in metres.
    """

    maximum_gap: float = 0.03
    """
    The largest gap between the nozzle and the receiver's rim, in metres.
    """

    stopper_clearance: float = 0.02
    """
    How far along the axis from its seat a stopper still closes the receiver, in metres.
    """


# %% station


@dataclass
class LaboratoryDispenser:
    """
    Delivers reagent doses into the vessel beneath the nozzle.
    """

    layout: DispenserLayout
    """
    The authored station.
    """

    liquid: LaboratoryLiquid
    """
    The vessels' liquid.
    """

    stopper: Optional[StopperLayout]
    """
    The stopper that may close a receiver, None for a laboratory without one.
    """

    parameters: DispenserParameters = field(default_factory=DispenserParameters)
    """
    The pump's limits and tolerances.
    """

    reservoirs: Dict[str, float] = field(init=False, default_factory=dict)
    """
    What each reservoir holds, in millilitres, by channel.
    """

    state: DispenserState = field(init=False, default=DispenserState.IDLE)
    """
    What the pump does.
    """

    channel: Optional[str] = field(init=False, default=None)
    """
    The channel of the current or last dose.
    """

    key: Optional[str] = field(init=False, default=None)
    """
    The receiver of the current or last dose.
    """

    requested: float = field(init=False, default=0.0)
    """
    The dose asked for, in millilitres.
    """

    delivered: float = field(init=False, default=0.0)
    """
    What was delivered of it, in millilitres.
    """

    blocked_by: Optional[Refusal] = field(init=False, default=None)
    """
    Why the dose stopped, while the pump is blocked.
    """

    def __post_init__(self) -> None:
        self.reset()

    @property
    def remaining(self) -> float:
        """
        What the current dose still owes, in millilitres.
        """
        return max(0.0, self.requested - self.delivered)

    def reset(self) -> None:
        """
        Fill the reservoirs and forget every dose.
        """
        self.reservoirs = {
            channel.identifier: self.parameters.reservoir
            for channel in self.layout.channels
        }
        self.state = DispenserState.IDLE
        self.channel = self.key = self.blocked_by = None
        self.requested = self.delivered = 0.0

    def operate(
        self,
        request: DispenserRequest,
        poses: Mapping[str, RigidPose],
        clamped: FrozenSet[str],
    ) -> None:
        """
        :param request: An operation, its fields checked for its action.
        :param poses: The free objects' measured poses.
        :param clamped: The vessels a centrifuge holder clamps.
        :raises OperationRefused: When the station or the receiver does not allow it.
        """
        if request.action is DispenserAction.STOP:
            self.state = DispenserState.IDLE
            self.blocked_by = None
            return
        if self.state is DispenserState.DISPENSING:
            raise OperationRefused(Refusal.DOSE_RUNNING)
        if request.action is DispenserAction.REFILL:
            self.reservoirs[self.known_channel(request.channel)] = (
                self.parameters.reservoir
            )
            return
        if request.action is DispenserAction.RESUME:
            if self.key is None or self.remaining <= VOLUME_TOLERANCE:
                raise OperationRefused(Refusal.NOTHING_TO_RESUME)
            key, channel, volume = self.key, self.channel, self.remaining
        else:
            channel = self.known_channel(request.channel)
            key = request.key
            volume = (
                self.parameters.default if request.volume is None else request.volume
            )
            if not self.parameters.minimum <= volume <= self.parameters.maximum:
                raise ValueOutOfRange(
                    Quantity.DOSE,
                    volume,
                    self.parameters.minimum,
                    self.parameters.maximum,
                )
        refusal = self.obstruction(key, channel, volume, poses, clamped)
        if refusal is not None:
            raise OperationRefused(refusal)
        if request.action is DispenserAction.DISPENSE:
            self.key, self.channel = key, channel
            self.requested, self.delivered = float(volume), 0.0
        self.blocked_by = None
        self.state = DispenserState.DISPENSING

    def known_channel(self, channel: Optional[str]) -> str:
        """
        :param channel: A channel's identifier.
        :return: The channel.
        :raises UnknownObject: When the station has no such channel.
        """
        if channel not in self.reservoirs:
            raise UnknownObject(str(channel), ObjectRole.CHANNEL)
        return channel

    def obstruction(
        self,
        key: str,
        channel: str,
        volume: float,
        poses: Mapping[str, RigidPose],
        clamped: FrozenSet[str],
    ) -> Optional[Refusal]:
        """
        :param key: The receiver.
        :param channel: The reagent channel.
        :param volume: The dose still to deliver, in millilitres.
        :param poses: The free objects' measured poses.
        :param clamped: The vessels a centrifuge holder clamps.
        :return: Why the dose cannot flow, None when it can.
        """
        if key not in self.liquid.vessels:
            return Refusal.RECEIVER_UNKNOWN
        if key in clamped:
            return Refusal.RECEIVER_CLAMPED
        pose = poses[key]
        shape = self.liquid.shape
        target = np.array(self.layout.target_position.to_json())
        if np.linalg.norm(pose.position - target) > self.parameters.position_tolerance:
            return Refusal.RECEIVER_MISPLACED
        if pose.axis[2] < math.cos(self.parameters.upright_tolerance):
            return Refusal.RECEIVER_TILTED
        nozzle = np.array(self.layout.nozzle_position.to_json())
        rim = pose.point_in_world(np.array([0.0, 0.0, shape.rim]))
        gap = nozzle[2] - rim[2]
        if (
            np.linalg.norm(rim[:2] - nozzle[:2]) > shape.radius
            or not self.parameters.minimum_gap <= gap <= self.parameters.maximum_gap
        ):
            return Refusal.RIM_MISALIGNED
        if self.stopper is not None and self.stopper.key in poses:
            stopper = pose.point_in_body(poses[self.stopper.key].position)
            seat = shape.rim - self.stopper.insertion_depth
            if (
                np.linalg.norm(stopper[:2]) < RIM_CLEARANCE_RADII * shape.radius
                and abs(stopper[2] - seat) < self.parameters.stopper_clearance
            ):
                return Refusal.STOPPER_IN_PLACE
        room = shape.capacity - self.liquid.vessels[key].volume
        if volume > room + VOLUME_TOLERANCE:
            return Refusal.RECEIVER_FULL
        if volume > self.reservoirs[channel] + VOLUME_TOLERANCE:
            return Refusal.RESERVOIR_EMPTY
        return None

    def advance(
        self,
        elapsed: float,
        poses: Mapping[str, RigidPose],
        clamped: FrozenSet[str],
    ) -> None:
        """
        Deliver what flowed during the elapsed time, if the receiver still allows it.

        :param elapsed: The simulated time since the previous call, in seconds.
        :param poses: The free objects' measured poses.
        :param clamped: The vessels a centrifuge holder clamps.
        """
        if self.state is not DispenserState.DISPENSING or elapsed == 0:
            return
        refusal = self.obstruction(
            self.key, self.channel, self.remaining, poses, clamped
        )
        if refusal is not None:
            self.state = DispenserState.BLOCKED
            self.blocked_by = refusal
            return
        amount = min(
            self.remaining,
            self.parameters.flow_rate * elapsed,
            self.reservoirs[self.channel],
        )
        accepted = self.liquid.supply(
            self.key, amount, np.array(REAGENT_COLORS[self.channel].to_json())
        )
        self.reservoirs[self.channel] -= accepted
        self.delivered += accepted
        if self.remaining <= VOLUME_TOLERANCE:
            self.state = DispenserState.COMPLETE

    def receiving(self, key: str) -> bool:
        """
        :param key: A vessel.
        :return: Whether a dose flows into it now.
        """
        return self.state is DispenserState.DISPENSING and self.key == key

    def limits(self) -> DoseLimits:
        """
        :return: The station's reagents and limits.
        """
        return DoseLimits(
            reagents=[
                Reagent(
                    identifier=channel.identifier,
                    label=REAGENT_LABELS[channel.identifier].value,
                    color=REAGENT_COLORS[channel.identifier],
                    capacity=self.parameters.reservoir,
                )
                for channel in self.layout.channels
            ],
            minimum=self.parameters.minimum,
            maximum=self.parameters.maximum,
            default=self.parameters.default,
            flow_rate=self.parameters.flow_rate,
        )

    def status(self) -> DispenserStatus:
        """
        :return: What the station measures, as the browser reads it.
        """
        return DispenserStatus(
            state=self.state,
            channel=self.channel,
            key=self.key,
            requested=self.requested,
            delivered=self.delivered,
            blocked_by=None if self.blocked_by is None else self.blocked_by.value,
            reservoirs=[
                ReservoirLevel(identifier=channel, volume=volume)
                for channel, volume in self.reservoirs.items()
            ],
        )
