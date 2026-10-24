"""
Errors cramera-questions raises.

Errors a request can cause derive from :class:`~cramera.exceptions.ViewerError`, so the
HTTP boundary answers them with their own status.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from typing_extensions import List

from cramera.exceptions import ViewerError

# %% base


@dataclass
class QuestionError(ViewerError):
    """
    A question that cannot be asked or answered.
    """


# %% requests


@dataclass
class MissingParameter(QuestionError):
    """
    A request lacking a query parameter its route needs.
    """

    parameter: str
    """
    The missing parameter.
    """

    def message(self) -> str:
        return f"The request needs the parameter {self.parameter!r}."


# %% installation


@dataclass
class QueryLanguageMissing(QuestionError):
    """
    A question asked of a viewer whose Python environment has no krrood, which evaluates
    the entity query language, or no cramera-bridge, whose question engine uses it.
    """

    missing: List[str]
    """
    The modules that cannot be found.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return (
            f"Answering questions needs {', '.join(self.missing)}, which this Python "
            f"environment does not have. Run the viewer from a CRAM workspace, or open "
            f"a scene whose answers were recorded with cramera-record-answers."
        )
