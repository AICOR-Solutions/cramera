"""
The state of a task demo the laboratory runs on request.
"""

from __future__ import annotations

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.laboratory.runs import TaskRun, TaskRunKey, TaskRunState

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
