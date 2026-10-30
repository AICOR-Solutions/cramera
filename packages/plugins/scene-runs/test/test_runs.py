"""
Starting the offered runs one at a time, stopping them, and telling how they ended.
"""

from __future__ import annotations

import json
import time

import pytest

from cramera_protocol.scene_runs import SceneRunCatalog, SceneRunState
from cramera_scene_runs.exceptions import (
    InvalidSceneRunCatalog,
    SceneRunBusy,
    SceneRunNotStarted,
    UnknownSceneRun,
)
from cramera_scene_runs.runs import SceneRunCatalogFile, SceneRunner

from .conftest import START, fake_run


@pytest.fixture
def runner(catalog, scenes, tmp_path):
    """
    :return: A runner of the catalog whose recordings exist once their bundle does.
    """
    runner = SceneRunner(
        catalog=catalog,
        logs=tmp_path / "logs",
        recorded=lambda name: (scenes / name / "scene.json").is_file(),
        clock=lambda: START,
        stop_timeout=2.0,
    )
    yield runner
    runner.close()


def finished(runner: SceneRunner, timeout: float = 20.0):
    """
    :return: The runner's state once the run started last no longer runs.
    """
    deadline = time.monotonic() + timeout
    state = runner.state()
    while state.current.state is SceneRunState.RUNNING:
        assert time.monotonic() < deadline, "the run did not end"
        time.sleep(0.05)
        state = runner.state()
    return state


# %% offering


def test_pages_see_the_offered_runs_without_their_commands(runner):
    state = runner.state()
    assert [run.identifier for run in state.runs] == [
        "pr2_transfer",
        "fr3_plates",
        "garmi_apartment",
    ]
    assert state.runs[0].scene == "aicor_medical_lab_pr2"
    assert state.current is None
    assert "command" not in json.dumps(state.to_json())


# %% running


def test_a_run_records_under_a_new_name(runner, scenes, tmp_path):
    started = runner.start("pr2_transfer")
    assert started.current.state is SceneRunState.RUNNING
    assert started.current.recording == "pr2_transfer_20261028_120000"
    state = finished(runner)
    assert state.current.state is SceneRunState.RECORDED
    assert "saved pr2_transfer_20261028_120000" in state.current.log
    assert (tmp_path / "logs" / "pr2_transfer_20261028_120000.log").is_file()


def test_a_run_that_ends_without_a_recording_failed(runner):
    runner.start("fr3_plates")
    state = finished(runner)
    assert state.current.state is SceneRunState.FAILED
    assert "could not reach the vessel" in state.current.log


def test_one_run_runs_at_a_time(runner):
    runner.start("garmi_apartment")
    with pytest.raises(SceneRunBusy) as busy:
        runner.start("pr2_transfer")
    assert busy.value.status() == 409
    assert "garmi apartment" in busy.value.message()


def test_a_stopped_run_says_so_and_the_next_one_starts(runner):
    runner.start("garmi_apartment")
    stopped = runner.stop()
    assert stopped.current.state is SceneRunState.STOPPED
    runner.start("pr2_transfer")
    assert finished(runner).current.state is SceneRunState.RECORDED


def test_stopping_without_a_run_changes_nothing(runner):
    assert runner.stop().current is None


def test_a_run_that_ignores_the_request_to_end_is_killed(catalog, scenes, tmp_path):
    stubborn = fake_run("stubborn", scenes, "wait")
    stubborn.command = [
        stubborn.command[0],
        "-c",
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(60)",
    ]
    runner = SceneRunner(
        catalog=SceneRunCatalog(runs=[stubborn]),
        logs=tmp_path / "logs",
        recorded=lambda name: False,
        stop_timeout=0.3,
    )
    runner.start("stubborn")
    time.sleep(0.3)
    assert runner.stop().current.state is SceneRunState.STOPPED


@pytest.mark.parametrize("identifier", ["unknown", "../pr2_transfer", ""])
def test_only_offered_runs_start(runner, identifier):
    with pytest.raises(UnknownSceneRun) as unknown:
        runner.start(identifier)
    assert unknown.value.status() == 404


def test_a_command_the_system_cannot_start_is_reported(scenes, tmp_path):
    missing = fake_run("missing", scenes, "record")
    missing.command = [str(tmp_path / "no_such_program")]
    runner = SceneRunner(
        catalog=SceneRunCatalog(runs=[missing]),
        logs=tmp_path / "logs",
        recorded=lambda name: False,
    )
    with pytest.raises(SceneRunNotStarted) as refused:
        runner.start("missing")
    assert refused.value.status() == 503
    assert runner.state().current is None


# %% catalog file


def test_the_catalog_file_names_the_offered_runs(catalog, tmp_path):
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(catalog.to_json()), encoding="utf-8")
    assert SceneRunCatalogFile(path).read() == catalog


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"runs": [{"identifier": "a"}]}',
        '{"runs": [{"identifier": "Has Spaces", "label": "x", "command": ["x"]}]}',
        '{"runs": [{"identifier": "a", "label": "x", "command": []}]}',
        '{"runs": ['
        '{"identifier": "a", "label": "x", "command": ["x"]},'
        '{"identifier": "a", "label": "y", "command": ["y"]}]}',
    ],
)
def test_a_catalog_file_the_viewer_cannot_offer_is_refused(tmp_path, content):
    path = tmp_path / "runs.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(InvalidSceneRunCatalog) as invalid:
        SceneRunCatalogFile(path).read()
    assert str(path) in invalid.value.message()


def test_a_missing_catalog_file_is_refused(tmp_path):
    with pytest.raises(InvalidSceneRunCatalog):
        SceneRunCatalogFile(tmp_path / "missing.json").read()
