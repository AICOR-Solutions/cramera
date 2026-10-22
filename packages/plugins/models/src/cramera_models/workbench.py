"""
The workbench a models plugin answers its routes with: one loaded model and the
questions asked about it, as protocol documents in and out.
"""

from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List

from cramera_models.exceptions import CircuitLibrariesMissing
from cramera_models.libraries import CircuitLibraries
from cramera_protocol.models import (
    ModeAnswer,
    ModelUpload,
    ModeRequest,
    PosteriorAnswer,
    PosteriorRequest,
    ProbabilityAnswer,
    ProbabilityRequest,
    WorkbenchState,
)

# %% interface


class Workbench(ABC):
    """
    Holds one model and answers questions about it; safe to call from several request
    threads.
    """

    @abstractmethod
    def state(self) -> WorkbenchState:
        """
        :return: Whether a model is loaded, and its variables.
        """

    @abstractmethod
    def load(self, upload: ModelUpload) -> WorkbenchState:
        """
        Replace the loaded model.

        :param upload: The model file.
        :return: The state with the new model.
        :raises InvalidJson: When the file is not JSON.
        :raises NotACircuit: When the file describes no probabilistic circuit.
        """

    @abstractmethod
    def probability(self, request: ProbabilityRequest) -> ProbabilityAnswer:
        """
        :param request: The query and the evidence.
        :return: The probability of the query given the evidence.
        :raises NoModelLoaded: Without a model.
        :raises UnknownVariable: When a constraint names no variable of the model.
        """

    @abstractmethod
    def posterior(self, request: PosteriorRequest) -> PosteriorAnswer:
        """
        :param request: The variables and the evidence.
        :return: The posterior marginal of each variable given the evidence.
        :raises NoModelLoaded: Without a model.
        :raises UnknownVariable: When a variable or a constraint names no variable of
            the model.
        :raises ImpossibleEvidence: When the evidence has the probability zero.
        """

    @abstractmethod
    def mode(self, request: ModeRequest) -> ModeAnswer:
        """
        :param request: The evidence.
        :return: The most likely assignments given the evidence.
        :raises NoModelLoaded: Without a model.
        :raises UnknownVariable: When a constraint names no variable of the model.
        :raises ImpossibleEvidence: When the evidence has the probability zero.
        """


# %% without the libraries


@dataclass(frozen=True)
class UnavailableWorkbench(Workbench):
    """
    The workbench of an environment without the circuit libraries: every request is
    answered with the error naming the missing modules.
    """

    missing: List[str]
    """
    The modules that cannot be found.
    """

    def state(self) -> WorkbenchState:
        raise CircuitLibrariesMissing(self.missing)

    def load(self, upload: ModelUpload) -> WorkbenchState:
        raise CircuitLibrariesMissing(self.missing)

    def probability(self, request: ProbabilityRequest) -> ProbabilityAnswer:
        raise CircuitLibrariesMissing(self.missing)

    def posterior(self, request: PosteriorRequest) -> PosteriorAnswer:
        raise CircuitLibrariesMissing(self.missing)

    def mode(self, request: ModeRequest) -> ModeAnswer:
        raise CircuitLibrariesMissing(self.missing)


# %% choice


class WorkbenchModule(StrEnum):
    """
    The module of the workbench that computes with the circuit libraries; it imports
    them, so it is only imported once they are found.
    """

    CIRCUITS = "cramera_models.circuit_workbench"
    """
    :class:`cramera_models.circuit_workbench.CircuitWorkbench`.
    """


@dataclass(frozen=True)
class WorkbenchChoice:
    """
    Creates the workbench the installed libraries allow.
    """

    libraries: CircuitLibraries = field(default_factory=CircuitLibraries)
    """
    Finds out which libraries are installed.
    """

    def workbench(self) -> Workbench:
        """
        :return: A circuit workbench, or an :class:`UnavailableWorkbench` naming the
            missing libraries.
        """
        missing = self.libraries.missing()
        if missing:
            return UnavailableWorkbench(missing)
        return importlib.import_module(WorkbenchModule.CIRCUITS).CircuitWorkbench()
