"""
The laboratory's routes, the commands sent to the contact simulation and the state it
measures.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import (
    InvalidDocumentValue,
    UnexpectedDocumentField,
)
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.laboratory.knowledge import ManualEdition
from cramera_protocol.laboratory.layout import Quaternion
from cramera_protocol.laboratory.physics import (
    CentrifugeAction,
    CentrifugeRequest,
    ContactPhysicsControls,
    ContactPhysicsKey,
    DispenserState,
    EmptyRequest,
    LaboratoryRoute,
    LiquidStateKey,
    ManualRequest,
    SimulationAnswer,
    SimulationAnswerKey,
    SimulationState,
    SnapshotKey,
    TargetRequest,
    TargetRequestKey,
)

# %% answers


def test_a_running_answer_reads_every_measurement(read_json):
    data = read_json("laboratory/simulation_answer.json")
    answer = SimulationAnswer.from_json(data)
    snapshot = answer.snapshot
    written = data[SimulationAnswerKey.SNAPSHOT]
    assert answer.state is SimulationState.RUNNING
    assert snapshot.objects["tube_clear"] == Pose.from_json(
        written[SnapshotKey.OBJECTS]["tube_clear"]
    )
    assert (
        snapshot.liquid.supplied == written[SnapshotKey.LIQUID][LiquidStateKey.SUPPLIED]
    )
    assert snapshot.centrifuge.holders[1].key is None
    assert snapshot.dispenser.state is DispenserState.BLOCKED
    assert snapshot.drawer.closed and not snapshot.drawer.fully_open
    assert snapshot.refrigerator.positions[0].key is None


def test_a_running_answer_round_trips(read_json):
    data = read_json("laboratory/simulation_answer.json")
    assert SimulationAnswer.from_json(data).to_json() == data


def test_an_idle_answer_has_no_snapshot(read_json):
    data = read_json("laboratory/idle_answer.json")
    answer = SimulationAnswer.from_json(data)
    assert answer.state is SimulationState.IDLE and answer.snapshot is None
    assert answer.to_json() == data


# %% commands


def test_a_target_request_reads_its_position_and_orientation(read_json):
    data = read_json("laboratory/target_request.json")
    request = TargetRequest.from_json(data)
    assert request.position == Vector3.from_json(data[TargetRequestKey.POSITION])
    assert request.orientation == Quaternion.from_json(
        data[TargetRequestKey.ORIENTATION]
    )


@pytest.mark.parametrize(
    "file_name, error",
    [
        ("target_request_with_short_position.json", InvalidDocumentValue),
        ("target_request_with_force.json", UnexpectedDocumentField),
    ],
)
def test_a_malformed_target_request_is_refused(read_json, file_name, error):
    with pytest.raises(error):
        TargetRequest.from_json(read_json(f"laboratory/invalid/{file_name}"))


def test_a_centrifuge_request_names_its_action(read_json):
    request = CentrifugeRequest.from_json(
        read_json("laboratory/centrifuge_secure_request.json")
    )
    assert request.action is CentrifugeAction.SECURE
    assert request.speed is None and request.duration is None


def test_an_unknown_centrifuge_action_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        CentrifugeRequest.from_json(
            read_json("laboratory/invalid/centrifuge_request_with_unknown_action.json")
        )


def test_a_manual_request_names_a_shipped_edition(read_json):
    request = ManualRequest.from_json(read_json("laboratory/manual_request.json"))
    assert request.edition is ManualEdition.SECOND and request.document is None


def test_an_empty_request_takes_no_keys(read_json):
    assert EmptyRequest.from_json({}) == EmptyRequest()
    with pytest.raises(UnexpectedDocumentField):
        EmptyRequest.from_json(
            read_json("laboratory/invalid/empty_request_with_key.json")
        )


# %% controls


def test_the_controls_round_trip(read_json):
    data = read_json("laboratory/contact_physics.json")
    controls = ContactPhysicsControls.from_json(data)
    assert controls.vessels == data[ContactPhysicsKey.VESSELS]
    assert controls.to_json() == data


def test_routes_lie_below_the_plugin_without_a_leading_slash():
    assert not any(route.startswith("/") for route in LaboratoryRoute)


def test_the_browser_reads_the_routes_and_state_keys():
    assert {LaboratoryRoute, SnapshotKey, SimulationState} <= set(BROWSER_ENUMERATIONS)
