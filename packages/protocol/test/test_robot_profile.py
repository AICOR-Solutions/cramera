"""
The robot profile a deployment configures the plan builder with.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import UnsupportedProtocolVersion
from cramera_protocol.plan_builder import RunMode
from cramera_protocol.robot_profile import (
    PROFILE_FORMAT_VERSION,
    ExecutorKind,
    RobotProfile,
    RobotProfileKey,
)
from cramera_protocol.version import ProtocolVersion

# %% reading


@pytest.fixture
def profile_file() -> Path:
    """
    :return: The test dataset's profile of Tracy.
    """
    return Path(__file__).parent / "dataset" / "robot_profiles" / "tracy.json"


def test_a_profile_file_names_the_robot_its_label_and_environment(profile_file):
    profile = RobotProfile.from_file(profile_file)
    assert profile == RobotProfile(
        robot="tracy", label="Tracy", environment="tracy_lab"
    )


def test_a_profile_without_environment_stands_on_the_empty_floor():
    profile = RobotProfile.from_json(
        {RobotProfileKey.ROBOT: "tracy", RobotProfileKey.LABEL: "Tracy"}
    )
    assert profile.environment is None
    assert profile.format_version == PROFILE_FORMAT_VERSION


def test_a_profile_round_trips(profile_file):
    profile = RobotProfile.from_file(profile_file)
    assert RobotProfile.from_json(profile.to_json()) == profile


def test_a_profile_of_a_newer_major_version_is_refused():
    newer = ProtocolVersion(major=PROFILE_FORMAT_VERSION.major + 1, minor=0)
    with pytest.raises(UnsupportedProtocolVersion):
        RobotProfile.from_json(
            {
                RobotProfileKey.FORMAT_VERSION: newer.to_json(),
                RobotProfileKey.ROBOT: "tracy",
                RobotProfileKey.LABEL: "Tracy",
            }
        )


def test_the_browser_reads_the_profile_keys():
    assert RobotProfileKey in BROWSER_ENUMERATIONS


# %% executors


def test_a_profile_naming_no_executors_runs_every_mode_on_its_default():
    profile = RobotProfile(robot="tracy", label="Tracy")
    assert (
        profile.executor_for(RunMode.SIMULATE, ExecutorKind.PHYSICS)
        is ExecutorKind.PHYSICS
    )


def test_a_profile_runs_the_modes_it_names_on_their_executors_and_no_others():
    profile = RobotProfile.from_json(
        {
            RobotProfileKey.ROBOT: "tracy",
            RobotProfileKey.LABEL: "Tracy",
            RobotProfileKey.EXECUTORS: {RunMode.PERFORM: ExecutorKind.PHYSICS},
        }
    )
    assert (
        profile.executor_for(RunMode.PERFORM, ExecutorKind.KINEMATIC)
        is ExecutorKind.PHYSICS
    )
    assert profile.executor_for(RunMode.SIMULATE, ExecutorKind.PHYSICS) is None
    assert RobotProfile.from_json(profile.to_json()) == profile


def test_the_browser_reads_the_executor_kinds():
    assert ExecutorKind in BROWSER_ENUMERATIONS
