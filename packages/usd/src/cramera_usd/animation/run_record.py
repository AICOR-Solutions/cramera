"""
The steps of a recorded run, read from the run record the twin's recorder writes beside
its trace, and the stretches of the playback they label.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, List, Self

from cramera_usd.encoding import TEXT_ENCODING

# %% record vocabulary


class RecordKey(StrEnum):
    """
    The keys of a run record that the steps are read from.
    """

    STEPS = "steps"
    """
    The completed steps, in order.
    """

    STEP = "step"
    """
    A step's name.
    """

    TIME = "t"
    """
    When a step completed, in seconds on the recorder's clock.
    """

    START = "t0_rig_s"
    """
    The recorder's clock time of the trace's first frame.
    """


# %% steps


@dataclass(frozen=True)
class StepSegment:
    """
    One labelled stretch of the playback, as the viewer's timeline shows it.
    """

    step: str
    """
    What happened in the stretch.
    """

    start: int
    """
    The first frame of the stretch.
    """

    end: int
    """
    The frame the stretch ends at, where the next one starts.
    """


@dataclass(frozen=True)
class RecordedStep:
    """
    One completed step of a recorded run.
    """

    name: str
    """
    What the step did.
    """

    end: float
    """
    When the step completed, in seconds on the recorder's clock.
    """


@dataclass(frozen=True)
class PlaybackClock:
    """
    The frames of a playback, to find the frame of a moment.
    """

    frames_per_second: float
    """
    The playback rate.
    """

    frame_count: int
    """
    The number of playback frames.
    """

    def frame_at(self, seconds: float) -> int:
        """
        :param seconds: A time since the first frame.
        :return: The playback frame nearest to it.
        """
        return min(
            max(round(seconds * self.frames_per_second), 0), self.frame_count - 1
        )


@dataclass
class RecordedRun:
    """
    The steps of a recorded run.
    """

    steps: List[RecordedStep]
    """
    The steps in the order they completed.
    """

    start: float = 0.0
    """
    The recorder's clock time of the trace's first frame.
    """

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> Self:
        """
        :param payload: A parsed run record.
        :return: The run it describes.
        """
        return cls(
            [
                RecordedStep(step[RecordKey.STEP], float(step[RecordKey.TIME]))
                for step in payload[RecordKey.STEPS]
            ],
            float(payload.get(RecordKey.START, 0.0)),
        )

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A JSON run record.
        :return: The run it describes.
        """
        return cls.from_json(json.loads(path.read_text(encoding=TEXT_ENCODING)))

    def segments(self, clock: PlaybackClock) -> List[StepSegment]:
        """
        :param clock: The frames of the playback.
        :return: One segment per step completed after the trace began, from the
            completion of the step before it (or the first frame) to its own
            completion.
        """
        segments = []
        previous = 0.0
        for step in self.steps:
            end = step.end - self.start
            if end < 0.0:
                continue
            segments.append(
                StepSegment(step.name, clock.frame_at(previous), clock.frame_at(end))
            )
            previous = max(previous, end)
        return segments
