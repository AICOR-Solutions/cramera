"""
Site files: the environment a site's robots stand in, where each stands, its zones and
the facts its commissioning recorded, read by one reader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cramera_protocol.exceptions import (
    DuplicateSiteRobot,
    DuplicateSiteZone,
    InvalidSiteRobotPose,
    MissingSiteFormatVersion,
    UnsetSiteVariable,
    UnsupportedProtocolVersion,
)
from cramera_protocol.geometry import Pose
from cramera_protocol.site import SITE_FORMAT, Site, SiteKey
from cramera_protocol.version import ProtocolVersion


def site_data(**changes) -> dict:
    data = {
        "formatVersion": "1.0",
        "id": "walker_s2_table",
        "label": "Walker S2 at its table",
        "environment": {"bundle": "walker_s2_table", "scenes": "environments"},
        "robots": [
            {
                "id": "example.walker_s2",
                "profile": "robots/walker_s2/profile.json",
                "pose": [0, 0, 0.9025, 0, 0, 0, 1],
                "commissioning": {
                    "safety": {"workspaces": [], "maximumToolVelocity": 0.5}
                },
            }
        ],
        "zones": [
            {
                "id": "center",
                "label": "Center",
                "area": {"minX": 0.52, "maxX": 0.6, "minY": -0.06, "maxY": 0.06},
            }
        ],
    }
    data.update(changes)
    return data


def write_site(directory: Path, data: dict) -> Path:
    path = directory / "site.json"
    path.write_text(json.dumps(data), "utf-8")
    return path


def test_a_site_names_its_environment_robots_poses_zones_and_commissioning(tmp_path):
    site = Site.from_file(write_site(tmp_path, site_data()))
    robot = site.robots[0]
    assert site.identifier == "walker_s2_table"
    assert site.environment.bundle == "walker_s2_table"
    assert robot.identifier == "example.walker_s2"
    assert robot.pose == Pose(0, 0, 0.9025, 0, 0, 0, 1)
    assert robot.commissioning.safety.maximum_tool_velocity == 0.5
    assert [zone.identifier for zone in site.zones] == ["center"]


def test_paths_of_a_site_are_read_relative_to_its_file(tmp_path):
    path = write_site(tmp_path, site_data())
    site = Site.from_file(path)
    assert site.profile_file(path, site.robots[0]) == (
        tmp_path / "robots" / "walker_s2" / "profile.json"
    )
    assert site.environment.scene_directory(path) == tmp_path / "environments"


def test_a_site_describes_itself_for_people_and_names_its_thumbnail(tmp_path):
    description = "Tracy stacks and sorts cubes on its table."
    path = write_site(
        tmp_path,
        site_data(
            formatVersion="1.1", description=description, thumbnail="thumbnail.png"
        ),
    )
    site = Site.from_file(path)
    assert site.description == description
    assert site.thumbnail_file(path) == tmp_path / "thumbnail.png"
    assert site.extensions == {}
    assert site.to_json()[SiteKey.DESCRIPTION] == description


def test_a_thumbnail_of_private_data_is_named_by_an_environment_variable(tmp_path):
    path = write_site(
        tmp_path,
        site_data(formatVersion="1.1", thumbnail="${SCANS}/hall/thumbnail.png"),
    )
    site = Site.from_file(path)
    assert site.thumbnail_file(path, {"SCANS": "/data/scans"}) == Path(
        "/data/scans/hall/thumbnail.png"
    )
    with pytest.raises(UnsetSiteVariable):
        site.thumbnail_file(path, {})


def test_a_site_of_the_first_minor_version_has_no_description_and_no_thumbnail(
    tmp_path,
):
    path = write_site(tmp_path, site_data())
    site = Site.from_file(path)
    assert site.description is None
    assert site.thumbnail_file(path) is None
    assert SiteKey.DESCRIPTION not in site.to_json()


def test_a_site_without_an_environment_stands_its_robots_on_an_empty_floor(tmp_path):
    data = site_data()
    del data["environment"]
    assert Site.from_file(write_site(tmp_path, data)).environment is None


def test_a_site_of_a_later_minor_version_keeps_the_keys_it_does_not_know(tmp_path):
    later = ProtocolVersion(SITE_FORMAT.major, SITE_FORMAT.minor + 1)
    data = site_data(formatVersion=later.to_json(), lockFile="site.lock")
    data["robots"][0]["driver"] = "ur_rtde"
    data["robots"][0]["commissioning"]["measuredOn"] = "2026-11-01"
    site = Site.from_file(write_site(tmp_path, data))
    assert site.format_version == later
    assert site.extensions == {"lockFile": "site.lock"}
    assert site.robots[0].extensions == {"driver": "ur_rtde"}
    assert site.robots[0].commissioning.facts == {"measuredOn": "2026-11-01"}
    assert site.to_json() == data


def test_a_site_of_another_major_version_is_refused(tmp_path):
    with pytest.raises(UnsupportedProtocolVersion):
        Site.from_file(write_site(tmp_path, site_data(formatVersion="2.0")))


def test_a_site_must_declare_its_format_version(tmp_path):
    data = site_data()
    del data[SiteKey.FORMAT_VERSION]
    with pytest.raises(MissingSiteFormatVersion):
        Site.from_file(write_site(tmp_path, data))


def test_a_site_naming_a_robot_twice_is_refused(tmp_path):
    data = site_data()
    data["robots"].append(dict(data["robots"][0]))
    with pytest.raises(DuplicateSiteRobot):
        Site.from_file(write_site(tmp_path, data))


def test_a_site_naming_a_zone_twice_is_refused(tmp_path):
    data = site_data()
    data["zones"].append(dict(data["zones"][0]))
    with pytest.raises(DuplicateSiteZone):
        Site.from_file(write_site(tmp_path, data))


def test_a_robot_pose_whose_orientation_is_no_unit_quaternion_is_refused(tmp_path):
    data = site_data()
    data["robots"][0]["pose"] = [0, 0, 0, 0, 0, 0, 0]
    with pytest.raises(InvalidSiteRobotPose):
        Site.from_file(write_site(tmp_path, data))


def test_a_site_robot_is_found_by_any_name_the_registry_gives_it(tmp_path):
    site = Site.from_file(write_site(tmp_path, site_data()))
    assert site.robot_named("example.walker_s2") is site.robots[0]
    assert site.robot_named("tracy") is None


def test_a_site_names_a_scene_directory_outside_the_repository_by_a_variable(tmp_path):
    data = site_data(environment={"bundle": "lab", "scenes": "${PRIVATE_SCENES}/sites"})
    path = write_site(tmp_path, data)
    site = Site.from_file(path)
    directory = site.environment.scene_directory(
        path, {"PRIVATE_SCENES": "/data/customer"}
    )
    assert directory == Path("/data/customer/sites")


def test_a_site_refuses_a_scene_directory_whose_variable_is_not_set(tmp_path):
    data = site_data(environment={"bundle": "lab", "scenes": "${PRIVATE_SCENES}"})
    path = write_site(tmp_path, data)
    with pytest.raises(UnsetSiteVariable):
        Site.from_file(path).environment.scene_directory(path, {})
