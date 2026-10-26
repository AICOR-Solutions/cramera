"""
Stand-ins for what holds a process at its queries and carries out its resolved plans,
remembering what the viewer asked of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import List, Optional

from cramera_bridge.live.query_steps import QueryStepControl
from cramera_bridge.live.resolutions import ResolutionExecution
from cramera_protocol.query_steps import HeldStep, SteppingRequest

# %% stepping


@dataclass
class RememberedStepControl(QueryStepControl):
    """
    Remembers every step the viewer let the process carry on from, and every change of
    how it is held.
    """

    advanced_from: List[Optional[HeldStep]] = field(default_factory=list)
    """
    The steps named by each request to carry on, in order.
    """

    stepping_changes: List[SteppingRequest] = field(default_factory=list)
    """
    The requests changing how the process is held, in order.
    """

    def advance(self, held: Optional[HeldStep]) -> None:
        self.advanced_from.append(held)

    def change_stepping(self, request: SteppingRequest) -> None:
        self.stepping_changes.append(request)


# %% execution


@dataclass
class RememberedExecution(ResolutionExecution):
    """
    Remembers every resolution whose plan the viewer had carried out.
    """

    executed: List[str] = field(default_factory=list)
    """
    The identities of the resolutions, in the order they were carried out.
    """

    def execute(self, resolution: str) -> None:
        self.executed.append(resolution)
