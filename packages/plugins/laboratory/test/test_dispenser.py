"""
The dispensing station: doses flow only into an open, upright receiver under the nozzle,
and every millilitre is accounted for.
"""

from __future__ import annotations

import numpy as np
import pytest

from cramera_laboratory.dispenser import (
    DispenserParameters,
    LaboratoryDispenser,
    ReagentChannel,
)
from cramera_laboratory.exceptions import (
    OperationRefused,
    Refusal,
    UnknownObject,
    ValueOutOfRange,
)
from cramera_laboratory.geometry import RigidPose
from cramera_laboratory.liquid import (
    LaboratoryLiquid,
    LaboratoryVessel,
    VesselShape,
    laboratory_fills,
)
from cramera_protocol.laboratory.physics import (
    DispenserAction,
    DispenserRequest,
    DispenserState,
)

DOSE = 1.0
"""
The dose of the tests, in millilitres.
"""

STEP = 0.02
"""
The step of the tests, in seconds.
"""


@pytest.fixture
def bench(bench_laboratory):
    """
    :return: The bench of the shipped laboratory.
    """
    return bench_laboratory.bench()


@pytest.fixture
def poses(bench):
    """
    :return: The vessels at their spawn poses, the clear vessel moved under the nozzle.
    """
    station = np.array(bench.dispenser.target_position.to_json())
    return {
        LaboratoryVessel.CLEAR: RigidPose(position=station, rotation=np.eye(3)),
        LaboratoryVessel.AMBER: RigidPose(
            position=station + [0.2, 0.0, 0.0], rotation=np.eye(3)
        ),
        bench.stopper.key: RigidPose.of_pose(bench.stopper.home),
    }


@pytest.fixture
def dispenser(bench, poses) -> LaboratoryDispenser:
    """
    :return: The station with the clear and amber vessels.
    """
    shape = VesselShape()
    fills = laboratory_fills(shape)
    liquid = LaboratoryLiquid(
        fills={
            key: fills[key] for key in (LaboratoryVessel.CLEAR, LaboratoryVessel.AMBER)
        },
        shape=shape,
    )
    liquid.reset(poses)
    return LaboratoryDispenser(bench.dispenser, liquid, bench.stopper)


def dispense(key=LaboratoryVessel.CLEAR, volume=DOSE) -> DispenserRequest:
    """
    :param key: The receiver.
    :param volume: The dose.
    :return: A request to dispense amber reagent.
    """
    return DispenserRequest(
        action=DispenserAction.DISPENSE,
        key=key,
        channel=ReagentChannel.AMBER,
        volume=volume,
    )


def run(dispenser, poses, seconds: float) -> None:
    """
    :param dispenser: The station.
    :param poses: The vessels' poses.
    :param seconds: How long to let it run.
    """
    for _ in range(round(seconds / STEP)):
        dispenser.advance(STEP, poses, frozenset())


def test_a_dose_flows_at_the_pump_rate_until_complete(dispenser, poses):
    dispenser.operate(dispense(), poses, frozenset())
    run(dispenser, poses, DOSE / DispenserParameters().flow_rate / 2)
    assert dispenser.delivered == pytest.approx(DOSE / 2)
    run(dispenser, poses, DOSE / DispenserParameters().flow_rate)
    assert dispenser.state is DispenserState.COMPLETE
    assert dispenser.liquid.vessels[LaboratoryVessel.CLEAR].volume == pytest.approx(
        DOSE
    )
    assert dispenser.reservoirs[ReagentChannel.AMBER] == pytest.approx(
        DispenserParameters().reservoir - DOSE
    )
    assert dispenser.liquid.total() == pytest.approx(dispenser.liquid.supplied)


def test_a_receiver_moved_away_blocks_the_dose_and_resumes(dispenser, poses):
    dispenser.operate(dispense(), poses, frozenset())
    run(dispenser, poses, 0.2)
    moved = dict(poses)
    moved[LaboratoryVessel.CLEAR] = poses[LaboratoryVessel.AMBER]
    dispenser.advance(STEP, moved, frozenset())
    assert dispenser.state is DispenserState.BLOCKED
    assert dispenser.blocked_by is Refusal.RECEIVER_MISPLACED
    delivered = dispenser.delivered
    dispenser.operate(
        DispenserRequest(action=DispenserAction.RESUME), poses, frozenset()
    )
    run(dispenser, poses, DOSE)
    assert dispenser.state is DispenserState.COMPLETE
    assert dispenser.delivered == pytest.approx(DOSE) and delivered < DOSE


@pytest.mark.parametrize(
    "change, refusal",
    [
        ("elsewhere", Refusal.RECEIVER_MISPLACED),
        ("tilted", Refusal.RECEIVER_TILTED),
        ("stoppered", Refusal.STOPPER_IN_PLACE),
        ("clamped", Refusal.RECEIVER_CLAMPED),
    ],
)
def test_a_receiver_that_cannot_take_the_dose_is_refused(
    dispenser, poses, bench, change, refusal
):
    clamped = frozenset()
    station = poses[LaboratoryVessel.CLEAR]
    if change == "elsewhere":
        poses[LaboratoryVessel.CLEAR] = poses[LaboratoryVessel.AMBER]
    elif change == "tilted":
        tilt = np.array(
            [[1, 0, 0], [0, np.cos(0.3), -np.sin(0.3)], [0, np.sin(0.3), np.cos(0.3)]]
        )
        poses[LaboratoryVessel.CLEAR] = RigidPose(
            position=station.position, rotation=tilt
        )
    elif change == "stoppered":
        seat = dispenser.liquid.shape.rim - bench.stopper.insertion_depth
        poses[bench.stopper.key] = RigidPose(
            position=station.position + [0, 0, seat], rotation=np.eye(3)
        )
    else:
        clamped = frozenset({LaboratoryVessel.CLEAR})
    with pytest.raises(OperationRefused) as refused:
        dispenser.operate(dispense(), poses, clamped)
    assert refused.value.refusal is refusal


def test_a_dose_beyond_the_receiver_room_is_refused(dispenser, poses):
    shape = dispenser.liquid.shape
    dispenser.liquid.fill(LaboratoryVessel.CLEAR, shape.capacity - DOSE / 2)
    with pytest.raises(OperationRefused) as refused:
        dispenser.operate(dispense(), poses, frozenset())
    assert refused.value.refusal is Refusal.RECEIVER_FULL


def test_an_empty_reservoir_refuses_and_refills(dispenser, poses):
    dispenser.reservoirs[ReagentChannel.AMBER] = DOSE / 2
    with pytest.raises(OperationRefused):
        dispenser.operate(dispense(), poses, frozenset())
    refill = DispenserRequest(
        action=DispenserAction.REFILL, channel=ReagentChannel.AMBER
    )
    dispenser.operate(refill, poses, frozenset())
    assert dispenser.reservoirs[ReagentChannel.AMBER] == DispenserParameters().reservoir


def test_a_running_dose_must_stop_before_anything_else(dispenser, poses):
    dispenser.operate(dispense(), poses, frozenset())
    assert dispenser.receiving(LaboratoryVessel.CLEAR)
    with pytest.raises(OperationRefused) as refused:
        dispenser.operate(dispense(), poses, frozenset())
    assert refused.value.refusal is Refusal.DOSE_RUNNING
    dispenser.operate(DispenserRequest(action=DispenserAction.STOP), poses, frozenset())
    assert dispenser.state is DispenserState.IDLE


def test_nothing_resumes_without_an_unfinished_dose(dispenser, poses):
    with pytest.raises(OperationRefused) as refused:
        dispenser.operate(
            DispenserRequest(action=DispenserAction.RESUME), poses, frozenset()
        )
    assert refused.value.refusal is Refusal.NOTHING_TO_RESUME


def test_a_dose_outside_the_limits_is_refused(dispenser, poses):
    with pytest.raises(ValueOutOfRange):
        dispenser.operate(
            dispense(volume=DispenserParameters().maximum * 2), poses, frozenset()
        )


def test_an_unknown_channel_or_vessel_is_refused(dispenser, poses):
    unknown_channel = DispenserRequest(
        action=DispenserAction.DISPENSE, key=LaboratoryVessel.CLEAR, channel="blue"
    )
    with pytest.raises(UnknownObject):
        dispenser.operate(unknown_channel, poses, frozenset())
    with pytest.raises(OperationRefused) as refused:
        dispenser.operate(dispense(key="beaker"), poses, frozenset())
    assert refused.value.refusal is Refusal.RECEIVER_UNKNOWN


def test_the_status_and_limits_name_the_reagents(dispenser, poses, bench):
    dispenser.operate(dispense(), poses, frozenset())
    status = dispenser.status()
    assert status.key == LaboratoryVessel.CLEAR and status.requested == DOSE
    assert [level.identifier for level in status.reservoirs] == [
        channel.identifier for channel in bench.dispenser.channels
    ]
    assert [reagent.identifier for reagent in dispenser.limits().reagents] == [
        channel.identifier for channel in bench.dispenser.channels
    ]


def test_reset_refills_and_forgets_the_dose(dispenser, poses):
    dispenser.operate(dispense(), poses, frozenset())
    run(dispenser, poses, 0.2)
    dispenser.reset()
    assert dispenser.state is DispenserState.IDLE and dispenser.key is None
    assert set(dispenser.reservoirs.values()) == {DispenserParameters().reservoir}
