"""
The steps of a recorded workshop demo: one per stage of its plan, covering the frames
recorded while the stage ran.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from typing_extensions import List, Sequence

from cramera_protocol.bundle.scene import Segment


@dataclass(frozen=True)
class StagePeriod:
    """
    When one stage of a plan ran.
    """

    stage: str
    """
    The stage's name.
    """

    start: float
    """
    When it began, in seconds since the epoch.
    """

    end: float
    """
    When it ended, in seconds since the epoch.
    """


@dataclass(frozen=True)
class StageTimeline:
    """
    The recorded frames, divided by the stages that ran while they were recorded.
    """

    frame_times: Sequence[float]
    """
    The wall-clock time of each frame in seconds since the epoch, in recording order.
    """

    periods: Sequence[StagePeriod]
    """
    When each stage ran, in the order they ran.
    """

    def segments(self) -> List[Segment]:
        """
        :return: One step per stage over the frames recorded while it ran; a frame two
            stages share belongs to the first, and a stage no frame shows is left out.
        """
        last_frame = len(self.frame_times) - 1
        segments: List[Segment] = []
        previous_end = -1
        for period in self.periods:
            start = max(bisect_left(self.frame_times, period.start), previous_end + 1)
            end = min(bisect_right(self.frame_times, period.end) - 1, last_frame)
            if end < start:
                continue
            segments.append(Segment(step=period.stage, start=start, end=end))
            previous_end = end
        return segments
