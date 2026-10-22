"""
Trajectories, statecharts, lighting and the scenes index.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.index import (
    IndexKey,
    InvalidSceneName,
    ReservedSceneName,
    SceneIndex,
    SceneIndexEntry,
    SceneName,
)
from cramera_protocol.bundle.lighting import Lighting, LightingKey
from cramera_protocol.bundle.statecharts import Statecharts, StatechartsKey
from cramera_protocol.bundle.trajectory import Trajectory, TrajectoryKey
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.version import UNVERSIONED

# %% trajectory


def test_a_trajectory_holds_one_entry_per_frame(read_json):
    data = read_json("recorded_cell/trajectory.json")
    trajectory = Trajectory.from_json(data)
    assert trajectory.frame_count() == len(data[TrajectoryKey.FRAMES])
    assert trajectory.frames_per_second == data[TrajectoryKey.LEGACY_FRAMES_PER_SECOND]
    assert Trajectory.from_json(trajectory.to_json()) == trajectory


def test_trajectory_poses_are_read_per_frame():
    trajectory = Trajectory.from_json(
        {
            TrajectoryKey.FRAMES: [{"joint": 0.5}],
            TrajectoryKey.BASE: [[1, 0, 0, 0, 0, 0, 1]],
            TrajectoryKey.OBJECTS: [{"cup": [0, 1, 0, 0, 0, 0, 1]}],
        }
    )
    assert trajectory.base == [Pose(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)]
    assert trajectory.objects[0]["cup"].y == 1.0


# %% statecharts


def test_statecharts_map_frames_to_moments(read_json):
    data = read_json("statecharts_excerpt.json")
    statecharts = Statecharts.from_json(data)
    assert statecharts.frames == data[StatechartsKey.FRAMES]
    for moment in statecharts.moments:
        chart = statecharts.charts[moment.chart]
        assert len(moment.life_cycles) == len(chart.nodes)
    assert Statecharts.from_json(statecharts.to_json()) == statecharts


# %% lighting


def test_lighting_reads_sun_dome_and_panels(read_json):
    data = read_json("converted_bundle/lighting.json")
    lighting = Lighting.from_json(data)
    assert lighting.sun.direction == Vector3.from_json(
        data[LightingKey.SUN]["direction"]
    )
    assert len(lighting.panels) == len(data[LightingKey.PANELS])
    assert Lighting.from_json(lighting.to_json()) == lighting


def test_a_stage_without_lights_has_empty_lighting():
    lighting = Lighting.from_json({LightingKey.SUN: None, LightingKey.DOME: None})
    assert lighting.sun is None and lighting.panels == []


# %% index


def test_an_unversioned_index_is_read(read_json):
    data = read_json("unversioned_index.json")
    index = SceneIndex.from_json(data)
    assert index.format_version == UNVERSIONED
    assert index.default == data[IndexKey.DEFAULT]
    assert [entry.name for entry in index.scenes] == [
        entry["name"] for entry in data[IndexKey.SCENES]
    ]


def test_an_index_finds_its_entries():
    index = SceneIndex(scenes=[SceneIndexEntry(name="cell", robot="arm")])
    assert index.entry("cell").robot == "arm"
    assert index.entry("missing") is None


@pytest.mark.parametrize("name", ["pr2_kitchen", "A-1", "x" * 64])
def test_valid_scene_names_are_accepted(name):
    assert SceneName(name).text == name


@pytest.mark.parametrize(
    "name",
    ["", "x" * 65, "../escape", "with space", "a/b", "name\n", *ReservedSceneName],
)
def test_invalid_scene_names_are_refused(name):
    with pytest.raises(InvalidSceneName):
        SceneName(name)
