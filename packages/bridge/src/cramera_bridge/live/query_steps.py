"""
The queries the running process asked, as it last published them, and holding it at each
query until the viewer moves on.
"""

from __future__ import annotations

import dataclasses
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from typing_extensions import Optional

from cramera_bridge.exceptions import NoQueryStepping
from cramera_protocol.live_messages import Acknowledgement
from cramera_protocol.query_steps import (
    HeldStep,
    QuerySteps,
    StepAdvance,
    SteppingRequest,
)

# %% control


class QueryStepControl(ABC):
    """
    Holds a running process at each query it asks, and lets the viewer move it on.
    """

    @abstractmethod
    def advance(self, held: Optional[HeldStep]) -> None:
        """
        Let the process carry on from the step it is held at.

        :param held: The step the viewer saw the process held at; the process carries on
            only while it is still held there. None lets it carry on from any step.
        """

    @abstractmethod
    def change_stepping(self, request: SteppingRequest) -> None:
        """
        :param request: Whether the process is held at every query it asks, and at the
            queries asked while another is answered.
        """


# %% board


@dataclass
class QueryStepBoard:
    """
    Keeps the newest query steps a process published, numbered by revision so a viewer
    showing the newest one is answered without them.
    """

    steps: Optional[QuerySteps] = field(default=None, init=False)
    """
    The newest steps with their revision, or None before any were published.
    """

    control: Optional[QueryStepControl] = field(default=None, init=False)
    """
    Holds the process at its queries, or None where it cannot be held.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Guards the steps, which the process writes and HTTP threads read.
    """

    def publish(
        self, steps: QuerySteps, control: Optional[QueryStepControl] = None
    ) -> None:
        """
        :param steps: Every query asked so far and the step the process is held at; its
            revision is replaced by the board's next one.
        :param control: Holds the process at its queries; None offers no stepping.
        """
        with self.lock:
            revision = 0 if self.steps is None else self.steps.revision
            self.steps = dataclasses.replace(
                steps, revision=revision + 1, unchanged=False
            )
            self.control = control

    def current(self, known_revision: Optional[int] = None) -> QuerySteps:
        """
        :param known_revision: The revision the viewer shows, if any.
        :return: The newest steps, or only their revision when the viewer shows it
            already; none before any were published.
        """
        with self.lock:
            steps = self.steps or QuerySteps()
        if known_revision == steps.revision:
            return QuerySteps(revision=steps.revision, unchanged=True)
        return steps

    def recorded(self) -> Optional[QuerySteps]:
        """
        :return: Every query asked, as a recording keeps them: held nowhere and by no
            revision; None before any query was asked.
        """
        with self.lock:
            steps = self.steps
        if steps is None or not steps.steps:
            return None
        return QuerySteps(steps=steps.steps)

    def is_published(self) -> bool:
        """
        :return: Whether steps were published.
        """
        with self.lock:
            return self.steps is not None

    def offers_stepping(self) -> bool:
        """
        :return: Whether the process can be held at its queries.
        """
        with self.lock:
            return self.control is not None

    def require_control(self) -> QueryStepControl:
        """
        :return: What holds the process at its queries.
        :raises NoQueryStepping: When the process cannot be held at them.
        """
        with self.lock:
            control = self.control
        if control is None:
            raise NoQueryStepping()
        return control

    def advance(self, request: StepAdvance) -> Acknowledgement:
        """
        :param request: The step the viewer saw the process held at.
        :return: The acknowledgement.
        :raises NoQueryStepping: When the process cannot be held at its queries.
        """
        self.require_control().advance(request.held)
        return Acknowledgement()

    def change_stepping(self, request: SteppingRequest) -> Acknowledgement:
        """
        :param request: Whether the process is held at every query.
        :return: The acknowledgement.
        :raises NoQueryStepping: When the process cannot be held at its queries.
        """
        self.require_control().change_stepping(request)
        return Acknowledgement()
