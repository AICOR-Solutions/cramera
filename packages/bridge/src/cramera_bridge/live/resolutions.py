"""
How the open parts of the running plans were resolved, as the process last published it,
and carrying out a resolved plan on request.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from typing_extensions import Optional

from cramera_bridge.exceptions import (
    NoResolutionExecution,
    ResolutionNotExecutable,
    UnknownResolution,
)
from cramera_protocol.live_messages import Acknowledgement
from cramera_protocol.resolutions import ExecutionRequest, PlanResolutions

# %% execution


class ResolutionExecution(ABC):
    """
    Carries out the plan a published resolution resolved.
    """

    @abstractmethod
    def execute(self, resolution: str) -> None:
        """
        Start carrying out a resolved plan; returns once it is handed to the thread that
        owns the world.

        :param resolution: The identity of a published, executable resolution.
        """


# %% board


@dataclass
class ResolutionBoard:
    """
    Keeps the newest resolutions a process published, read from HTTP threads.
    """

    resolutions: Optional[PlanResolutions] = field(default=None, init=False)
    """
    The newest resolutions, or None before any were published.
    """

    execution: Optional[ResolutionExecution] = field(default=None, init=False)
    """
    Carries out a resolved plan, or None where the process carries out none on request.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Guards the resolutions, which the process writes and HTTP threads read.
    """

    def publish(
        self,
        resolutions: PlanResolutions,
        execution: Optional[ResolutionExecution] = None,
    ) -> None:
        """
        :param resolutions: Every resolution so far.
        :param execution: Carries out a resolved plan on request; None offers none.
        """
        with self.lock:
            self.resolutions = resolutions
            self.execution = execution

    def current(self) -> PlanResolutions:
        """
        :return: The newest resolutions, none before any were published.
        """
        with self.lock:
            return self.resolutions or PlanResolutions()

    def is_published(self) -> bool:
        """
        :return: Whether resolutions were published.
        """
        with self.lock:
            return self.resolutions is not None

    def offers_execution(self) -> bool:
        """
        :return: Whether a resolved plan can be carried out on request.
        """
        with self.lock:
            return self.execution is not None

    def execute(self, request: ExecutionRequest) -> Acknowledgement:
        """
        :param request: The resolution whose plan is carried out.
        :return: The acknowledgement, once the plan is handed on.
        :raises NoResolutionExecution: When the process carries out no plans on request.
        :raises UnknownResolution: When no published resolution has the identity.
        :raises ResolutionNotExecutable: When the resolution's plan cannot be carried
            out.
        """
        with self.lock:
            execution = self.execution
            resolutions = self.resolutions or PlanResolutions()
        if execution is None:
            raise NoResolutionExecution()
        resolution = next(
            (
                resolution
                for resolution in resolutions.resolutions
                if resolution.identifier == request.resolution
            ),
            None,
        )
        if resolution is None:
            raise UnknownResolution(request.resolution)
        if not resolution.executable:
            raise ResolutionNotExecutable(request.resolution)
        execution.execute(request.resolution)
        return Acknowledgement()
