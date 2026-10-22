"""
Errors the models plugin raises; each becomes the error answer of the request that
raised it.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% libraries


@dataclass
class CircuitLibrariesMissing(ViewerError):
    """
    The libraries the workbench computes with are not installed.
    """

    modules: List[str]
    """
    The modules that cannot be found.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            f"The models workbench needs {', '.join(self.modules)}, which this Python "
            f"environment does not have. Install cramera-models[circuits] or run the "
            f"viewer from a CRAM workspace."
        )


# %% requests


@dataclass
class InvalidJson(ViewerError):
    """
    A request body or a model file that is not JSON.
    """

    source: str
    """
    What the text was: the request body or the model file's name.
    """

    reason: str
    """
    What the JSON reader reported.
    """

    def message(self) -> str:
        return f"{self.source} is not JSON: {self.reason}"


@dataclass
class NotACircuit(ViewerError):
    """
    A model file that does not describe a probabilistic circuit.
    """

    name: str
    """
    The model file's name.
    """

    reason: str
    """
    Why it was refused.
    """

    def message(self) -> str:
        return f"{self.name} is not a probabilistic circuit: {self.reason}"


@dataclass
class NoModelLoaded(ViewerError):
    """
    A question asked before a model was loaded.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return "No model is loaded; load a circuit file first."


@dataclass
class UnknownVariable(ViewerError):
    """
    A constraint or a posterior request naming a variable the model does not have.
    """

    name: str
    """
    The variable name that was given.
    """

    def message(self) -> str:
        return f"The loaded model has no variable named {self.name!r}."


@dataclass
class ImpossibleEvidence(ViewerError):
    """
    Evidence the loaded model gives the probability zero, so nothing can be conditioned
    on it.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.UNPROCESSABLE_ENTITY

    def message(self) -> str:
        return "The evidence has the probability zero under the loaded model."
