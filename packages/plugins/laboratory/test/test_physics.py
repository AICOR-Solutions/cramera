"""
The bench laboratory's contact simulation in MuJoCo: support, pulling, the liquid's
weight, the scale, the centrifuge, the refrigerator, the drawer and the dispensing
station, each checked against what the simulation measures.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from cramera_laboratory.dispenser import ReagentChannel
from cramera_laboratory.exceptions import (
    OperationRefused,
    Refusal,
    TooFewSamples,
    UnknownObject,
    ValueOutOfRange,
)
from cramera_laboratory.liquid import LaboratoryVessel
from cramera_laboratory.physics.mass import GRAMS_PER_KILOGRAM
from cramera_laboratory.physics.simulation import LaboratoryPhysics
from cramera_laboratory.session import ContactSimulation
from cramera_protocol.geometry import Vector3
from cramera_protocol.laboratory.knowledge import ManualEdition
from cramera_protocol.laboratory.physics import (
    CentrifugeAction,
    CentrifugeRequest,
    DispenserAction,
    DispenserRequest,
    DispenserState,
    LiquidRequest,
    ManualRequest,
    OpeningAction,
    OpeningRequest,
    SimulationSnapshot,
    TargetRequest,
)
from cramera_protocol.laboratory.layout import Quaternion

SETTLE_STEPS = 1500
"""
How long the tests let the laboratory settle, in steps.
"""

POSITION_TOLERANCE = 0.001
"""
How far a resting object may drift, in metres.
"""

LIFT = 0.17
"""
How high a vessel is lifted out of the rack, in metres.
"""

CLEAR_LIFT = 0.35
"""
How high a vessel is lifted to pass over the centrifuge's housing, in metres.
"""

HOLDER_CLEARANCE = 0.01
"""
How far above a holder's floor a vessel is lowered before it is let go, in metres.
"""

PAN_CLEARANCE = 0.002
"""
How far above the scale's pan a vessel is lowered before it is let go, in metres.
"""

STATION_APPROACH = -0.25
"""
The y coordinate in front of the dispensing station a vessel is slid in from, below its
nozzle.
"""

STATION_CLEARANCE = 0.004
"""
How far above its place at the station a vessel is slid in, in metres.
"""

SAMPLE_VOLUME = 5.0
"""
The liquid each centrifuge sample holds, in millilitres.
"""

GLASS_GRAMS = 12.0
"""
The mass of an empty vessel the bundle authors, in grams.
"""

SCALE_TOLERANCE = 0.1
"""
How far the scale's reading may lie from the vessel's mass, in grams.
"""

CYCLE_SPEED = 120.0
"""
The speed of the tests' centrifuge cycle, in revolutions per minute.
"""

CYCLE_SECONDS = 1.0
"""
The length of the tests' centrifuge cycle at speed, in seconds.
"""

SPEED_TOLERANCE = 0.05
"""
The share of the cycle speed the rotor must reach.
"""

# %% fixtures


@pytest.fixture(scope="module")
def physics(bench_laboratory) -> LaboratoryPhysics:
    """
    :return: The bench laboratory's simulation, shared by the module's tests.
    """
    return LaboratoryPhysics(bench_laboratory)


@pytest.fixture
def laboratory(physics) -> LaboratoryPhysics:
    """
    :return: The shared simulation, reset to the authored laboratory.
    """
    physics.reset()
    return physics


def position(physics: LaboratoryPhysics, key: str) -> np.ndarray:
    """
    :param physics: The simulation.
    :param key: A free object.
    :return: Its measured position.
    """
    return np.array(physics.data.xpos[physics.objects[key]])


def seconds(physics: LaboratoryPhysics, duration: float) -> None:
    """
    :param physics: The simulation.
    :param duration: How long to simulate, in seconds.
    """
    physics.step(round(duration / physics.timestep))


def pull(physics: LaboratoryPhysics, key: str, target, duration: float = 2.0) -> None:
    """
    Pull an object towards a target for a while.

    :param physics: The simulation.
    :param key: The object.
    :param target: Where to.
    :param duration: For how long, in seconds.
    """
    physics.set_target(TargetRequest(key=key, position=Vector3(*map(float, target))))
    seconds(physics, duration)


def carry(physics: LaboratoryPhysics, key: str, destination, clearance: float) -> None:
    """
    Lift an object, carry it above a destination, lower it there and let go.

    :param physics: The simulation.
    :param key: The object.
    :param destination: Where its origin should end up.
    :param clearance: How far above the destination it is let go, in metres.
    """
    start = position(physics, key)
    height = start[2] + CLEAR_LIFT
    pull(physics, key, [start[0], start[1], height], 3.0)
    pull(physics, key, [destination[0], destination[1], height], 4.0)
    pull(
        physics, key, [destination[0], destination[1], destination[2] + clearance], 4.0
    )
    physics.release()
    physics.step(SETTLE_STEPS)


# %% support and pulling


def test_the_simulation_is_a_contact_simulation(laboratory):
    assert isinstance(laboratory, ContactSimulation)


def test_resting_objects_stay_on_their_supports(laboratory):
    before = {key: position(laboratory, key) for key in laboratory.objects}
    laboratory.step(SETTLE_STEPS)
    snapshot = laboratory.snapshot()
    for key, start in before.items():
        np.testing.assert_allclose(
            position(laboratory, key), start, atol=POSITION_TOLERANCE
        )
    assert snapshot.contacts and all(contact.force > 0 for contact in snapshot.contacts)
    assert np.isfinite(snapshot.energy)


def test_a_sideways_pull_is_stopped_by_the_rack(laboratory):
    key = LaboratoryVessel.CLEAR
    start = position(laboratory, key)
    pull(laboratory, key, start + [0.03, 0.0, 0.0], 1.5)
    snapshot = laboratory.snapshot()
    assert position(laboratory, key)[0] < start[0] + 0.008
    assert snapshot.maximum_applied_force <= laboratory.parameters.pull.maximum_force
    assert any(
        {contact.first_body, contact.second_body} == {key, "laboratory_rack"}
        for contact in snapshot.contacts
    )


def test_a_vessel_lifts_out_and_back_into_its_slot(laboratory):
    key = LaboratoryVessel.CLEAR
    start = position(laboratory, key)
    pull(laboratory, key, start + [0.0, 0.0, LIFT])
    np.testing.assert_allclose(
        position(laboratory, key), start + [0, 0, LIFT], atol=0.002
    )
    pull(laboratory, key, start)
    laboratory.release()
    laboratory.step(SETTLE_STEPS)
    np.testing.assert_allclose(
        position(laboratory, key), start, atol=POSITION_TOLERANCE
    )


def test_a_released_vessel_falls(laboratory):
    key = LaboratoryVessel.CLEAR
    pull(laboratory, key, position(laboratory, key) + [0.0, 0.0, LIFT])
    raised = position(laboratory, key)[2]
    laboratory.release()
    laboratory.step(100)
    assert laboratory.snapshot().target is None
    assert position(laboratory, key)[2] < raised - 0.02


def test_reset_restores_the_authored_laboratory(laboratory):
    authored = laboratory.snapshot().objects
    pull(
        laboratory,
        LaboratoryVessel.CLEAR,
        position(laboratory, LaboratoryVessel.CLEAR) + [0, 0, LIFT],
        1.0,
    )
    laboratory.reset()
    snapshot = laboratory.snapshot()
    assert snapshot.objects == authored
    assert snapshot.target is None and snapshot.time == 0
    assert snapshot.maximum_applied_force == 0


def test_a_pull_outside_the_bounds_or_of_the_environment_is_refused(laboratory):
    with pytest.raises(ValueOutOfRange):
        laboratory.set_target(
            TargetRequest(key=LaboratoryVessel.CLEAR, position=Vector3(0, 0, 9))
        )
    with pytest.raises(UnknownObject):
        laboratory.set_target(
            TargetRequest(key="laboratory_rack", position=Vector3(0, 0, 1))
        )


def test_a_turned_target_is_normalized(laboratory):
    key = LaboratoryVessel.CLEAR
    laboratory.set_target(
        TargetRequest(
            key=key,
            position=Vector3(*position(laboratory, key)),
            orientation=Quaternion(0, 0, 0, 2),
        )
    )
    assert laboratory.snapshot().target.orientation == Quaternion(0.0, 0.0, 0.0, 1.0)


# %% liquid and scale


def test_liquid_adds_its_weight_to_the_vessel(laboratory):
    body = laboratory.objects[LaboratoryVessel.CLEAR]
    dry = laboratory.model.body_mass[body]
    laboratory.fill(LiquidRequest(key=LaboratoryVessel.CLEAR, volume=SAMPLE_VOLUME))
    assert laboratory.model.body_mass[body] - dry == pytest.approx(
        SAMPLE_VOLUME / GRAMS_PER_KILOGRAM
    )


def test_the_scale_weighs_a_vessel_placed_on_its_pan(laboratory):
    pan = laboratory.laboratory.bench().scale.pan_position.to_json()
    carry(laboratory, LaboratoryVessel.RESERVE, pan, 0.002)
    reading = laboratory.scale.reading()
    assert reading.grams == pytest.approx(GLASS_GRAMS, abs=SCALE_TOLERANCE)
    assert reading.objects == [LaboratoryVessel.RESERVE]
    seconds(laboratory, 1.0)
    laboratory.tare()
    seconds(laboratory, 0.2)
    assert abs(laboratory.scale.reading().grams) < SCALE_TOLERANCE


def test_an_unsettled_scale_refuses_to_tare(laboratory):
    laboratory.scale.reset()
    with pytest.raises(OperationRefused) as refused:
        laboratory.tare()
    assert refused.value.refusal is Refusal.UNSETTLED_SCALE


# %% centrifuge


def load(laboratory: LaboratoryPhysics, key: str, slot: str) -> None:
    """
    Fill a vessel, carry it into a holder and secure it.

    :param laboratory: The simulation.
    :param key: The vessel.
    :param slot: The holder.
    """
    laboratory.fill(LiquidRequest(key=key, volume=SAMPLE_VOLUME))
    holder = laboratory.centrifuge.holders[slot]
    carry(
        laboratory, key, laboratory.centrifuge.holder_position(holder), HOLDER_CLEARANCE
    )
    laboratory.operate_centrifuge(
        CentrifugeRequest(action=CentrifugeAction.SECURE, slot=slot, key=key)
    )


def test_a_balanced_pair_runs_a_timed_cycle_and_stops(laboratory):
    load(laboratory, LaboratoryVessel.CLEAR, "C1")
    with pytest.raises(TooFewSamples):
        laboratory.operate_centrifuge(CentrifugeRequest(action=CentrifugeAction.START))
    load(laboratory, LaboratoryVessel.RESERVE, "C3")
    with pytest.raises(OperationRefused) as refused:
        laboratory.operate_centrifuge(CentrifugeRequest(action=CentrifugeAction.START))
    assert refused.value.refusal is Refusal.NOT_READY_TO_START
    laboratory.operate_centrifuge(CentrifugeRequest(action=CentrifugeAction.CLOSE))
    seconds(laboratory, 3.0)
    state = laboratory.centrifuge.state()
    assert state.lid_closed and state.balanced and state.knowledge.evaluation.allowed
    laboratory.operate_centrifuge(
        CentrifugeRequest(
            action=CentrifugeAction.START, speed=CYCLE_SPEED, duration=CYCLE_SECONDS
        )
    )
    seconds(laboratory, 2.5)
    assert laboratory.centrifuge.speed == pytest.approx(
        CYCLE_SPEED, rel=SPEED_TOLERANCE
    )
    with pytest.raises(OperationRefused) as refused:
        laboratory.operate_centrifuge(CentrifugeRequest(action=CentrifugeAction.OPEN))
    assert refused.value.refusal is Refusal.ROTOR_TURNING
    seconds(laboratory, 3.5)
    state = laboratory.centrifuge.state()
    assert not state.running and state.remaining == 0
    assert [holder.key for holder in state.holders if holder.key] == [
        LaboratoryVessel.CLEAR,
        LaboratoryVessel.RESERVE,
    ]
    with pytest.raises(OperationRefused) as refused:
        laboratory.set_target(
            TargetRequest(key=LaboratoryVessel.CLEAR, position=Vector3(0, 0, 1))
        )
    assert refused.value.refusal is Refusal.CLAMPED_VESSEL


def test_a_vessel_above_a_holder_cannot_be_secured(laboratory):
    key = LaboratoryVessel.CLEAR
    holder = laboratory.centrifuge.holders["C1"]
    target = laboratory.centrifuge.holder_position(holder)
    start = position(laboratory, key)
    pull(laboratory, key, [start[0], start[1], start[2] + CLEAR_LIFT], 3.0)
    pull(laboratory, key, [target[0], target[1], start[2] + CLEAR_LIFT], 4.0)
    with pytest.raises(OperationRefused) as refused:
        laboratory.operate_centrifuge(
            CentrifugeRequest(action=CentrifugeAction.SECURE, slot="C1", key=key)
        )
    assert refused.value.refusal is Refusal.NOT_SEATED


def test_the_second_manual_asks_for_two_pairs(laboratory):
    laboratory.read_manual(ManualRequest(edition=ManualEdition.SECOND))
    evaluation = laboratory.centrifuge.state().knowledge.evaluation
    assert laboratory.centrifuge.knowledge.active.minimum_samples == 4
    assert not evaluation.allowed
    laboratory.read_manual(ManualRequest(edition=ManualEdition.FIRST))


# %% refrigerator, drawer, dispensing station


def test_the_refrigerator_door_opens_and_the_cabinet_warms(laboratory):
    laboratory.operate_refrigerator(OpeningRequest(action=OpeningAction.OPEN))
    seconds(laboratory, 4.0)
    state = laboratory.refrigerator.state()
    assert state.door_open and not state.door_closed
    assert (
        state.temperature
        > laboratory.laboratory.bench().refrigerator.target_temperature
    )
    assert laboratory.snapshot().joints[laboratory.refrigerator.layout.door_joint] > 0


def test_the_drawer_opens_with_a_hand_strong_force(laboratory):
    laboratory.operate_drawer(OpeningRequest(action=OpeningAction.OPEN))
    seconds(laboratory, 5.0)
    state = laboratory.drawer.state()
    assert state.fully_open and not state.closed
    laboratory.operate_drawer(OpeningRequest(action=OpeningAction.CLOSE))
    seconds(laboratory, 5.0)
    assert laboratory.drawer.state().closed


def test_a_dose_flows_into_a_vessel_placed_at_the_station(laboratory):
    key = LaboratoryVessel.CLEAR
    station = laboratory.dispenser.layout.target_position.to_json()
    start = position(laboratory, key)
    raised = start[2] + LIFT
    low = station[2] + STATION_CLEARANCE
    for waypoint in (
        [start[0], start[1], raised],
        [start[0], STATION_APPROACH, raised],
        [station[0], STATION_APPROACH, raised],
        [station[0], STATION_APPROACH, low],
        [station[0], station[1], low],
    ):
        pull(laboratory, key, waypoint, 3.0)
    laboratory.release()
    laboratory.step(SETTLE_STEPS)
    laboratory.operate_dispenser(
        DispenserRequest(
            action=DispenserAction.DISPENSE,
            key=LaboratoryVessel.CLEAR,
            channel=ReagentChannel.TEAL,
            volume=0.5,
        )
    )
    seconds(laboratory, 1.0)
    assert laboratory.dispenser.state is DispenserState.COMPLETE
    assert laboratory.liquid.vessels[LaboratoryVessel.CLEAR].volume == pytest.approx(
        0.5
    )


def test_filling_during_a_dose_is_refused(laboratory):
    laboratory.dispenser.state = DispenserState.DISPENSING
    laboratory.dispenser.key = LaboratoryVessel.CLEAR
    with pytest.raises(OperationRefused) as refused:
        laboratory.fill(LiquidRequest(key=LaboratoryVessel.CLEAR, volume=1.0))
    assert refused.value.refusal is Refusal.DOSE_DELIVERING


def test_the_bench_has_no_instrument_collection(laboratory):
    from cramera_protocol.laboratory.physics import InstrumentPose, InstrumentRequest

    with pytest.raises(OperationRefused):
        laboratory.move_instrument(
            InstrumentRequest(instrument="vortex_mixer", pose=InstrumentPose.REST)
        )


# %% reports


def test_the_snapshot_round_trips_and_names_every_part(laboratory):
    laboratory.step(SETTLE_STEPS)
    snapshot = laboratory.snapshot()
    assert (
        SimulationSnapshot.from_json(json.loads(json.dumps(snapshot.to_json())))
        == snapshot
    )
    assert set(snapshot.objects) == set(laboratory.objects)
    assert set(snapshot.liquid.vessels) == set(laboratory.liquid.fills)
    assert snapshot.rack.supports
    occupants = {slot.identifier: slot.key for slot in snapshot.rack.slots}
    assert {
        placement.slot: occupants[placement.slot]
        for placement in laboratory.laboratory.bench().tubes
    } == {
        placement.slot: placement.key
        for placement in laboratory.laboratory.bench().tubes
    }


def test_the_controls_describe_the_laboratory(laboratory):
    controls = laboratory.controls()
    assert controls.laboratory == laboratory.laboratory.name
    assert controls.vessels == list(laboratory.liquid.fills)
    assert (
        controls.cycles.maximum_speed
        == laboratory.laboratory.bench().centrifuge.maximum_speed
    )
