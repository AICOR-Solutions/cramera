"""
The documents of the cable lab: the cable configuration, the gripper commands and the
measured state.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.cable_lab import (
    MAXIMUM_CABLE_LENGTH,
    CableConfiguration,
    CableConfigurationKey,
    CableLabKey,
    CableLabRoute,
    CableLabState,
    GraspState,
    GripperAction,
    GripperCommand,
    GripperCommandKey,
    InvalidCableConfiguration,
    InvalidGripperCommand,
    SimulationLifecycle,
)
from cramera_protocol.exceptions import UnexpectedDocumentField

# %% configuration


def test_an_empty_configuration_asks_for_the_default_cable(read_json):
    configuration = CableConfiguration.from_json(
        read_json("cable_lab/default_configuration.json")
    )
    assert configuration == CableConfiguration()
    assert configuration.anchored is True


def test_a_configuration_reads_every_setting(read_json):
    data = read_json("cable_lab/loose_configuration.json")
    configuration = CableConfiguration.from_json(data)
    assert configuration.segment_count == data[CableConfigurationKey.SEGMENT_COUNT]
    assert configuration.anchored is data[CableConfigurationKey.ANCHORED]
    assert configuration.friction.sliding == data[CableConfigurationKey.FRICTION][0]
    assert configuration.solver_impedance.power == (
        data[CableConfigurationKey.SOLVER_IMPEDANCE][-1]
    )
    assert configuration.to_json() == data


def test_the_length_is_the_elements_together(read_json):
    data = read_json("cable_lab/loose_configuration.json")
    configuration = CableConfiguration.from_json(data)
    assert configuration.length() == pytest.approx(
        data[CableConfigurationKey.SEGMENT_COUNT]
        * data[CableConfigurationKey.SEGMENT_LENGTH]
    )


@pytest.mark.parametrize(
    "file_name, key",
    [
        ("configuration_with_one_element.json", CableConfigurationKey.SEGMENT_COUNT),
        (
            "configuration_longer_than_the_lab.json",
            CableConfigurationKey.SEGMENT_LENGTH,
        ),
        ("configuration_with_negative_radius.json", CableConfigurationKey.RADIUS),
        ("configuration_with_bright_color.json", CableConfigurationKey.COLOR),
        ("configuration_with_infinite_bend.json", CableConfigurationKey.BEND),
        (
            "configuration_with_unsupported_contact_dimension.json",
            CableConfigurationKey.CONTACT_DIMENSION,
        ),
        (
            "configuration_with_inverted_impedance.json",
            CableConfigurationKey.SOLVER_IMPEDANCE,
        ),
        ("configuration_with_negative_friction.json", CableConfigurationKey.FRICTION),
        (
            "configuration_with_infinite_offset.json",
            CableConfigurationKey.ANCHOR_OFFSET,
        ),
        (
            "configuration_with_zero_time_constant.json",
            CableConfigurationKey.SOLVER_REFERENCE,
        ),
    ],
)
def test_a_cable_the_lab_cannot_build_is_refused_by_its_key(read_json, file_name, key):
    with pytest.raises(InvalidCableConfiguration) as refused:
        CableConfiguration.from_json(read_json(f"cable_lab/{file_name}"))
    assert refused.value.key is key
    assert key.value in refused.value.message()


def test_a_cable_longer_than_the_lab_names_the_limit(read_json):
    with pytest.raises(InvalidCableConfiguration) as refused:
        CableConfiguration.from_json(
            read_json("cable_lab/configuration_longer_than_the_lab.json")
        )
    assert str(MAXIMUM_CABLE_LENGTH) in refused.value.reason


def test_the_keys_of_earlier_versions_are_refused(read_json):
    with pytest.raises(UnexpectedDocumentField):
        CableConfiguration.from_json(
            read_json("cable_lab/configuration_with_snake_case_keys.json")
        )


# %% commands


def test_a_pinch_takes_no_position(read_json):
    command = GripperCommand.from_json(read_json("cable_lab/pinch.json"))
    assert command.action is GripperAction.PINCH
    assert command.position is None


def test_a_move_names_its_target(read_json):
    data = read_json("cable_lab/move.json")
    command = GripperCommand.from_json(data)
    assert command.position.to_json() == data[GripperCommandKey.POSITION]


@pytest.mark.parametrize(
    "file_name",
    ["move_without_position.json", "move_to_infinity.json", "lift_with_position.json"],
)
def test_a_command_whose_position_does_not_fit_is_refused(read_json, file_name):
    data = read_json(f"cable_lab/{file_name}")
    with pytest.raises(InvalidGripperCommand) as refused:
        GripperCommand.from_json(data)
    assert refused.value.action.value == data[GripperCommandKey.ACTION]
    assert refused.value.message()


# %% state


def test_a_running_state_reads_geometry_forces_and_grasp(read_json):
    data = read_json("cable_lab/running_state.json")
    state = CableLabState.from_json(data)
    assert state.lifecycle is SimulationLifecycle.RUNNING
    assert len(state.segments) == len(data[CableLabKey.SEGMENTS])
    assert state.gripper.pads[0].size.to_json() == (
        data[CableLabKey.GRIPPER][CableLabKey.PADS][0][CableLabKey.SIZE]
    )
    assert state.grasp.state is GraspState.OPEN
    assert state.is_commandable()
    assert CableLabState.from_json(state.to_json()) == state


def test_an_idle_lab_without_a_cable_takes_no_commands(read_json):
    state = CableLabState.from_json(read_json("cable_lab/idle_state.json"))
    assert state.configuration is None
    assert not state.is_commandable()


# %% names


def test_the_browser_reads_the_cable_lab_names():
    for enumeration in (
        CableLabRoute,
        CableConfigurationKey,
        GripperAction,
        GripperCommandKey,
        SimulationLifecycle,
        GraspState,
        CableLabKey,
    ):
        assert enumeration in BROWSER_ENUMERATIONS
