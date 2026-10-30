"""
The events detectors see while a run is published: offered live, written into the
recording on the frames they happened at, and trimmed with it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus

from typing_extensions import List

from cramera.http.messages import HttpMethod
from cramera_bridge.detections import DetectionRecorder
from cramera_bridge.documents import DocumentFile
from cramera_bridge.live.detected_events import DetectedEventSource
from cramera_bridge.visualization import (
    DETECTION_ENABLED,
    DetectionEnvironmentVariable,
    LiveVisualization,
)
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import ReservedSceneName
from cramera_protocol.bundle.scene import (
    DetectedEvent,
    DetectedEventKind,
    SceneDescription,
)
from cramera_protocol.live import Capability, LiveRoute
from cramera_protocol.live_messages import DetectedEvents, RecordingSaveRequest
from segmind.datastructures.events import TranslationEvent
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix

from .conftest import live_request

FRAME_COUNT = 5
"""
How many frames the published run records besides the one taken when it was attached.
"""

# %% a scripted source


@dataclass
class ScriptedDetections(DetectedEventSource):
    """
    Reports an event at chosen frames of the publisher's recording.
    """

    events_at: List[float] = field(default_factory=list)
    """
    When each event happened, in seconds since the epoch.
    """

    stopped: bool = False
    """
    Whether it was told to stop.
    """

    def events(self) -> List[DetectedEvent]:
        return [
            DetectedEvent(
                name=f"milk SupportEvent {position}",
                event_type="SupportEvent",
                timestamp=datetime.fromtimestamp(moment).isoformat(),
                tracked_object="milk",
                with_object="table",
                kind=DetectedEventKind.SUPPORT,
                keys=["milk", "table"],
            )
            for position, moment in enumerate(self.events_at)
        ]

    def stop(self) -> None:
        self.stopped = True


def move_milk(kitchen, publisher) -> None:
    """
    Move the milk along the table and record a frame per step.
    """
    for step in range(FRAME_COUNT):
        kitchen.milk_connection.origin = HomogeneousTransformationMatrix.from_xyz_rpy(
            1.0 + 0.1 * step, 0.1, 0.9, reference_frame=kitchen.root
        )
        publisher.observe_state_change()


def scene_of(locations, name: str = ReservedSceneName.RECORDING) -> SceneDescription:
    """
    :return: The scene description of a bundle in the local scenes.
    """
    return DocumentFile(locations.local_scenes / name / BundleFile.SCENE).read(
        SceneDescription
    )


# %% offered live


def test_a_publisher_without_detectors_offers_no_events(publisher):
    assert Capability.DETECTED_EVENTS not in publisher.capabilities()
    assert publisher.detected_events() == DetectedEvents()


def test_a_publisher_with_detectors_offers_their_events_on_its_frames(
    publisher, kitchen
):
    move_milk(kitchen, publisher)
    times = publisher.recording.frame_times()
    publisher.detections = ScriptedDetections([times[2]])
    [event] = publisher.detected_events().events
    assert Capability.DETECTED_EVENTS in publisher.capabilities()
    assert event.frame == 2
    assert event.keys == ["milk", "table"]


def test_the_events_are_answered_on_their_route(answerer, publisher, kitchen):
    move_milk(kitchen, publisher)
    publisher.detections = ScriptedDetections([publisher.recording.frame_times()[1]])
    answer = answerer.answer(live_request(HttpMethod.GET, LiveRoute.DETECTED_EVENTS))
    assert answer.status is HTTPStatus.OK
    [event] = DetectedEvents.from_json(json.loads(answer.body)).events
    assert event.frame == 1


# %% recorded


def test_the_recording_lists_the_events_on_the_frames_they_happened_at(
    publisher, kitchen, locations
):
    move_milk(kitchen, publisher)
    times = publisher.recording.frame_times()
    publisher.detections = ScriptedDetections([times[1], times[-1], times[-1] + 60])
    publisher.finish_recording()
    assert [event.frame for event in scene_of(locations).detected_events] == [
        1,
        len(times) - 1,
    ]


def test_a_saved_recording_keeps_the_events_of_its_frames(
    publisher, kitchen, locations
):
    move_milk(kitchen, publisher)
    times = publisher.recording.frame_times()
    publisher.detections = ScriptedDetections([times[0], times[3]])
    publisher.finish_recording()
    saved = publisher.save_recording(
        RecordingSaveRequest(name="moved", first_frame=2, last_frame=4)
    )
    assert [
        event.frame for event in scene_of(locations, saved.scene).detected_events
    ] == [1]


# %% the visualization's detectors


def visualization(kitchen, locations, **changes) -> LiveVisualization:
    """
    :return: A visualization of the kitchen without ROS.
    """
    return LiveVisualization(
        world=kitchen.world,
        port=0,
        locations=locations,
        read_ros_markers=False,
        read_robokudo_images=False,
        class_index=WorkspaceClassIndex(),
        **changes,
    )


def test_events_are_detected_when_the_environment_asks(kitchen, locations, monkeypatch):
    monkeypatch.setenv(DetectionEnvironmentVariable.DETECT_EVENTS, DETECTION_ENABLED)
    assert visualization(kitchen, locations).detect_events is True
    monkeypatch.delenv(DetectionEnvironmentVariable.DETECT_EVENTS)
    assert visualization(kitchen, locations).detect_events is False


def lower_milk(kitchen, recorder: DetectionRecorder) -> None:
    """
    Lower the milk onto the table step by step, letting the recorder look after every
    step.
    """
    for height in (1.3, 1.1, 0.95, 0.9, 0.9, 0.9):
        kitchen.milk_connection.origin = HomogeneousTransformationMatrix.from_xyz_rpy(
            1.0, 0.1, height, reference_frame=kitchen.root
        )
        recorder.tick()


def test_a_visualization_detecting_events_records_what_segmind_saw(kitchen, locations):
    started = visualization(kitchen, locations, detect_events=True).start()
    offered = started.publisher.capabilities()
    lower_milk(kitchen, started.detections)
    started.stop()
    [translation, *_] = [
        event
        for event in scene_of(locations).detected_events
        if event.event_type == TranslationEvent.__name__
    ]
    assert Capability.DETECTED_EVENTS in offered
    assert started.detections.is_watching is False
    assert translation.kind is DetectedEventKind.MOTION
    assert translation.frame is not None
    assert translation.keys == [str(kitchen.milk.id)]


def test_a_visualization_not_detecting_events_starts_no_segmind(kitchen, locations):
    started = visualization(kitchen, locations, detect_events=False).start()
    offered = started.publisher.capabilities()
    started.stop()
    assert started.detections is None
    assert Capability.DETECTED_EVENTS not in offered
