"""
The documents a live publisher serves and accepts.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.statecharts import ChartEdge
from cramera_protocol.exceptions import InvalidDocumentValue, MissingDocumentField
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.live import LiveInfo, LiveInfoKey
from cramera_protocol.live_messages import (
    ConnectionKind,
    ConstraintActivation,
    ConstraintMonitorType,
    ConstraintOperation,
    ConstraintRequest,
    ConstraintRequestKey,
    JointRequest,
    LivePlan,
    LivePlanNodeKey,
    LiveState,
    LiveStateKey,
    LiveStatechart,
    MarkerKind,
    MarkerOverlay,
    MarkerTopicRequest,
    MoveRequest,
    MoveRequestKey,
    ObjectCatalog,
    Quaternion,
    RecordingSaveRequest,
    RecordingState,
    RecordingStatus,
    RobotRoster,
    SceneDestination,
    ShapeKind,
    TeleoperationRequest,
    TransformFreshness,
    TransformGraph,
)

# %% documents a publisher serves


@pytest.mark.parametrize(
    "document_class, relative_path",
    [
        (LiveState, "live/state.json"),
        (LivePlan, "live/plan.json"),
        (LiveStatechart, "live/statechart.json"),
        (TransformGraph, "live/transforms.json"),
        (MarkerOverlay, "live/markers.json"),
        (ObjectCatalog, "live/objects.json"),
        (RobotRoster, "live/robots.json"),
        (RecordingStatus, "live/recording_status.json"),
        (RecordingSaveRequest, "live/recording_save_request.json"),
        (MoveRequest, "live/move_request.json"),
        (JointRequest, "live/joint_request.json"),
        (TeleoperationRequest, "live/teleoperation_request.json"),
        (ConstraintRequest, "live/constraint_request.json"),
        (LiveInfo, "live/info.json"),
    ],
)
def test_live_documents_round_trip(read_json, document_class, relative_path):
    document = document_class.from_json(read_json(relative_path))
    assert document_class.from_json(document.to_json()) == document


def test_the_state_reads_poses_by_their_keys(read_json):
    data = read_json("live/state.json")
    state = LiveState.from_json(data)
    assert state.base == Pose.from_json(data[LiveStateKey.BASE])
    assert state.model_bases.keys() == data[LiveStateKey.MODEL_BASES].keys()
    assert state.sequence_number == data[LiveStateKey.SEQUENCE_NUMBER]


def test_plan_nodes_keep_the_native_status_names(read_json):
    data = read_json("live/plan.json")
    plan = LivePlan.from_json(data)
    assert [node.status for node in plan.nodes] == [
        node[LivePlanNodeKey.STATUS] for node in data["nodes"]
    ]
    assert plan.nodes[1].constraints[0].monitor == ConstraintMonitorType.VECTORS_ALIGNED


def test_statechart_edges_are_the_bundle_edges(read_json):
    chart = LiveStatechart.from_json(read_json("live/statechart.json"))
    assert isinstance(chart.edges[0], ChartEdge)


def test_transforms_read_kind_and_freshness(read_json):
    graph = TransformGraph.from_json(read_json("live/transforms.json"))
    assert graph.connections[0].kind is ConnectionKind.FREE
    assert graph.connections[1].freshness is TransformFreshness.STATIC
    assert graph.connections[1].age_seconds is None


def test_markers_and_shapes_read_their_kinds(read_json):
    overlay = MarkerOverlay.from_json(read_json("live/markers.json"))
    catalog = ObjectCatalog.from_json(read_json("live/objects.json"))
    assert overlay.markers[0].kind is MarkerKind.LINE_LIST
    assert overlay.markers[0].points[1] == Vector3(0.1, 0.2, 0.3)
    assert [shape.kind for shape in catalog.objects[0].shapes] == [
        ShapeKind.MESH,
        ShapeKind.CYLINDER,
    ]


def test_a_body_without_shapes_is_published_without_geometry(read_json):
    catalog = ObjectCatalog.from_json(read_json("live/objects.json"))
    assert catalog.objects[1].shapes == []


def test_the_recording_status_reads_its_state(read_json):
    status = RecordingStatus.from_json(read_json("live/recording_status.json"))
    assert status.state is RecordingState.FINALIZED


def test_a_save_request_defaults_to_the_local_directory():
    request = RecordingSaveRequest(name="run")
    assert request.destination is SceneDestination.LOCAL
    assert RecordingSaveRequest.from_json({"name": "run"}) == request


def test_the_information_reports_the_bundle_signature(read_json):
    data = read_json("live/info.json")
    info = LiveInfo.from_json(data)
    assert info.running is True
    assert info.bundle_signature == data[LiveInfoKey.BUNDLE_SIGNATURE]


# %% requests


def test_a_move_request_reads_position_and_orientation(read_json):
    data = read_json("live/move_request.json")
    request = MoveRequest.from_json(data)
    assert request.position == Vector3.from_json(data[MoveRequestKey.POSITION])
    assert request.quaternion == Quaternion.from_json(data[MoveRequestKey.QUATERNION])
    assert request.final is True


def test_a_move_request_with_an_infinite_coordinate_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        MoveRequest.from_json(
            read_json("live/move_request_with_infinite_position.json")
        )


def test_a_joint_request_with_a_missing_joint_is_refused():
    with pytest.raises(MissingDocumentField):
        JointRequest.from_json({"position": 0.1})


def test_a_teleoperation_request_with_a_text_position_is_refused():
    with pytest.raises(InvalidDocumentValue):
        TeleoperationRequest.from_json({"arm": "left_arm", "position": "up"})


def test_a_constraint_request_reads_the_browser_shape(read_json):
    data = read_json("live/constraint_request.json")
    request = ConstraintRequest.from_json(data)
    assert request.operation is ConstraintOperation.ATTACH_MONITOR
    assert request.apply is ConstraintActivation.NEXT_ACTIVATION
    assert request.monitor.monitor_type is ConstraintMonitorType.HEIGHT
    assert request.monitor.parameters == data[ConstraintRequestKey.MONITOR]["params"]


def test_a_constraint_request_naming_a_goal_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        ConstraintRequest.from_json(read_json("live/constraint_request_with_goal.json"))


def test_a_marker_topic_must_start_with_a_slash(read_json):
    with pytest.raises(InvalidDocumentValue):
        MarkerTopicRequest.from_json(read_json("live/marker_topic_without_slash.json"))
