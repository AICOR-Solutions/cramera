"""
The run log of a plan: every attempt at a step and what the camera kept in view, written
as lines to the run's output, which the plan builder shows as the run's log.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import Callable, TextIO

from krrood.ormatic.utils import classproperty

# %% entries


class RunLogEntry(ABC):
    """
    One thing that happened while a plan ran.
    """

    @abstractmethod
    def line(self) -> str:
        """
        :return: The entry as a person reads it in the run log.
        """


class AttemptOutcome(StrEnum):
    """
    How an attempt at a step ended.
    """

    SUCCEEDED = "succeeded"
    """
    The step succeeded.
    """

    RETRYING = "failed, retrying"
    """
    The step failed and is attempted again.
    """

    ABORTED = "failed, giving up"
    """
    The step failed and no attempt is left, so the plan is aborted.
    """


@dataclass(frozen=True)
class StepAttempt(RunLogEntry):
    """
    How one attempt at a step ended.
    """

    step: str
    """
    The identity of the step.
    """

    number: int
    """
    Which attempt it was, counting from 1.
    """

    attempts: int
    """
    How many attempts the step has at most.
    """

    outcome: AttemptOutcome
    """
    How the attempt ended.
    """

    reason: str | None = None
    """
    Why the attempt failed, None when it succeeded.
    """

    next_attempt: str | None = None
    """
    How the next attempt differs, None when none follows.
    """

    def line(self) -> str:
        text = f"{self.step}: attempt {self.number}/{self.attempts} {self.outcome}"
        if self.reason is not None:
            text = f"{text}: {self.reason}"
        if self.next_attempt is not None:
            text = f"{text} Next attempt {self.next_attempt}."
        return text


class View(StrEnum):
    """
    Whether the camera sees what a step keeps in view.
    """

    IN_VIEW = "in view ✓"
    """
    The target lies inside the camera's field of view.
    """

    OUT_OF_VIEW = "out of view ✗"
    """
    The target lies outside the camera's field of view.
    """


@dataclass(frozen=True)
class LookAt(RunLogEntry):
    """
    What a step's look-at observed once it changed.
    """

    step: str
    """
    The identity of the step keeping its target in view.
    """

    target: str
    """
    The identity of the object kept in view.
    """

    view: View
    """
    Whether the camera sees it.
    """

    def line(self) -> str:
        return f"{self.step}: look-at: {self.view} ({self.target})"


# %% the log


@dataclass
class RunLog:
    """
    The entries of a run, each written as a line to :attr:`stream` once it happened and
    handed to every listener.
    """

    stream: TextIO = field(default_factory=lambda: sys.stdout)
    """
    Where the lines are written.
    """

    entries: list[RunLogEntry] = field(default_factory=list)
    """
    The entries written so far, in order.
    """

    listeners: list[Callable[[RunLogEntry], None]] = field(default_factory=list)
    """
    Called with every entry once it was written.
    """

    @classproperty
    def line_prefix(cls) -> str:
        """
        :return: What every line of the run log starts with, telling it from the rest
            of the run's output.
        """
        return "[run log]"

    def write(self, entry: RunLogEntry) -> None:
        """
        :param entry: What happened.
        """
        self.entries.append(entry)
        print(f"{self.line_prefix} {entry.line()}", file=self.stream, flush=True)
        for listener in self.listeners:
            listener(entry)
