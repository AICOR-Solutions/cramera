"""
The events detectors saw during a run, placed on the frames of the recording they
happened in.

Nothing here imports the detectors: :class:`~cramera_bridge.detections.DetectionRecorder`
is the source that does, so the publisher and the recordings handle protocol documents
only.
"""

from __future__ import annotations

import bisect
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime

from typing_extensions import List, Optional, Sequence

from cramera_protocol.bundle.scene import DetectedEvent

PLACEMENT_TOLERANCE_SECONDS = 1.0
"""
How long before the first frame or after the last an event may happen and still be
placed on that frame: the detectors and the recording look at the same state change one
after the other.
"""

# %% source


class DetectedEventSource(ABC):
    """
    Delivers the events detectors saw during a run.
    """

    @abstractmethod
    def events(self) -> List[DetectedEvent]:
        """
        :return: Everything detected so far, oldest first, not placed on any frame.
        """

    @abstractmethod
    def stop(self) -> None:
        """
        Stop detecting; what was detected stays readable.
        """


# %% placement


@dataclass(frozen=True)
class EventPlacement:
    """
    Places events on the frames of a recording by when they happened.
    """

    frame_times: Sequence[float]
    """
    The wall-clock time of every frame, in seconds since the epoch, in recording order.
    """

    def frame_of(self, event: DetectedEvent) -> Optional[int]:
        """
        :param event: An event, stamped with the local time it happened at.
        :return: The frame nearest to when it happened, the earlier of two equally near;
            None when it happened outside the recording.
        """
        if not self.frame_times:
            return None
        moment = datetime.fromisoformat(event.timestamp).timestamp()
        if (
            moment < self.frame_times[0] - PLACEMENT_TOLERANCE_SECONDS
            or moment > self.frame_times[-1] + PLACEMENT_TOLERANCE_SECONDS
        ):
            return None
        after = bisect.bisect_left(self.frame_times, moment)
        neighbours = [
            frame for frame in (after - 1, after) if 0 <= frame < len(self.frame_times)
        ]
        return min(neighbours, key=lambda frame: abs(self.frame_times[frame] - moment))

    def placed(self, events: List[DetectedEvent]) -> List[DetectedEvent]:
        """
        :param events: Events of the run.
        :return: The same events, each on its frame, or on none when it happened outside
            the recording.
        """
        return [replace(event, frame=self.frame_of(event)) for event in events]

    def within(self, events: List[DetectedEvent]) -> List[DetectedEvent]:
        """
        :param events: Events of the run.
        :return: The events that happened during the recording, each on its frame.
        """
        return [event for event in self.placed(events) if event.frame is not None]
