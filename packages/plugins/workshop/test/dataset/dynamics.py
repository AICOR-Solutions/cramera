"""
A contact world and a clock that stand in for MuJoCo and the wall clock, so the session
can be tested without either.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from typing_extensions import List, Optional, Tuple

from cramera_protocol.geometry import Pose
from cramera_protocol.workshop import DriveDirection, WorkshopState
from cramera_workshop.exceptions import (
    NothingHeld,
    UnknownWorkshopBody,
    WorkshopSimulationFailure,
)
from cramera_workshop.session import WorkshopDynamics

MOVABLE_BODIES = ("screw_box", "screw_1")
"""
The bodies the stand-in lets a spring hold.
"""


@dataclass
class RecordingDynamics(WorkshopDynamics):
    """
    Records every call and lets time pass by counting steps.
    """

    calls: List[Tuple[str, ...]] = field(default_factory=list)
    """
    Each call's method name and arguments, in order.
    """

    held_body: Optional[str] = None
    """
    The held body.
    """

    simulated_time: float = 0.0
    """
    The time the steps added up to, in seconds.
    """

    failing: bool = False
    """
    Whether the next step loses a valid state.
    """

    crashing: bool = False
    """
    Whether the next step fails in a way the session does not expect.
    """

    stepped: threading.Event = field(default_factory=threading.Event)
    """
    Set by every step.
    """

    def held(self) -> Optional[str]:
        return self.held_body

    def grab(self, key: str) -> None:
        if key not in MOVABLE_BODIES:
            raise UnknownWorkshopBody(key)
        self.calls.append(("grab", key))
        self.held_body = key

    def move(self, key: str, pose: Pose) -> None:
        if key != self.held_body:
            raise NothingHeld(key)
        self.calls.append(("move", key))

    def release(self) -> None:
        self.calls.append(("release",))
        self.held_body = None

    def set_drawer(self, joint: str, position: float) -> None:
        self.calls.append(("drawer", joint))

    def drive(self, direction: DriveDirection) -> None:
        self.calls.append(("drive", direction.value))

    def step(self, duration: float) -> None:
        if self.crashing:
            raise ArithmeticError("the stand-in crashed")
        if self.failing:
            raise WorkshopSimulationFailure()
        self.simulated_time += duration
        self.stepped.set()

    def state(self) -> WorkshopState:
        return WorkshopState(held=self.held_body, time=self.simulated_time)

    def reset(self) -> None:
        self.calls.append(("reset",))
        self.held_body = None
        self.simulated_time = 0.0


@dataclass
class ManualClock:
    """
    A clock that only moves when told to.
    """

    now: float = 0.0
    """
    The current time, in seconds.
    """

    def __call__(self) -> float:
        return self.now
