"""
Placing detected events on the frames of a recording, and keeping them when a recording
is trimmed, without the detectors.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from typing_extensions import Optional

from cramera_bridge.live.detected_events import (
    PLACEMENT_TOLERANCE_SECONDS,
    EventPlacement,
)
from cramera_bridge.live.recording import FrameRange
from cramera_bridge.live.segments import DetectedEventClipping
from cramera_protocol.bundle.scene import DetectedEvent, DetectedEventKind

RECORDING_START = datetime(2026, 10, 28, 14, 2, 30)
"""
When the recording's first frame was taken, in local time as the detectors stamp events.
"""

FRAME_INTERVAL = 0.5
"""
The seconds between two frames.
"""

FRAME_COUNT = 5
"""
How many frames the recording holds.
"""

FRAME_TIMES = [
    RECORDING_START.timestamp() + frame * FRAME_INTERVAL for frame in range(FRAME_COUNT)
]
"""
The time of every frame, in seconds since the epoch.
"""


def event(after: float, frame: Optional[int] = None) -> DetectedEvent:
    """
    :param after: The seconds after the recording's start it happened at.
    :param frame: The frame it is placed on.
    :return: A support event of a box on a table.
    """
    return DetectedEvent(
        name="box SupportEvent",
        event_type="SupportEvent",
        timestamp=(RECORDING_START + timedelta(seconds=after)).isoformat(),
        tracked_object="box",
        with_object="table",
        kind=DetectedEventKind.SUPPORT,
        frame=frame,
        keys=["box", "table"],
    )


# %% placement


def test_an_event_is_placed_on_the_nearest_frame():
    placement = EventPlacement(FRAME_TIMES)
    assert placement.frame_of(event(0.0)) == 0
    assert placement.frame_of(event(0.6)) == 1
    assert placement.frame_of(event(0.9)) == 2


def test_an_event_between_two_frames_is_placed_on_the_earlier():
    assert EventPlacement(FRAME_TIMES).frame_of(event(FRAME_INTERVAL / 2)) == 0


def test_an_event_just_outside_the_recording_is_placed_on_its_end():
    placement = EventPlacement(FRAME_TIMES)
    last = (FRAME_COUNT - 1) * FRAME_INTERVAL
    assert placement.frame_of(event(-PLACEMENT_TOLERANCE_SECONDS / 2)) == 0
    assert placement.frame_of(event(last + PLACEMENT_TOLERANCE_SECONDS / 2)) == (
        FRAME_COUNT - 1
    )


def test_an_event_long_before_or_after_the_recording_is_placed_nowhere():
    placement = EventPlacement(FRAME_TIMES)
    last = (FRAME_COUNT - 1) * FRAME_INTERVAL
    assert placement.frame_of(event(-2 * PLACEMENT_TOLERANCE_SECONDS)) is None
    assert placement.frame_of(event(last + 2 * PLACEMENT_TOLERANCE_SECONDS)) is None


def test_without_frames_no_event_is_placed():
    assert EventPlacement([]).placed([event(0.0)]) == [event(0.0)]


def test_placed_events_keep_everything_but_their_frame():
    [placed] = EventPlacement(FRAME_TIMES).placed([event(1.0)])
    assert placed == event(1.0, frame=2)


def test_only_the_events_within_the_recording_are_kept_for_it():
    events = [event(-10.0), event(1.0), event(100.0)]
    assert EventPlacement(FRAME_TIMES).within(events) == [event(1.0, frame=2)]


# %% trimming


def test_trimming_keeps_the_events_within_the_stretch_rebased():
    events = [event(0.0, frame=0), event(1.0, frame=2), event(2.0, frame=4)]
    clipped = DetectedEventClipping(FrameRange(first=1, last=3)).clip(events)
    assert [placed.frame for placed in clipped] == [1]


def test_trimming_keeps_an_event_placed_nowhere():
    clipped = DetectedEventClipping(FrameRange(first=1, last=3)).clip([event(0.0)])
    assert clipped == [event(0.0)]
