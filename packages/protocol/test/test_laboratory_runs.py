"""
The state of a task demo the laboratory runs on request.
"""

from __future__ import annotations

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.laboratory.runs import (
    DemoRoute,
    LaboratoryDemo,
    TaskRecording,
    TaskRun,
    TaskRunKey,
    TaskRunState,
)

SCENE = "aicor_medical_lab_pr2_transfer"
"""
The recording the transfer demo saves.
"""

FAILURE = "the vessel is still held"
"""
Why the demo of the test failed.
"""


def test_a_running_demo_names_its_recording_without_an_error():
    written = TaskRun(state=TaskRunState.RUNNING, scene=SCENE).to_json()
    assert written == {TaskRunKey.STATE: TaskRunState.RUNNING, TaskRunKey.SCENE: SCENE}


def test_a_failed_demo_round_trips_with_its_error():
    run = TaskRun(state=TaskRunState.FAILED, scene=SCENE, error=FAILURE)
    assert TaskRun.from_json(run.to_json()) == run


def test_the_browser_reads_the_run_states():
    assert {TaskRunState, TaskRunKey} <= set(BROWSER_ENUMERATIONS)


def test_a_running_demo_carries_its_local_live_address_and_run_availability():
    run = TaskRun(
        state=TaskRunState.RUNNING,
        scene=SCENE,
        live_url="/api/plugins/laboratory/transfer/live/",
        can_run=True,
    )
    assert TaskRun.from_json(run.to_json()) == run


# %% demos


def test_every_demo_saves_a_recording_of_its_own():
    recordings = [demo.recording for demo in LaboratoryDemo]
    assert set(recordings) == set(TaskRecording)
    assert len(recordings) == len(set(recordings))


def test_every_demo_answers_on_routes_below_its_own_name():
    routes = {
        demo: [demo.route(route) for route in DemoRoute] for demo in LaboratoryDemo
    }
    for demo, own in routes.items():
        assert all(route.startswith(f"{demo.value}/") for route in own)
    assert len({route for own in routes.values() for route in own}) == len(
        LaboratoryDemo
    ) * len(DemoRoute)


def test_the_browser_reads_the_demos_and_their_routes():
    assert {LaboratoryDemo, DemoRoute} <= set(BROWSER_ENUMERATIONS)
