"""
Checking commands before the simulation acts on them.
"""

from __future__ import annotations

import math

import pytest

from cramera_laboratory.commands import CommandCheck
from cramera_laboratory.exceptions import (
    AmbiguousManualRequest,
    MissingRequestField,
    NonFiniteValue,
    RequestField,
    UnexpectedRequestField,
    ZeroQuaternion,
)
from cramera_protocol.geometry import Vector3
from cramera_protocol.laboratory.knowledge import ManualEdition
from cramera_protocol.laboratory.layout import Quaternion
from cramera_protocol.laboratory.physics import (
    CentrifugeAction,
    CentrifugeRequest,
    DispenserAction,
    DispenserRequest,
    LiquidRequest,
    ManualRequest,
    TargetRequest,
)

from .test_knowledge import manual_text

KEY = "tube_clear"
"""
The vessel the requests name.
"""


def test_a_target_with_a_finite_position_and_orientation_passes():
    CommandCheck().target(
        TargetRequest(
            key=KEY, position=Vector3(0, 0, 1), orientation=Quaternion(0, 0, 0, 1)
        )
    )


def test_a_target_with_a_non_finite_coordinate_is_refused():
    with pytest.raises(NonFiniteValue):
        CommandCheck().target(TargetRequest(key=KEY, position=Vector3(math.nan, 0, 1)))


def test_a_zero_orientation_is_refused():
    with pytest.raises(ZeroQuaternion):
        CommandCheck().target(
            TargetRequest(
                key=KEY, position=Vector3(0, 0, 1), orientation=Quaternion(0, 0, 0, 0)
            )
        )


def test_an_infinite_liquid_volume_is_refused():
    with pytest.raises(NonFiniteValue):
        CommandCheck().liquid(LiquidRequest(key=KEY, volume=math.inf))


def test_securing_needs_a_slot_and_a_vessel():
    with pytest.raises(MissingRequestField) as missing:
        CommandCheck().centrifuge(
            CentrifugeRequest(action=CentrifugeAction.SECURE, slot="C1")
        )
    assert missing.value.field_name is RequestField.KEY


def test_opening_takes_no_speed():
    with pytest.raises(UnexpectedRequestField) as unexpected:
        CommandCheck().centrifuge(
            CentrifugeRequest(action=CentrifugeAction.OPEN, speed=100.0)
        )
    assert unexpected.value.field_name is RequestField.SPEED


def test_starting_may_give_a_speed_and_a_duration():
    CommandCheck().centrifuge(
        CentrifugeRequest(action=CentrifugeAction.START, speed=100.0, duration=10.0)
    )


def test_a_non_finite_cycle_is_refused():
    with pytest.raises(NonFiniteValue):
        CommandCheck().centrifuge(
            CentrifugeRequest(action=CentrifugeAction.START, duration=math.nan)
        )


def test_dispensing_needs_a_vessel_and_a_channel_and_stopping_takes_neither():
    with pytest.raises(MissingRequestField):
        CommandCheck().dispenser(
            DispenserRequest(action=DispenserAction.DISPENSE, key=KEY)
        )
    with pytest.raises(UnexpectedRequestField):
        CommandCheck().dispenser(DispenserRequest(action=DispenserAction.STOP, key=KEY))


def test_a_manual_request_names_one_source():
    with pytest.raises(AmbiguousManualRequest):
        CommandCheck.manual(ManualRequest())
    with pytest.raises(AmbiguousManualRequest):
        CommandCheck.manual(ManualRequest(edition=ManualEdition.FIRST, document="# x"))


def test_a_manual_request_reads_an_edition_or_a_text():
    shipped = CommandCheck.manual(ManualRequest(edition=ManualEdition.SECOND))
    written = CommandCheck.manual(ManualRequest(document=manual_text("german.md")))
    assert shipped.minimum_samples == written.minimum_samples == 4
