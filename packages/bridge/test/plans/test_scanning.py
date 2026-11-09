"""
Scanning the scene for a plan's objects: Tracy's simulated camera, rendered from a scene
holding three cubes, fills a plan whose twin holds none with a copy of the cube model of
each color seen, where it was seen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from importlib.util import find_spec

import numpy as np
import pytest

from coraplex.perception import Detection
from cramera_bridge.execution import PERCEPTION_ENGINE_VARIABLE
from cramera_bridge.plans.objects import LIBRARY_VARIABLE
from cramera_bridge.plans.scanning import SceneScanner
from cramera_bridge.plans.world import PlannedGraspable
from cramera_protocol.detection import DetectionGrounding, SceneScan, SceneScanOrder
from cramera_protocol.plan_builder import DemoDocument, PlanDocument, PlannedObject
from krrood_spatial_math.spatial_types import Pose
from semantic_digital_twin.robots.tracy import Tracy
from semantic_digital_twin.world_description.color_names import ColorName

from ..dataset.bundles import DATASET

pytestmark = pytest.mark.skipif(
    not Tracy.is_description_installed(),
    reason="iai_tracy_description is not installed",
)

CUBE_LIBRARY = DATASET / "cube_library"
"""
A red, a yellow and a blue cube, each named by its color.
"""

TRACY_CUBES = DATASET / "plans" / "tracy_cubes.json"
"""
Tracy with a red, a yellow and a blue cube on its table.
"""

SCANNED_POSITION_TOLERANCE = 0.01
"""
How far, in metres, a cube found may lie from where it stands in the simulated scene.
"""

# %% fixtures


@pytest.fixture
def cubes() -> PlanDocument:
    """
    :return: The plan of Tracy and the three cubes on its table.
    """
    return PlanDocument.from_json(json.loads(TRACY_CUBES.read_text("utf-8")))


@pytest.fixture
def empty_twin(cubes: PlanDocument) -> PlanDocument:
    """
    :return: The plan of Tracy without objects or steps.
    """
    [robot] = cubes.robots
    return replace(cubes, objects=[], robots=[replace(robot, steps=[])])


def model_of(scanned: PlannedObject, objects: list[PlannedObject]) -> PlannedObject:
    """
    :return: The object of ``objects`` that is a copy of the scanned object's model.
    """
    [matching] = [item for item in objects if item.model == scanned.model]
    return matching


# %% matching models


def test_a_cube_found_is_a_copy_of_the_model_of_its_color(monkeypatch, cubes):
    monkeypatch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))
    scanner = SceneScanner(SceneScanOrder(demo=DemoDocument(plan=cubes)))

    for standing in cubes.objects:
        color = ColorName(standing.identifier.removesuffix("_cube"))
        found = Detection(PlannedGraspable, Pose(), color=color)
        assert scanner.matching_model(found) == standing.model


def test_a_found_object_of_a_color_no_model_shows_matches_none(monkeypatch, cubes):
    monkeypatch.setenv(LIBRARY_VARIABLE, str(CUBE_LIBRARY))
    scanner = SceneScanner(SceneScanOrder(demo=DemoDocument(plan=cubes)))

    found = Detection(PlannedGraspable, Pose(), color=ColorName.GREEN)

    assert scanner.matching_model(found) is None


def test_an_identity_taken_gets_the_next_number(cubes):
    assert SceneScanner.free_identifier("red_cube", cubes.objects) == "red_cube_2"
    assert SceneScanner.free_identifier("green_cube", cubes.objects) == "green_cube"


# %% scanning through the simulated camera


@pytest.mark.skipif(
    find_spec("robokudo_msgs") is None, reason="RoboKudo's messages are not installed"
)
def test_a_scan_of_the_simulated_scene_fills_an_empty_twin_with_the_three_cubes(
    tmp_path, cubes, empty_twin
):
    order_file = tmp_path / "order.json"
    scan_file = tmp_path / "scan.json"
    order = SceneScanOrder(
        demo=DemoDocument(plan=empty_twin), simulated_objects=cubes.objects
    )
    order_file.write_text(json.dumps(order.to_json()), encoding="utf-8")

    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "cramera_bridge.plans.scanning",
            str(order_file),
            str(scan_file),
        ],
        env={
            **os.environ,
            LIBRARY_VARIABLE: str(CUBE_LIBRARY),
            PERCEPTION_ENGINE_VARIABLE: "tracy_cubes",
        },
        capture_output=True,
        timeout=600,
    )

    assert finished.returncode == 0, finished.stderr.decode()[-4000:]
    scan = SceneScan.from_json(json.loads(scan_file.read_text("utf-8")))
    assert scan.grounding is DetectionGrounding.PERCEIVED
    assert sorted(item.model for item in scan.objects) == sorted(
        item.model for item in cubes.objects
    )
    for scanned in scan.objects:
        standing = model_of(scanned, cubes.objects)
        np.testing.assert_allclose(
            scanned.pose.to_json()[:2],
            standing.pose.to_json()[:2],
            atol=SCANNED_POSITION_TOLERANCE,
        )
