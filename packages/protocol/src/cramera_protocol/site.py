"""
Sites: where robots work.

A site file names the environment bundle its robots stand in, each robot by its registry
identifier with its robot profile, the pose it stands at and the facts its commissioning
recorded, and the named zones of the site's table.

The format is open; the sites themselves belong to whoever runs them. A site file
declares its format version under ``formatVersion``. A reader reads every minor version
of its own major version and keeps the keys it does not know, so writing a file back
loses nothing a later minor version added.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, List, Mapping, Optional, Self

from cramera_protocol.document import JsonDocument, document_field, extension_field
from cramera_protocol.exceptions import (
    DuplicateSiteRobot,
    DuplicateSiteZone,
    InvalidSiteRobotPose,
    MissingSiteFormatVersion,
    UnsetSiteVariable,
)
from cramera_protocol.geometry import Pose
from cramera_protocol.robot_profile import SafetyLimits, Zone
from cramera_protocol.version import ProtocolVersion

SITE_FORMAT = ProtocolVersion(major=1, minor=1)
"""
The site format version this package reads and writes.
"""

# %% names


class SiteFile(StrEnum):
    """
    The files of a site.
    """

    SITE = "site.json"
    """
    The site's description, in a directory of its own.
    """


class SiteKey(StrEnum):
    """
    The keys of a site file.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The site format's version, ``major.minor``.
    """

    IDENTIFIER = "id"
    """
    The site's stable identity.
    """

    LABEL = "label"
    """
    The site's name for people.
    """

    DESCRIPTION = "description"
    """
    One or two plain sentences telling people what the site is; since version 1.1.
    """

    THUMBNAIL = "thumbnail"
    """
    A square picture of the site, relative to the site file; since version 1.1.
    """

    ENVIRONMENT = "environment"
    """
    The environment bundle the robots stand in.
    """

    ROBOTS = "robots"
    """
    The robots working at the site.
    """

    ZONES = "zones"
    """
    The named zones of the site's table.
    """


class EnvironmentReferenceKey(StrEnum):
    """
    The keys of a site's environment.
    """

    BUNDLE = "bundle"
    """
    The environment bundle's name, as the viewer's scene directories list it.
    """

    SCENES = "scenes"
    """
    The scene directory holding the bundle, relative to the site file. ``${NAME}``
    stands for the environment variable ``NAME``, so a site names data kept outside
    every repository, such as a customer's scanned building, by where each machine
    keeps it.
    """


class SiteRobotKey(StrEnum):
    """
    The keys of a robot of a site.
    """

    IDENTIFIER = "id"
    """
    The robot's registry identifier.
    """

    PROFILE = "profile"
    """
    The robot profile's file, relative to the site file.
    """

    POSE = "pose"
    """
    Where the robot stands.
    """

    COMMISSIONING = "commissioning"
    """
    What the robot's commissioning at the site recorded.
    """


class CommissioningKey(StrEnum):
    """
    The keys of a robot's commissioning facts.
    """

    SAFETY = "safety"
    """
    The safety limits the robot's runs at the site are held to.
    """


SITE_VARIABLE = re.compile(r"\$\{(\w+)\}")
"""
How a site path names an environment variable: ``${NAME}``.
"""


def site_path(
    site_file: Path, path: str, environment: Optional[Mapping[str, str]] = None
) -> Path:
    """
    :param site_file: The site file writing the path.
    :param path: A path as the site writes it, relative to the site file; ``${NAME}``
        stands for the environment variable ``NAME``.
    :param environment: The environment variables, the process's own by default.
    :return: The path with its variables expanded, relative to the site file.
    :raises UnsetSiteVariable: When the path names a variable that is not set.
    """
    variables = os.environ if environment is None else environment
    for variable in SITE_VARIABLE.findall(path):
        if variable not in variables:
            raise UnsetSiteVariable(path=path, variable=variable)
    expanded = SITE_VARIABLE.sub(lambda found: variables[found.group(1)], path)
    return site_file.parent / Path(expanded).expanduser()


# %% parts


@dataclass(kw_only=True)
class EnvironmentReference(JsonDocument):
    """
    The environment bundle a site's robots stand in.
    """

    bundle: str = document_field(EnvironmentReferenceKey.BUNDLE)
    """
    The bundle's name, as the viewer's scene directories list it.
    """

    scenes: Optional[str] = document_field(EnvironmentReferenceKey.SCENES, default=None)
    """
    The scene directory holding the bundle, relative to the site file; None when the
    viewer's own scene directories hold it.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The keys this reader does not know, kept as written.
    """

    def scene_directory(
        self, site_file: Path, environment: Optional[Mapping[str, str]] = None
    ) -> Optional[Path]:
        """
        :param site_file: The site file naming this environment.
        :param environment: The environment variables a ``${NAME}`` in the path stands
            for, the process's own by default.
        :return: The scene directory holding the bundle, or None when the viewer's own
            scene directories hold it.
        :raises UnsetSiteVariable: When the path names a variable that is not set.
        """
        if self.scenes is None:
            return None
        return site_path(site_file, self.scenes, environment)


@dataclass(kw_only=True)
class Commissioning(JsonDocument):
    """
    What a robot's commissioning at a site recorded, as data: the safety limits its runs
    are held to and any further facts, kept as written.
    """

    safety: Optional[SafetyLimits] = document_field(
        CommissioningKey.SAFETY, default=None
    )
    """
    The safety limits the robot's runs are held to; None holds them to none.
    """

    facts: Dict[str, Any] = extension_field()
    """
    The further facts the commissioning recorded, by name.
    """


@dataclass(kw_only=True)
class SiteRobot(JsonDocument):
    """
    A robot working at a site.
    """

    identifier: str = document_field(SiteRobotKey.IDENTIFIER)
    """
    The robot's registry identifier, such as ``cram.tracy``.
    """

    pose: Pose = document_field(SiteRobotKey.POSE)
    """
    Where the robot stands, in the site's frame.
    """

    profile: Optional[str] = document_field(SiteRobotKey.PROFILE, default=None)
    """
    The robot profile's file, relative to the site file; None for a robot without one.
    """

    commissioning: Commissioning = document_field(
        SiteRobotKey.COMMISSIONING, default_factory=Commissioning
    )
    """
    What the robot's commissioning at the site recorded.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The keys this reader does not know, kept as written.
    """

    def quaternion_norm(self) -> float:
        """
        :return: The length of the quaternion of the robot's pose.
        """
        pose = self.pose
        return math.sqrt(pose.qx**2 + pose.qy**2 + pose.qz**2 + pose.qw**2)


# %% site


@dataclass(kw_only=True)
class Site(JsonDocument):
    """
    One site: its environment, its robots and where they stand, and its zones.
    """

    identifier: str = document_field(SiteKey.IDENTIFIER)
    """
    The site's stable identity.
    """

    label: str = document_field(SiteKey.LABEL)
    """
    The site's name for people.
    """

    description: Optional[str] = document_field(SiteKey.DESCRIPTION, default=None)
    """
    One or two plain sentences telling people what the site is, or None.
    """

    thumbnail: Optional[str] = document_field(SiteKey.THUMBNAIL, default=None)
    """
    A square picture of the site, relative to the site file, or None.
    """

    robots: List[SiteRobot] = document_field(SiteKey.ROBOTS, default_factory=list)
    """
    The robots working at the site, in order.
    """

    environment: Optional[EnvironmentReference] = document_field(
        SiteKey.ENVIRONMENT, default=None
    )
    """
    The environment bundle the robots stand in; None stands them on an empty floor, as
    when the robot's own description holds its table.
    """

    zones: List[Zone] = document_field(SiteKey.ZONES, default_factory=list)
    """
    The named zones of the site's table, in the frame of the site.
    """

    format_version: Optional[ProtocolVersion] = document_field(
        SiteKey.FORMAT_VERSION, default=None
    )
    """
    The format version the file declares; reading requires one.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    The top-level keys this reader does not know, kept as written.
    """

    def __post_init__(self) -> None:
        self.validate()

    def validate(self, quaternion_tolerance: float = 1e-3) -> None:
        """
        :param quaternion_tolerance: How far a robot pose's quaternion length may be
            from 1.
        :raises MissingSiteFormatVersion: When the site declares no format version.
        :raises UnsupportedProtocolVersion: When it is of another major version.
        :raises DuplicateSiteRobot: When it names a robot twice.
        :raises DuplicateSiteZone: When it names a zone twice.
        :raises InvalidSiteRobotPose: When a robot's quaternion is no unit quaternion.
        """
        if self.format_version is None:
            raise MissingSiteFormatVersion(self.identifier)
        self.format_version.require_readable_by(SITE_FORMAT)
        robots: set[str] = set()
        for robot in self.robots:
            if robot.identifier in robots:
                raise DuplicateSiteRobot(self.identifier, robot.identifier)
            robots.add(robot.identifier)
            norm = robot.quaternion_norm()
            if abs(norm - 1.0) > quaternion_tolerance:
                raise InvalidSiteRobotPose(self.identifier, robot.identifier, norm)
        zones: set[str] = set()
        for zone in self.zones:
            if zone.identifier in zones:
                raise DuplicateSiteZone(self.identifier, zone.identifier)
            zones.add(zone.identifier)

    def robot_named(self, identifier: str) -> Optional[SiteRobot]:
        """
        :param identifier: A robot's identifier as the site writes it.
        :return: The site's robot of that identifier, or None.
        """
        return next(
            (robot for robot in self.robots if robot.identifier == identifier), None
        )

    def thumbnail_file(
        self, site_file: Path, environment: Optional[Mapping[str, str]] = None
    ) -> Optional[Path]:
        """
        :param site_file: The site's file.
        :param environment: The environment variables a ``${NAME}`` in the path stands
            for, the process's own by default; a picture of private data lies with it.
        :return: The site's picture as the file names it, or None when it names none.
        :raises UnsetSiteVariable: When the path names a variable that is not set.
        """
        if self.thumbnail is None:
            return None
        return site_path(site_file, self.thumbnail, environment)

    @staticmethod
    def profile_file(site_file: Path, robot: SiteRobot) -> Optional[Path]:
        """
        :param site_file: The site's file.
        :param robot: One of its robots.
        :return: The robot's profile file, or None for a robot without one.
        """
        if robot.profile is None:
            return None
        return site_file.parent / robot.profile

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A ``site.json``.
        :return: The site.
        :raises SiteError: When the file is no valid site, see :meth:`validate`.
        :raises UnsupportedProtocolVersion: When it is of another major version.
        """
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
