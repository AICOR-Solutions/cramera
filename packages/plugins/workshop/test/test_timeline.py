"""
The steps of a recorded workshop demo: one per stage of its plan, covering the frames
recorded while the stage ran.
"""

from __future__ import annotations

from cramera_protocol.bundle.scene import Segment
from cramera_workshop.timeline import StageTimeline

from .dataset.timelines import (
    BLINK,
    CARRY,
    FETCH,
    FRAME_TIMES,
    PLACE,
    SHARED_END,
    SHARED_START,
)


def test_each_stage_covers_the_frames_recorded_while_it_ran():
    timeline = StageTimeline(FRAME_TIMES, [FETCH, CARRY, PLACE])
    assert timeline.segments() == [
        Segment(step=FETCH.stage, start=0, end=3),
        Segment(step=CARRY.stage, start=4, end=6),
        Segment(step=PLACE.stage, start=7, end=len(FRAME_TIMES) - 1),
    ]


def test_a_stage_no_frame_shows_is_left_out():
    timeline = StageTimeline(FRAME_TIMES, [CARRY, BLINK, PLACE])
    assert [segment.step for segment in timeline.segments()] == [
        CARRY.stage,
        PLACE.stage,
    ]


def test_a_frame_shared_by_two_stages_belongs_to_the_first():
    first, second = StageTimeline(FRAME_TIMES, [SHARED_END, SHARED_START]).segments()
    assert (first.end, second.start) == (3, 4)


def test_a_recording_without_frames_has_no_steps():
    assert StageTimeline([], [FETCH]).segments() == []
