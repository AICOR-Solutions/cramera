"""
A robot profile: how the plan builder is set up for one robot at one site, which robot
plans start with and the environment it stands in.

A deployment names its profile with :attr:`RobotProfileVariable.PROFILE`; without one
the plan builder offers every robot and action of the CRAM workspace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Optional, Self

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.version import ProtocolVersion

PROFILE_FORMAT_VERSION = ProtocolVersion(major=1, minor=0)
"""
The version profiles are written with.
"""


class RobotProfileVariable(StrEnum):
    """
    The environment variables a deployment configures the profile with.
    """

    PROFILE = "CRAMERA_ROBOT_PROFILE"
    """
    The path of the robot profile's JSON file.
    """


class RobotProfileKey(StrEnum):
    """
    The keys of a robot profile.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The format version the profile is written in.
    """

    ROBOT = "robot"
    """
    The robot model plans start with.
    """

    LABEL = "label"
    """
    The name the site gives the robot.
    """

    ENVIRONMENT = "environment"
    """
    The environment bundle the robot stands in.
    """


@dataclass(kw_only=True)
class RobotProfile(JsonDocument):
    """
    The plan builder's setup for one robot.
    """

    robot: str = document_field(RobotProfileKey.ROBOT)
    """
    The identifier of the robot model a new plan starts with, as the catalog lists it.
    """

    label: str = document_field(RobotProfileKey.LABEL)
    """
    The name shown for the robot.
    """

    environment: Optional[str] = document_field(
        RobotProfileKey.ENVIRONMENT, default=None
    )
    """
    The environment bundle a new plan is set in, or None for an empty floor.
    """

    format_version: ProtocolVersion = document_field(
        RobotProfileKey.FORMAT_VERSION, default=PROFILE_FORMAT_VERSION
    )
    """
    The format version the profile is written in.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(PROFILE_FORMAT_VERSION)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A profile's JSON file.
        :return: The profile it holds.
        """
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
