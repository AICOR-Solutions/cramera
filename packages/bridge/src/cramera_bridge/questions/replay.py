"""
The stretch of a recording worth replaying around one answered moment, in the frames of
the recording.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime

from typing_extensions import Optional, Sequence

from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.questions import ReplayWindow

REPLAY_LEAD_SECONDS = 1.0
"""
How long before its moment a replay starts.
"""

REPLAY_TAIL_SECONDS = 1.0
"""
How long after its moment a replay ends.
"""

MOMENT_TOLERANCE_SECONDS = 1.0
"""
How long before the first frame or after the last a moment may lie and still be
replayed: a detector and the recording look at the same state change one after the
other.
"""

# %% windows


@dataclass(frozen=True)
class FrameTimeline:
    """
    The frames of a recording by when each was recorded.
    """

    frame_times: Sequence[float] = field(default_factory=tuple)
    """
    The wall-clock time of every frame, in seconds since the epoch, in recording order;
    empty for a running world or a recording that did not stamp its frames.
    """

    @classmethod
    def of_trajectory(cls, trajectory: Optional[Trajectory]) -> FrameTimeline:
        """
        :param trajectory: A recorded trajectory, or None for a bundle without one.
        :return: The trajectory's frames by when each was recorded.
        """
        return cls(() if trajectory is None else tuple(trajectory.frame_times))

    def nearest_frame(self, at: float) -> int:
        """
        :param at: A wall-clock time in seconds since the epoch.
        :return: The frame recorded nearest to it, the earlier of two equally near.
        """
        after = bisect.bisect_left(self.frame_times, at)
        neighbours = [
            frame for frame in (after - 1, after) if 0 <= frame < len(self.frame_times)
        ]
        return min(neighbours, key=lambda frame: abs(self.frame_times[frame] - at))

    def covers(self, at: float) -> bool:
        """
        :param at: A wall-clock time in seconds since the epoch.
        :return: Whether it lies within the recording, give or take
            :data:`MOMENT_TOLERANCE_SECONDS`.
        """
        return bool(self.frame_times) and (
            self.frame_times[0] - MOMENT_TOLERANCE_SECONDS
            <= at
            <= self.frame_times[-1] + MOMENT_TOLERANCE_SECONDS
        )

    def window_around(self, moment: datetime) -> Optional[ReplayWindow]:
        """
        :param moment: When an answered thing happened.
        :return: The frames from shortly before to shortly after the moment, or None
            when the moment lies outside the recording.
        """
        at = moment.timestamp()
        if not self.covers(at):
            return None
        return ReplayWindow(
            first_frame=self.nearest_frame(at - REPLAY_LEAD_SECONDS),
            last_frame=self.nearest_frame(at + REPLAY_TAIL_SECONDS),
        )
