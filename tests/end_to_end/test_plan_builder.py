"""
The plan builder out of the box: a PR2 in the apartment gets a plan composed through the
builder's routes, the plan is saved and exported, its demo is run from the builder, and
the recording it saves replays in the viewer.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from typing_extensions import Any, Dict, Iterator, List

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import PlanNode
from cramera_protocol.plan_builder import (
    PlanBuilderCatalog,
    PlanBuilderRoute,
    PLAN_FORMAT_VERSION,
    PlanRecord,
    RunMode,
    RunRequest,
    RunState,
    RunStatus,
    SavedDemo,
)
from cramera_protocol.viewer import ViewerRoute

from .conftest import POLL_INTERVAL, SceneReplay, Viewer, start_viewer

BUILDER = f"{ViewerRoute.PLUGIN_API}plan-builder/"
"""
Where the plan builder's routes are served.
"""

ENVIRONMENT = "apartment"
"""
The environment bundle the plan runs in, built from coraplex's apartment.
"""

ROBOT = "PR2"
"""
The robot the plan is composed for.
"""

MILK_START = (2.37, 2.0, 1.0345)
"""
Where the milk stands on the apartment's counter, as coraplex's apartment demo puts it.
"""

LIFTED = 0.05
"""
How much higher than it started the milk must end, in metres, for the pick-up to count.
"""

RUN_TIMEOUT = 900.0
"""
How long the plan's demo may take, in seconds.
"""

PLAN: Dict[str, Any] = {
    "formatVersion": "1.1",
    "name": "pr2_apartment_pick",
    "task": "Pick the milk up from the counter",
    "environment": ENVIRONMENT,
    "selectedRobot": "robot_1",
    "robots": [
        {
            "id": "robot_1",
            "model": ROBOT,
            "label": "PR2 1",
            "pose": [1.1, 2.5, 0.0, 0.0, 0.0, 0.0, 1.0],
            "steps": [
                {
                    "id": "step_1",
                    "action": "ParkArmsAction",
                    "values": {"arms": "BOTH"},
                },
                {
                    "id": "step_2",
                    "action": "MoveTorsoAction",
                    "values": {"torso_state": "HIGH"},
                },
                {
                    "id": "step_3",
                    "action": "NavigateAction",
                    "values": {"target_location": [1.7, 2.0, 0.0, 0.0, 0.0, 0.0, 1.0]},
                },
                {
                    "id": "step_4",
                    "action": "PickUpAction",
                    "values": {"grasp": "milk", "arm": "LEFT"},
                },
            ],
        }
    ],
    "objects": [
        {
            "id": "milk",
            "model": "milk.stl",
            "pose": [*MILK_START, 0.0, 0.0, 0.0, 1.0],
            "color": "#e6ecff",
        }
    ],
}
"""
The plan a person composed in the builder: the PR2 parks its arms, raises its torso,
drives to the counter and picks the milk up.

It is a plan of format 1.1, naming the planner's classes, as plans saved before the
protocol had its own names do; the builder translates it to the catalog's identifiers.
"""

ACTIONS = [step["action"] for step in PLAN["robots"][0]["steps"]]
"""
The actions of the plan, in order.
"""


def apartment_bundle(scenes: Path, apartment_urdf: Path) -> None:
    """
    Write the apartment as an environment bundle, as the scene builder writes one: a
    scene description naming the world's URDF, and no robot.

    :param scenes: A scenes directory.
    :param apartment_urdf: coraplex's apartment.
    """
    bundle = scenes / ENVIRONMENT
    bundle.mkdir()
    shutil.copy(apartment_urdf, bundle / apartment_urdf.name)
    description = {
        "name": ENVIRONMENT,
        "formatVersion": "1.0",
        "environmentName": "Apartment",
        "models": [
            {
                "name": ENVIRONMENT,
                "urdf": apartment_urdf.name,
                "prefix": "",
                "robot": False,
                "links": 1,
                "movableJoints": [],
            }
        ],
        "objects": [],
    }
    (bundle / BundleFile.SCENE).write_text(json.dumps(description))


def finished_run(viewer: Viewer, started: RunStatus) -> RunStatus:
    """
    :param viewer: The viewer the run was started from.
    :param started: The state the run started in.
    :return: The run's state once it ended.
    :raises AssertionError: When it does not end in time.
    """
    status, deadline = started, time.monotonic() + RUN_TIMEOUT
    while status.state is RunState.RUNNING:
        assert time.monotonic() < deadline, f"the demo did not end:\n{status.log}"
        threading.Event().wait(POLL_INTERVAL)
        status = RunStatus.from_json(viewer.client.get(BUILDER + PlanBuilderRoute.RUN))
    return status


def nodes_of(roots: List[PlanNode]) -> List[PlanNode]:
    """
    :param roots: Recorded plan trees.
    :return: Every node of them.
    """
    nodes, pending = [], list(roots)
    while pending:
        node = pending.pop(0)
        nodes.append(node)
        pending.extend(node.children)
    return nodes


@dataclass
class BuilderRun:
    """
    What the builder answered while a plan was composed, saved, exported and run, and
    the viewer replaying the recording.
    """

    catalog: PlanBuilderCatalog
    """
    What the builder offered.
    """

    saved: PlanRecord
    """
    The saved plan.
    """

    exported: SavedDemo
    """
    Where the plan's demo was written.
    """

    status: RunStatus
    """
    The run once it ended.
    """

    replay: SceneReplay
    """
    The recording the run saved, as the viewer serves it.
    """


@pytest.fixture(scope="module")
def builder_run(tmp_path_factory, coraplex_resources) -> Iterator[BuilderRun]:
    """
    :return: The plan composed, saved, exported and run once through a viewer whose
        shared scenes hold the apartment.
    """
    work = tmp_path_factory.mktemp("plan_builder")
    scenes = work / "shared_scenes"
    scenes.mkdir()
    apartment_bundle(scenes, coraplex_resources.world("apartment.urdf"))
    viewer = start_viewer(work, work / "data", scenes)
    try:
        catalog = PlanBuilderCatalog.from_json(
            viewer.client.get(BUILDER + PlanBuilderRoute.CATALOG)
        )
        record = PlanRecord.from_json({"document": PLAN})
        saved = PlanRecord.from_json(
            viewer.client.post(BUILDER + PlanBuilderRoute.PLANS, record.to_json())
        )
        exported = SavedDemo.from_json(
            viewer.client.post(
                BUILDER + PlanBuilderRoute.DEMOS, saved.document.to_json()
            )
        )
        request = RunRequest(plan=saved.document, mode=RunMode.PERFORM)
        started = RunStatus.from_json(
            viewer.client.post(BUILDER + PlanBuilderRoute.RUN, request.to_json())
        )
        status = finished_run(viewer, started)
        names = [name for name in viewer.scene_names() if name.endswith(PLAN["name"])]
        yield BuilderRun(
            catalog=catalog,
            saved=saved,
            exported=exported,
            status=status,
            replay=SceneReplay(viewer, names[0] if names else PLAN["name"]),
        )
    finally:
        viewer.server.stop()


def test_the_builder_offers_the_pr2_the_apartment_the_milk_and_the_actions(
    builder_run,
):
    catalog = builder_run.catalog
    assert ROBOT in [saved for robot in catalog.robots for saved in robot.saved_as]
    assert ENVIRONMENT in [entry.name for entry in catalog.environments]
    assert "milk.stl" in [model.identifier for model in catalog.objects]
    saved_actions = {saved for action in catalog.actions for saved in action.saved_as}
    assert set(ACTIONS) <= saved_actions


def test_the_plan_is_saved_and_exported_as_a_demo(builder_run):
    assert builder_run.saved.identifier is not None
    saved = builder_run.saved.document
    assert saved.format_version == PLAN_FORMAT_VERSION
    assert saved.robots[0].model == "pr2"
    assert [step.action for step in saved.robots[0].steps] == [
        "park_arms",
        "move_torso",
        "navigate",
        "pick_up",
    ]
    assert Path(builder_run.exported.path).is_file()
    assert PLAN["name"] in Path(builder_run.exported.path).read_text()


def test_the_demo_runs_to_its_end(builder_run):
    status = builder_run.status
    assert (status.state, status.return_code) == (RunState.FINISHED, 0), status.log


def test_the_recording_replays_the_plan_and_the_pick_up(builder_run):
    replay = builder_run.replay
    assert replay.name in replay.viewer.scene_names()
    description = replay.description()
    assert [model.name for model in description.models] == ["environment", "pr2"]
    (root,) = description.plan_trees
    assert root.status == "SUCCEEDED"
    nodes = nodes_of([root])
    assert all(action in [node.label for node in nodes] for action in ACTIONS)
    assert all(
        node.status == "SUCCEEDED" for node in nodes if node.kind == "MotionNode"
    )
    trajectory = replay.trajectory()
    assert trajectory.frame_count() > 0
    (milk,) = description.objects
    start, end = trajectory.objects[0][milk.key], trajectory.objects[-1][milk.key]
    assert start.z == pytest.approx(MILK_START[2], abs=0.01)
    assert end.z - start.z > LIFTED
    assert replay.unserved_files() == []


def test_every_recorded_action_succeeded_and_names_its_frames(builder_run):
    (root,) = builder_run.replay.description().plan_trees
    actions = [node for node in nodes_of([root]) if node.label in ACTIONS]
    assert [node.status for node in actions] == ["SUCCEEDED"] * len(ACTIONS)
    assert all(node.start is not None and node.end is not None for node in actions)
