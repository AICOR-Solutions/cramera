"""
The reduced liquid model: volumes, free surfaces, pouring, catching and spilling.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from cramera_laboratory.exceptions import NonFiniteValue, UnknownObject, ValueOutOfRange
from cramera_laboratory.geometry import RigidPose
from cramera_laboratory.liquid import (
    AMBER_LIQUID,
    CLEAR_LIQUID,
    LaboratoryLiquid,
    LaboratoryVessel,
    LiquidParameters,
    VesselShape,
    laboratory_fills,
)

VOLUME_TOLERANCE = 1e-6
"""
How close two volumes in millilitres must be in the tests.
"""

SOURCE_POSITION = np.array([0.0, 0.0, 1.0])
"""
Where the pouring vessel stands, above the worktop.
"""

POUR_ANGLE = 2.2
"""
How far the pouring vessel is tipped, in radians: past horizontal.
"""

POUR_SECONDS = 1.0
"""
How long a test pours, in seconds.
"""

HIGH_SOURCE = np.array([0.0, 0.0, 1.5])
"""
Where a pouring vessel is held high above the worktop.
"""

STREAM_RECEIVER = np.array([0.0, -0.0875, 1.12])
"""
Where a vessel stands so the stream of the vessel tipped at :data:`HIGH_SOURCE` falls
through its opening, found by following the stream.
"""

STEP = 0.02
"""
The liquid step of the tests, in seconds.
"""


def upright(position) -> RigidPose:
    """
    :param position: A position.
    :return: An upright pose there.
    """
    return RigidPose(position=np.array(position, dtype=float), rotation=np.eye(3))


def tipped(position, angle: float) -> RigidPose:
    """
    :param position: A position.
    :param angle: How far the vessel is turned about x, in radians.
    :return: The tipped pose.
    """
    return RigidPose(
        position=np.array(position, dtype=float),
        rotation=Rotation.from_rotvec([angle, 0.0, 0.0]).as_matrix(),
    )


@pytest.fixture
def shape() -> VesselShape:
    """
    :return: The laboratory's vessel interior.
    """
    return VesselShape()


@pytest.fixture
def liquid(shape) -> LaboratoryLiquid:
    """
    :return: The amber and clear vessels, upright side by side over the worktop.
    """
    fills = laboratory_fills(shape)
    model = LaboratoryLiquid(
        fills={
            key: fills[key] for key in (LaboratoryVessel.AMBER, LaboratoryVessel.CLEAR)
        },
        shape=shape,
    )
    model.reset(
        {
            LaboratoryVessel.AMBER: upright(SOURCE_POSITION),
            LaboratoryVessel.CLEAR: upright(SOURCE_POSITION + [0.3, 0.0, 0.0]),
        }
    )
    return model


# %% shape


def test_the_full_vessel_holds_its_capacity(shape):
    assert shape.upright_volume(shape.rim) == pytest.approx(shape.capacity)
    assert shape.upright_volume(shape.bottom) == 0


def test_a_level_surface_holds_its_upright_volume(shape):
    height = 0.08
    volume = shape.upright_volume(height)
    assert shape.surface_offset(np.array([0.0, 0.0, 1.0]), volume) == pytest.approx(
        height, abs=1e-6
    )


@pytest.mark.parametrize("angle", [0.3, 1.0, 1.5])
def test_a_tilted_surface_keeps_its_volume(shape, angle):
    normal = np.array([math.sin(angle), 0.0, math.cos(angle)])
    volume = 4.0
    offset = shape.surface_offset(normal, volume)
    assert shape.volume_below(normal, offset) == pytest.approx(volume, rel=1e-3)


def test_the_lowest_lip_lies_opposite_the_surface_tilt(shape):
    lip = shape.lowest_lip(np.array([0.6, 0.0, 0.8]))
    assert lip[0] == pytest.approx(-shape.radius) and lip[2] == shape.rim


def test_the_interior_document_states_the_capacity(shape):
    assert shape.document().capacity == shape.capacity


# %% filling


def test_reset_restores_the_authored_fills(liquid, shape):
    assert liquid.vessels[LaboratoryVessel.CLEAR].volume == 0
    assert liquid.vessels[LaboratoryVessel.AMBER].volume == pytest.approx(
        shape.upright_volume(laboratory_fills(shape)[LaboratoryVessel.AMBER].level)
    )
    assert liquid.supplied == pytest.approx(liquid.total())


def test_filling_accounts_for_the_liquid_supplied(liquid):
    liquid.fill(LaboratoryVessel.CLEAR, 5.0)
    assert liquid.vessels[LaboratoryVessel.CLEAR].volume == 5.0
    assert liquid.supplied == pytest.approx(liquid.total())


@pytest.mark.parametrize(
    "volume, error",
    [(-1.0, ValueOutOfRange), (1e3, ValueOutOfRange), (math.nan, NonFiniteValue)],
)
def test_an_impossible_fill_is_refused(liquid, volume, error):
    with pytest.raises(error):
        liquid.fill(LaboratoryVessel.CLEAR, volume)


def test_filling_an_unknown_vessel_is_refused(liquid):
    with pytest.raises(UnknownObject):
        liquid.fill("beaker", 1.0)


def test_supplied_liquid_mixes_by_volume(liquid):
    liquid.fill(LaboratoryVessel.CLEAR, 1.0)
    accepted = liquid.supply(
        LaboratoryVessel.CLEAR, 1.0, np.array(AMBER_LIQUID.to_json())
    )
    color = liquid.vessels[LaboratoryVessel.CLEAR].color
    expected = (np.array(CLEAR_LIQUID.to_json()) + np.array(AMBER_LIQUID.to_json())) / 2
    assert accepted == 1.0
    np.testing.assert_allclose(color, expected)


def test_a_full_vessel_takes_only_what_fits(liquid, shape):
    liquid.fill(LaboratoryVessel.CLEAR, shape.capacity - 0.5)
    assert liquid.supply(
        LaboratoryVessel.CLEAR, 2.0, np.array(AMBER_LIQUID.to_json())
    ) == pytest.approx(0.5)


# %% motion


def test_a_resting_vessel_keeps_its_liquid(liquid):
    before = liquid.vessels[LaboratoryVessel.AMBER].volume
    poses = {key: content.pose for key, content in liquid.vessels.items()}
    for _ in range(50):
        liquid.step(STEP, poses)
    assert liquid.vessels[LaboratoryVessel.AMBER].volume == pytest.approx(before)
    assert liquid.portions == [] and liquid.pools == []


def test_a_tipped_vessel_pours_onto_the_worktop_and_keeps_every_millilitre(liquid):
    before = liquid.vessels[LaboratoryVessel.AMBER].volume
    poses = {
        LaboratoryVessel.AMBER: tipped(SOURCE_POSITION, POUR_ANGLE),
        LaboratoryVessel.CLEAR: liquid.vessels[LaboratoryVessel.CLEAR].pose,
    }
    for _ in range(int(POUR_SECONDS / STEP)):
        liquid.step(STEP, poses)
    assert liquid.vessels[LaboratoryVessel.AMBER].volume < before
    assert liquid.pools
    assert liquid.pools[0].position[2] == pytest.approx(
        LiquidParameters().worktop_height + LiquidParameters().puddle_lift
    )
    assert liquid.total() == pytest.approx(liquid.supplied, abs=VOLUME_TOLERANCE)


def test_a_vessel_under_the_stream_catches_it(liquid):
    source = tipped(HIGH_SOURCE, POUR_ANGLE)
    receiver = upright(STREAM_RECEIVER)
    poses = {LaboratoryVessel.AMBER: source, LaboratoryVessel.CLEAR: receiver}
    for _ in range(int(POUR_SECONDS / STEP)):
        liquid.step(STEP, poses)
    assert liquid.vessels[LaboratoryVessel.CLEAR].volume > 0
    assert liquid.total() == pytest.approx(liquid.supplied, abs=VOLUME_TOLERANCE)


def test_an_accelerating_vessel_tilts_its_surface(liquid):
    content = liquid.vessels[LaboratoryVessel.AMBER]
    level = content.normal.copy()
    moved = upright(SOURCE_POSITION + [0.02, 0.0, 0.0])
    liquid.step(
        STEP,
        {
            LaboratoryVessel.AMBER: moved,
            LaboratoryVessel.CLEAR: liquid.vessels[LaboratoryVessel.CLEAR].pose,
        },
    )
    assert not np.allclose(content.normal, level)


def test_a_too_long_step_is_refused(liquid):
    poses = {key: content.pose for key, content in liquid.vessels.items()}
    with pytest.raises(ValueOutOfRange):
        liquid.step(LiquidParameters().maximum_duration * 2, poses)


def test_the_state_lists_vessels_droplets_and_puddles(liquid):
    poses = {
        LaboratoryVessel.AMBER: tipped(SOURCE_POSITION, POUR_ANGLE),
        LaboratoryVessel.CLEAR: liquid.vessels[LaboratoryVessel.CLEAR].pose,
    }
    for _ in range(10):
        liquid.step(STEP, poses)
    state = liquid.state()
    assert set(state.vessels) == set(liquid.vessels)
    assert len(state.droplets) == len(liquid.portions)
    assert state.supplied == liquid.supplied
