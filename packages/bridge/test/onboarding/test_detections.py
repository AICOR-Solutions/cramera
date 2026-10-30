"""
Segmind segmenting a run into events, ticked by hand where the order matters.
"""

from __future__ import annotations

from segmind.datastructures.events import (
    ContactEvent,
    SupportEvent,
    TranslationEvent,
)
from semantic_digital_twin.world import World

from cramera_bridge.detections import EVENT_NAME_SEPARATOR, DetectionRecorder
from cramera_protocol.bundle.scene import DetectedEventKind

from ..dataset.onboarding.sliding_box_demo import BOX_HEIGHTS

# %% helpers


def lower_box(sliding_box, recorder: DetectionRecorder) -> None:
    """
    Move the box down onto the table, letting the recorder look after every move and at
    the box at rest.
    """
    recorder.tick()
    for height in BOX_HEIGHTS:
        sliding_box.move_box(height)
        recorder.tick()
    for _ in range(recorder.segmentation.ticks_to_see_the_world_at_rest):
        recorder.tick()


def events_of_type(recorder: DetectionRecorder, event_type: type) -> list:
    """
    :return: The recorder's events of one type.
    """
    return [
        event for event in recorder.events() if event.event_type == event_type.__name__
    ]


# %% what is watched


def test_the_run_s_objects_are_watched(sliding_box):
    assert DetectionRecorder(sliding_box.world).watched_bodies() == [sliding_box.box]


def test_a_world_without_objects_is_not_segmented():
    recorder = DetectionRecorder(World()).start()
    recorder.tick()
    recorder.stop()
    assert recorder.segmentation is None
    assert recorder.is_watching is False
    assert recorder.events() == []


# %% detecting


def test_a_recorder_that_never_compiled_detects_nothing(sliding_box):
    recorder = DetectionRecorder(sliding_box.world)
    for height in BOX_HEIGHTS:
        sliding_box.move_box(height)
    recorder.tick()
    assert recorder.events() == []


def test_a_compiled_recorder_detects_what_the_world_does(sliding_box):
    recorder = DetectionRecorder(sliding_box.world).compile()
    lower_box(sliding_box, recorder)
    event_types = {event.event_type for event in recorder.events()}
    assert {
        ContactEvent.__name__,
        SupportEvent.__name__,
        TranslationEvent.__name__,
    } <= event_types


def test_an_event_names_its_bodies_its_kind_and_their_keys(sliding_box):
    recorder = DetectionRecorder(sliding_box.world).compile()
    lower_box(sliding_box, recorder)
    [support] = events_of_type(recorder, SupportEvent)
    assert support.tracked_object == str(sliding_box.box.name)
    assert support.with_object == str(sliding_box.table.name)
    assert support.name == EVENT_NAME_SEPARATOR.join(
        (str(sliding_box.box.name), SupportEvent.__name__)
    )
    assert support.kind is DetectedEventKind.SUPPORT
    assert support.keys == [str(sliding_box.box.id), str(sliding_box.table.name)]
    assert support.frame is None


def test_an_event_without_a_second_body_names_none(sliding_box):
    recorder = DetectionRecorder(sliding_box.world).compile()
    lower_box(sliding_box, recorder)
    [translation, *_] = events_of_type(recorder, TranslationEvent)
    assert translation.with_object is None
    assert translation.keys == [str(sliding_box.box.id)]


# %% the thread


def test_a_started_recorder_watches_until_stopped_and_keeps_its_events(sliding_box):
    recorder = DetectionRecorder(sliding_box.world).start()
    watching = recorder.is_watching
    for height in BOX_HEIGHTS:
        sliding_box.move_box(height)
    recorder.stop()
    detected = recorder.events()
    recorder.stop()
    assert watching is True
    assert recorder.is_watching is False
    assert events_of_type(recorder, SupportEvent)
    assert recorder.events() == detected


def test_stopping_a_recorder_that_never_started_changes_nothing(sliding_box):
    recorder = DetectionRecorder(sliding_box.world).compile()
    recorder.stop()
    assert recorder.is_watching is False
