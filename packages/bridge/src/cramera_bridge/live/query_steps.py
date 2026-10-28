"""
The queries the running process asked, as it last published them, and holding it at each
query until the viewer moves on.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from typing_extensions import Callable, Optional

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


@dataclass
class HeldQueries(QueryStepControl):
    """
    Holds the process's thread at a query until the viewer moves it on.
    """

    stepping: bool = True
    """
    Whether the process is held at every query.
    """

    holds_nested: bool = True
    """
    Whether it is also held at queries asked while another is answered.
    """

    held: Optional[HeldStep] = None
    """
    The step the process is held at, or None while it runs on.
    """

    condition: threading.Condition = field(default_factory=threading.Condition)
    """
    Wakes the held process when the viewer moves it on.
    """

    held_seconds: float = 0.0
    """
    How long the process was held so far, in seconds.
    """

    def advance(self, held: Optional[HeldStep]) -> None:
        with self.condition:
            if held is None or held == self.held:
                self.held = None
                self.condition.notify_all()

    def change_stepping(self, request: SteppingRequest) -> None:
        with self.condition:
            self.stepping = request.stepping
            self.holds_nested = request.holds_nested
            if not self.stepping:
                self.held = None
            self.condition.notify_all()

    def release(self) -> None:
        """
        Let the process carry on from any step and hold it at no further query.
        """
        self.change_stepping(SteppingRequest(stepping=False))

    def holds_at(self, depth: int) -> bool:
        """
        :param depth: How many queries a query is asked inside.
        :return: Whether the process is held at it.
        """
        return self.stepping and (depth == 0 or self.holds_nested)

    def hold(self, step: HeldStep, depth: int, publish: Callable[[], None]) -> None:
        """
        Hold the calling thread at a step until the viewer moves it on, unless the
        process is not held at it.

        :param step: The step the process reached.
        :param depth: How many queries the step's query is asked inside.
        :param publish: Publishes the steps, called once it is decided whether the
            process is held, so the viewer sees where it waits.
        """
        with self.condition:
            if self.holds_at(depth):
                self.held = step
            publish()
            waiting = time.monotonic()
            while self.held is not None:
                self.condition.wait()
            self.held_seconds += time.monotonic() - waiting

    def running_time(self) -> float:
        """
        A clock that stands still while the process is held, so a recording stamped with
        it replays the run at the pace it ran, however long a person looked at each
        query.

        :return: The wall-clock time less the time the process was held, in seconds
            since the epoch.
        """
        return time.time() - self.held_seconds


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
