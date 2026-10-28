"""
Errors the scene runs plugin raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from cramera.exceptions import ViewerError


@dataclass
class SceneRunsError(ViewerError):
    """
    A run the plugin cannot offer, start or stop.
    """


@dataclass
class InvalidSceneRunCatalog(SceneRunsError):
    """
    A catalog file of runs the viewer cannot offer; the viewer does not start with it.
    """

    path: Path
    """
    The catalog file.
    """

    reason: str
    """
    What is wrong with it.
    """

    def message(self) -> str:
        return f"The runs in {self.path} cannot be offered: {self.reason}"


@dataclass
class UnknownSceneRun(SceneRunsError):
    """
    A run the viewer does not offer.
    """

    identifier: str
    """
    The requested run.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No run named {self.identifier!r} is offered."


@dataclass
class SceneRunBusy(SceneRunsError):
    """
    A start while another run runs; one runs at a time.
    """

    running: str
    """
    The label of the run that runs.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.CONFLICT

    def message(self) -> str:
        return f"{self.running} runs; stop it first, one run runs at a time."


@dataclass
class SceneRunNotStarted(SceneRunsError):
    """
    A run whose command the operating system could not start.
    """

    identifier: str
    """
    The run.
    """

    reason: str
    """
    What the operating system reported.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.SERVICE_UNAVAILABLE

    def message(self) -> str:
        return f"The run {self.identifier!r} could not start: {self.reason}"
