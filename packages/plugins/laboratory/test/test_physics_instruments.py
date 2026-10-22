"""
The expanded laboratory's instruments in the contact simulation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cramera_laboratory.exceptions import (
    InvalidLaboratoryModel,
    UnknownInstrument,
)
from cramera_laboratory.physics.instruments import InstrumentModelPart
from cramera_laboratory.physics.simulation import LaboratoryPhysics
from cramera_laboratory.resources import LaboratoryResource
from cramera_protocol.laboratory.layout import InstrumentJointKind
from cramera_protocol.laboratory.physics import (
    InstrumentPose,
    InstrumentRequest,
)

INSPECTION_SECONDS = 4.0
"""
How long the tests let an instrument move, in seconds.
"""


@pytest.fixture(scope="module")
def expanded(shelf) -> LaboratoryPhysics:
    """
    :return: The expanded laboratory's simulation, shared by the module's tests.
    """
    return LaboratoryPhysics(shelf.laboratory(LaboratoryResource.EXPANDED))


def moving_instrument(expanded: LaboratoryPhysics):
    """
    :param expanded: The simulation.
    :return: The first instrument whose joints all move between distinct positions.
    """
    return next(
        instrument
        for instrument in expanded.instruments.collection.instruments
        if instrument.joints
        and all(joint.inspection != joint.rest for joint in instrument.joints)
    )


def test_an_instrument_moves_to_inspection_and_back(expanded):
    expanded.reset()
    instrument = moving_instrument(expanded)
    expanded.move_instrument(
        InstrumentRequest(
            instrument=instrument.identifier, pose=InstrumentPose.INSPECTION
        )
    )
    expanded.step(round(INSPECTION_SECONDS / expanded.timestep))
    assert expanded.instruments.arrived(instrument.identifier)
    joints = expanded.snapshot().joints
    for joint in instrument.joints:
        assert joints[joint.name] == pytest.approx(joint.inspection, abs=0.01)
    expanded.move_instrument(
        InstrumentRequest(instrument=instrument.identifier, pose=InstrumentPose.REST)
    )
    expanded.step(round(INSPECTION_SECONDS / expanded.timestep))
    assert expanded.instruments.arrived(instrument.identifier)


def test_an_unknown_instrument_is_refused(expanded):
    with pytest.raises(UnknownInstrument):
        expanded.move_instrument(
            InstrumentRequest(instrument="toaster", pose=InstrumentPose.REST)
        )


def test_the_expanded_bounds_come_from_the_collection(expanded):
    assert expanded.bounds() == expanded.instruments.collection.bounds


def test_a_rest_position_beyond_the_stops_is_refused(shelf):
    collection = shelf.laboratory(LaboratoryResource.EXPANDED).instruments()
    instrument = next(item for item in collection.instruments if item.joints)
    joint = next(
        joint
        for joint in instrument.joints
        if joint.kind is not InstrumentJointKind.CONTINUOUS
    )
    instrument.joints[instrument.joints.index(joint)] = replace(
        joint, rest=joint.upper + 1
    )
    with pytest.raises(InvalidLaboratoryModel):
        InstrumentModelPart(collection)
