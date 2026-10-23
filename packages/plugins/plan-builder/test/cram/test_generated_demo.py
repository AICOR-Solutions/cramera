"""
The plan builder against the installed CRAM workspace, which it reaches through cramera-
cram only: the catalog read from it, the generated demo importing cramera-bridge's plan
demo command, and a staged demo started as a child process.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import time

import pytest

from cramera_bridge.plans.command import PlanDemoCommand
from cramera_plan_builder.demos import DemoDirectory, DemoTemplate
from cramera_plan_builder.runs import DemoRunner
from cramera_plan_builder.workspace import InstalledWorkspace, WorkspaceLoader
from cramera_protocol.live import LIVE_HOST, LiveRoute
from cramera_protocol.plan_builder import (
    DemoDocument,
    PlanDocument,
    RunMode,
    RunState,
)
from cramera_protocol.viewer import EnvironmentVariable

from ..dataset.given_workspace import DATASET
from ..dataset.live_reader import ObjectCatalogReader

PLAN_FILE = DATASET / "plans" / "pick_and_place.json"
"""
The plan the tests run: one PR2 picks the milk up and puts it down, another stands.
"""

STAGE_WAIT = 300.0
"""
How long the staging test waits for the staged world, in seconds.
"""

STAGE_POLL_INTERVAL = 0.5
"""
How often the staging test asks the staged world, in seconds.
"""


@pytest.fixture
def document() -> DemoDocument:
    """
    :return: The test plan on an empty floor.
    """
    return DemoDocument(
        plan=PlanDocument.from_json(json.loads(PLAN_FILE.read_text("utf-8")))
    )


def free_port() -> int:
    """
    :return: A port no process listens on right now.
    """
    with socket.socket() as probe:
        probe.bind((LIVE_HOST, 0))
        return probe.getsockname()[1]


# %% the catalog


@pytest.fixture(scope="module")
def workspace() -> InstalledWorkspace:
    """
    :return: The workspace this interpreter imports, as the loader reads it.
    """
    return WorkspaceLoader().workspace()


def test_the_loader_reads_the_installed_workspace(workspace):
    assert isinstance(workspace, InstalledWorkspace)
    assert workspace.missing() == []


def test_the_installed_workspace_serves_its_object_meshes(workspace):
    assert "milk.stl" in [model.identifier for model in workspace.objects()]
    assert (
        workspace.object_file("milk.stl")
        == (workspace.object_directory() / "milk.stl").resolve()
    )


# %% the generated file


def test_the_generated_demo_imports_and_carries_its_plan(tmp_path, document):
    saved = DemoDirectory(tmp_path).write(DemoTemplate().render(document))
    specification = importlib.util.spec_from_file_location(
        document.plan.name, saved.path
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    assert module.PlanDemoCommand is PlanDemoCommand
    assert PlanDemoCommand.of_text(module.DEMO).document == document


# %% running


def test_a_staged_demo_publishes_its_world_until_it_is_stopped(
    tmp_path, document, monkeypatch
):
    monkeypatch.setenv(EnvironmentVariable.DATA, str(tmp_path / "data"))
    port = free_port()
    runner = DemoRunner(
        directory=DemoDirectory(tmp_path / "demos", interpreter=sys.executable),
        port=port,
        log_limit=64 * 1024,
    )
    runner.start(document, RunMode.STAGE)
    objects_url = f"http://{LIVE_HOST}:{port}{LiveRoute.OBJECTS}"
    deadline = time.monotonic() + STAGE_WAIT
    catalog = None
    while catalog is None and time.monotonic() < deadline:
        assert runner.status().state is RunState.RUNNING, runner.status().log
        catalog = ObjectCatalogReader(objects_url).read()
        time.sleep(STAGE_POLL_INTERVAL)
    stopped = runner.stop()
    assert [item.identifier for item in catalog.objects] == ["milk"]
    assert stopped.state is RunState.STOPPED
