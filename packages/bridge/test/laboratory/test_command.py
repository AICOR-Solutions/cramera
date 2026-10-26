"""
The optional transfer's plain-data command boundary, without importing CRAM.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cramera_bridge.laboratory import command
from cramera_protocol.laboratory.runs import LaboratoryDemo, TransferOption
from cramera_protocol.live_messages import SavedScene


def test_dependency_discovery_names_missing_modules_without_importing(monkeypatch):
    present = {"semantic_digital_twin", "coraplex"}
    monkeypatch.setattr(
        command.importlib.util,
        "find_spec",
        lambda name: object() if name in present else None,
    )
    before = set(sys.modules)
    assert command.missing_libraries() == ["giskardpy", "krrood", "segmind"]
    assert set(sys.modules) == before


def test_a_missing_workspace_stops_before_loading_native_transfer(monkeypatch, capsys):
    monkeypatch.setattr(command, "missing_libraries", lambda: ["coraplex"])
    called = []
    monkeypatch.setattr(
        command, "run_transfer", lambda *arguments: called.append(arguments)
    )
    with pytest.raises(SystemExit) as stopped:
        command.main([TransferOption.BUNDLE, "/laboratory"])
    assert stopped.value.code == 2
    assert "CRAM workspace: coraplex" in capsys.readouterr().err
    assert called == []


def test_the_command_passes_the_bundle_path_and_task_options(monkeypatch, tmp_path):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    called = []
    monkeypatch.setattr(
        command, "run_transfer", lambda *arguments: called.append(arguments)
    )
    command.main([TransferOption.BUNDLE, str(tmp_path), "--port", "0"])
    assert called == [(str(tmp_path), ["--port", "0"])]


def test_the_command_requires_an_explicit_bundle(monkeypatch):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    with pytest.raises(SystemExit) as stopped:
        command.main([])
    assert stopped.value.code == 2


def test_the_preview_command_returns_a_protocol_scene_without_running_transfer(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    called = []

    def preview(bundle, scenes):
        called.append((bundle, scenes))
        return SavedScene(scene="aicor_medical_lab_pr2")

    monkeypatch.setattr(command, "prepare_preview", preview)
    command.main(
        [TransferOption.BUNDLE, "/laboratory", TransferOption.PREVIEW, str(tmp_path)]
    )
    assert called == [("/laboratory", str(tmp_path))]
    assert capsys.readouterr().out.strip() == '{"scene": "aicor_medical_lab_pr2"}'


def test_the_preview_command_rejects_transfer_only_options(monkeypatch, tmp_path):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    with pytest.raises(SystemExit) as stopped:
        command.main(
            [
                TransferOption.BUNDLE,
                "/laboratory",
                TransferOption.PREVIEW,
                str(tmp_path),
                "--publish",
                str(tmp_path),
            ]
        )
    assert stopped.value.code == 2


def test_the_run_uses_its_recording_name_and_live_announcement_file(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    called = []
    monkeypatch.setattr(
        command, "run_transfer", lambda *args, **kwargs: called.append((args, kwargs))
    )
    announcement = str(tmp_path / "live-url.json")
    command.main(
        [
            TransferOption.BUNDLE,
            "/laboratory",
            TransferOption.RECORDING,
            "pr2_transfer_2",
            TransferOption.LIVE_URL_FILE,
            announcement,
            "--port",
            "0",
        ]
    )
    assert called == [
        (
            ("/laboratory", ["--port", "0"]),
            {"recording": "pr2_transfer_2", "live_url_file": announcement},
        )
    ]


def test_transfer_boundary_passes_run_options_to_the_native_demo(monkeypatch, tmp_path):
    supplied = []
    result = SavedScene(scene="transfer_2")

    def at_the_bench(bundle, **fields):
        supplied.append((bundle, fields))
        return "native demo"

    def task_command(demo):
        assert demo == "native demo"
        return SimpleNamespace(main=lambda arguments: result)

    monkeypatch.setitem(
        sys.modules,
        "cramera_bridge.laboratory.transfer",
        SimpleNamespace(VesselTransferDemo=SimpleNamespace(at_the_bench=at_the_bench)),
    )
    monkeypatch.setitem(
        sys.modules,
        "cramera_bridge.robot_task",
        SimpleNamespace(TaskCommand=task_command),
    )
    announcement = tmp_path / "live-url.json"
    assert (
        command.run_transfer("/lab", ["--port", "0"], "transfer_2", str(announcement))
        is result
    )
    assert supplied == [
        (Path("/lab"), {"name": "transfer_2", "live_url_file": announcement})
    ]


# %% demos


def test_the_command_runs_the_demo_it_is_given(monkeypatch, tmp_path):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    called = []
    monkeypatch.setattr(
        command, "run_transfer", lambda *arguments: called.append(("transfer",))
    )
    monkeypatch.setattr(
        command, "run_workflow", lambda *arguments: called.append(arguments)
    )
    command.main(
        [
            TransferOption.BUNDLE,
            str(tmp_path),
            TransferOption.DEMO,
            LaboratoryDemo.WORKFLOW,
            "--port",
            "0",
        ]
    )
    assert called == [(str(tmp_path), ["--port", "0"])]


def test_an_unknown_demo_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(command, "missing_libraries", lambda: [])
    with pytest.raises(SystemExit) as stopped:
        command.main(
            [TransferOption.BUNDLE, str(tmp_path), TransferOption.DEMO, "juggling"]
        )
    assert stopped.value.code == 2


def test_workflow_boundary_passes_run_options_to_the_native_demo(monkeypatch, tmp_path):
    supplied = []
    result = SavedScene(scene="workflow_2")

    def at_the_bench(bundle, **fields):
        supplied.append((bundle, fields))
        return "native demo"

    def task_command(demo):
        assert demo == "native demo"
        return SimpleNamespace(main=lambda arguments: result)

    monkeypatch.setitem(
        sys.modules,
        "cramera_bridge.laboratory.workflow",
        SimpleNamespace(
            LaboratoryWorkflowDemo=SimpleNamespace(at_the_bench=at_the_bench)
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "cramera_bridge.robot_task",
        SimpleNamespace(TaskCommand=task_command),
    )
    announcement = tmp_path / "live-url.json"
    assert (
        command.run_workflow("/lab", ["--port", "0"], "workflow_2", str(announcement))
        is result
    )
    assert supplied == [
        (Path("/lab"), {"name": "workflow_2", "live_url_file": announcement})
    ]
