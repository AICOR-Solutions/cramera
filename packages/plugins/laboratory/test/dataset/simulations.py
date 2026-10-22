"""
Stand-ins for the contact simulation, so the session and the routes are tested without
MuJoCo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import List, Optional

from cramera_laboratory.exceptions import (
    OperationRefused,
    PhysicsUnavailable,
    Refusal,
)
from cramera_laboratory.resources import LaboratoryBundle
from cramera_laboratory.session import ContactSimulation, SimulationFactory
from cramera_protocol.laboratory.physics import (
    CentrifugeRequest,
    ContactPhysicsControls,
    DispenserRequest,
    InstrumentRequest,
    LiquidRequest,
    ManualRequest,
    OpeningRequest,
    SimulationSnapshot,
    TargetRequest,
)

DATASET = Path(__file__).parent
"""
The directory of the test documents.
"""

STEP = 0.001
"""
The stand-in's integration step, in seconds.
"""


@dataclass
class RecordingSimulation(ContactSimulation):
    """
    Remembers the commands it receives and reports a fixed snapshot.
    """

    laboratory: LaboratoryBundle
    """
    The laboratory it stands for.
    """

    commands: List[object] = field(default_factory=list)
    """
    The requests received, in order; ``None`` for a command without a document.
    """

    steps: int = 0
    """
    How many steps were integrated.
    """

    failure: Optional[Exception] = None
    """
    What stepping raises, None to step normally.
    """

    @property
    def timestep(self) -> float:
        return STEP

    def step(self, count: int) -> None:
        if self.failure is not None:
            raise self.failure
        self.steps += count

    def reset(self) -> None:
        self.commands.append(None)

    def set_target(self, request: TargetRequest) -> None:
        self.commands.append(request)

    def release(self) -> None:
        self.commands.append(None)

    def fill(self, request: LiquidRequest) -> None:
        self.commands.append(request)

    def tare(self) -> None:
        raise OperationRefused(Refusal.UNSETTLED_SCALE)

    def operate_centrifuge(self, request: CentrifugeRequest) -> None:
        self.commands.append(request)

    def read_manual(self, request: ManualRequest) -> None:
        self.commands.append(request)

    def operate_refrigerator(self, request: OpeningRequest) -> None:
        self.commands.append(request)

    def operate_drawer(self, request: OpeningRequest) -> None:
        self.commands.append(request)

    def operate_dispenser(self, request: DispenserRequest) -> None:
        self.commands.append(request)

    def move_instrument(self, request: InstrumentRequest) -> None:
        self.commands.append(request)

    def snapshot(self) -> SimulationSnapshot:
        return SimulationSnapshot.from_json(
            json.loads((DATASET / "snapshot.json").read_text(encoding="utf-8"))
        )

    def controls(self) -> ContactPhysicsControls:
        controls = ContactPhysicsControls.from_json(
            json.loads((DATASET / "controls.json").read_text(encoding="utf-8"))
        )
        controls.laboratory = self.laboratory.name
        return controls


@dataclass
class RecordingFactory(SimulationFactory):
    """
    Creates recording stand-ins and remembers them.
    """

    installed: bool = True
    """
    Whether it pretends the engine is installed.
    """

    created: List[RecordingSimulation] = field(default_factory=list)
    """
    The stand-ins created, in order.
    """

    def available(self) -> bool:
        return self.installed

    def create(self, laboratory: LaboratoryBundle) -> RecordingSimulation:
        if not self.installed:
            raise PhysicsUnavailable()
        simulation = RecordingSimulation(laboratory)
        self.created.append(simulation)
        return simulation
