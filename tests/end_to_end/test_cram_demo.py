"""
A CRAM demo shown in cramera: coraplex's apartment demo runs unchanged under ``cramera-
live``, its world and plan are published while it runs, the recording is saved, and the
saved scene replays in the viewer.
"""

from __future__ import annotations

import shutil
import threading
import time
import urllib.error
from dataclasses import dataclass

import pytest
from typing_extensions import Iterator, List

from cramera_protocol.bundle.index import ReservedSceneName
from cramera_protocol.live import LIVE_PORT, LiveInfo, LiveRoute
from cramera_protocol.live_messages import (
    LivePlan,
    LiveScene,
    ObjectCatalog,
    RecordingSaveRequest,
    RecordingState,
    RecordingStatus,
    SavedScene,
)

from .conftest import (
    LOCALHOST,
    POLL_INTERVAL,
    JsonClient,
    SceneReplay,
    ServerProcess,
    stack_environment,
    start_viewer,
)

DEMO = "coraplex_bullet_world_demo"
"""
The demo: the PR2 lays a place setting in the apartment, carrying the milk, a bowl and a
spoon onto the table.
"""

CARRIED = 3
"""
How many objects the demo carries.
"""

SAVED_NAME = "pr2_place_setting"
"""
The name the recording is saved under.
"""

DEMO_TIMEOUT = 1200.0
"""
How long the demo's plan may take, in seconds.
"""

FINISHED = ("SUCCEEDED", "FAILED")
"""
The statuses a plan's root ends with.
"""


@dataclass
class DemoRun:
    """
    What a scenario saw while the demo ran, and the viewer replaying its recording.
    """

    info: LiveInfo
    """
    What the publisher said about itself.
    """

    live_scene: LiveScene
    """
    The bundle the publisher wrote of the world.
    """

    objects: List[ObjectCatalog]
    """
    The free objects the publisher listed, every time the scenario looked.
    """

    plan: LivePlan
    """
    The plan once its root ended.
    """

    saved: RecordingStatus
    """
    The recording once it was finished.
    """

    replay: SceneReplay
    """
    The saved recording as the viewer serves it.
    """


def finished_plan(client: JsonClient, publisher: ServerProcess, seen: List) -> LivePlan:
    """
    :param client: Reads the publisher's routes.
    :param publisher: The publisher's process.
    :param seen: Receives the free objects the publisher lists while the plan runs.
    :return: The plan once its root ended.
    :raises AssertionError: When the demo ends early or the plan does not end in time.
    """
    deadline = time.monotonic() + DEMO_TIMEOUT
    while time.monotonic() < deadline:
        assert publisher.process.poll() is None, publisher.output()[-4000:]
        threading.Event().wait(POLL_INTERVAL)
        try:
            plan = LivePlan.from_json(client.get(LiveRoute.PLAN))
        except (urllib.error.URLError, ConnectionError):
            continue
        roots = [node for node in plan.nodes if node.parent is None]
        if roots:
            seen.append(ObjectCatalog.from_json(client.get(LiveRoute.OBJECTS)))
        if roots and roots[0].status in FINISHED:
            return plan
    raise AssertionError(f"the demo's plan did not end:\n{publisher.output()[-4000:]}")


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory, coraplex_resources) -> Iterator[DemoRun]:
    """
    :return: The demo run once, published, saved and served by a viewer on the same
        data directory.
    """
    work = tmp_path_factory.mktemp("cram_demo")
    data = work / "data"
    publisher = ServerProcess(
        [shutil.which("cramera-live"), str(coraplex_resources.demo(DEMO))],
        stack_environment(data),
        work / "live.log",
    ).start()
    client = JsonClient(f"http://{LOCALHOST}:{LIVE_PORT}")
    try:
        client.wait_until_answering(LiveRoute.INFO, publisher.process)
        info = LiveInfo.from_json(client.get(LiveRoute.INFO))
        seen: List[ObjectCatalog] = []
        plan = finished_plan(client, publisher, seen)
        live_scene = LiveScene.from_json(client.get(LiveRoute.LIVE_SCENE))
        saved = RecordingStatus.from_json(client.post(LiveRoute.RECORDING_STOP))
        SavedScene.from_json(
            client.post(
                LiveRoute.RECORDING_SAVE,
                RecordingSaveRequest(name=SAVED_NAME).to_json(),
            )
        )
    finally:
        publisher.stop()
    viewer = start_viewer(work, data)
    try:
        yield DemoRun(
            info=info,
            live_scene=live_scene,
            objects=seen,
            plan=plan,
            saved=saved,
            replay=SceneReplay(viewer, SAVED_NAME),
        )
    finally:
        viewer.server.stop()


def test_the_demo_is_published_while_it_runs(demo_run):
    assert demo_run.info.running
    assert demo_run.live_scene.scene == ReservedSceneName.LIVE
    (root,) = [node for node in demo_run.plan.nodes if node.parent is None]
    assert root.status == "SUCCEEDED"
    assert any(node.label == "TransportAction" for node in demo_run.plan.nodes)


def test_the_recording_is_saved_and_listed(demo_run):
    assert demo_run.saved.state is RecordingState.FINALIZED
    assert demo_run.saved.frame_count > 0
    assert SAVED_NAME in demo_run.replay.viewer.scene_names()


def test_the_saved_scene_replays_with_its_plan(demo_run):
    description = demo_run.replay.description()
    assert [model.name for model in description.models] == ["environment", "pr2"]
    (root,) = description.plan_trees
    assert root.status == "SUCCEEDED"
    assert demo_run.replay.trajectory().frame_count() == demo_run.saved.frame_count
    assert demo_run.replay.unserved_files() == []


@pytest.mark.xfail(
    strict=True,
    reason="#37: the demo fixes its objects to the apartment, so none is tracked",
)
def test_the_carried_objects_are_seen_and_move_in_the_replay(demo_run):
    assert max(len(catalog.objects) for catalog in demo_run.objects) == CARRIED
    description = demo_run.replay.description()
    assert len(description.objects) == CARRIED
    trajectory = demo_run.replay.trajectory()
    for entry in description.objects:
        start, end = trajectory.objects[0][entry.key], trajectory.objects[-1][entry.key]
        assert start != end
