"""
A workbench that records the documents it is given and answers with fixed documents, for
testing the routes without the circuit libraries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing_extensions import List

from cramera_models.workbench import Workbench, WorkbenchChoice
from cramera_protocol.document import JsonDocument
from cramera_protocol.models import (
    ModeAnswer,
    ModelUpload,
    ModelVariable,
    ModeRequest,
    PosteriorAnswer,
    PosteriorRequest,
    ProbabilityAnswer,
    ProbabilityRequest,
    VariableKind,
    WorkbenchState,
)

# %% workbench


@dataclass
class RecordingWorkbench(Workbench):
    """
    Records every request and answers with the documents its fields hold.
    """

    received: List[JsonDocument] = field(default_factory=list)
    """
    The requests, in the order they arrived.
    """

    loaded_state: WorkbenchState = field(
        default_factory=lambda: WorkbenchState(
            loaded=True,
            name="recorded.json",
            variables=[
                ModelVariable(name="x", kind=VariableKind.CONTINUOUS, low=0, high=1)
            ],
        )
    )
    """
    The answer to state and load requests.
    """

    probability_answer: ProbabilityAnswer = field(
        default_factory=lambda: ProbabilityAnswer(probability=0.125)
    )
    """
    The answer to probability requests.
    """

    posterior_answer: PosteriorAnswer = field(
        default_factory=lambda: PosteriorAnswer(figures={"x": {}})
    )
    """
    The answer to posterior requests.
    """

    mode_answer: ModeAnswer = field(
        default_factory=lambda: ModeAnswer(likelihood=0.5, modes=[{"x": "0.5"}])
    )
    """
    The answer to mode requests.
    """

    def state(self) -> WorkbenchState:
        return self.loaded_state

    def load(self, upload: ModelUpload) -> WorkbenchState:
        self.received.append(upload)
        return self.loaded_state

    def probability(self, request: ProbabilityRequest) -> ProbabilityAnswer:
        self.received.append(request)
        return self.probability_answer

    def posterior(self, request: PosteriorRequest) -> PosteriorAnswer:
        self.received.append(request)
        return self.posterior_answer

    def mode(self, request: ModeRequest) -> ModeAnswer:
        self.received.append(request)
        return self.mode_answer


# %% choice


@dataclass(frozen=True)
class GivenWorkbenchChoice(WorkbenchChoice):
    """
    Chooses the workbench it was given, whatever is installed.
    """

    given: Workbench = field(default_factory=RecordingWorkbench)
    """
    The workbench to choose.
    """

    def workbench(self) -> Workbench:
        return self.given
