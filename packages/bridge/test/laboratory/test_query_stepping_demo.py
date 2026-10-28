"""
The PR2's vessel transfer run with its queries stepped, as its command runs it.
"""

from __future__ import annotations

from cramera_bridge.demos.query_stepping import NAME, TASK, main
from cramera_bridge.documents import DocumentFile
from cramera_bridge.robot_task import TaskArgument
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.laboratory.runs import TransferOption
from cramera_protocol.query_steps import QuerySteps, StepPhase
from cramera_protocol.viewer import EnvironmentVariable


def test_the_transfer_steps_through_its_robot_handles_and_vessel(
    laboratory_bundle, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(EnvironmentVariable.DATA, str(tmp_path / "data"))
    main(
        [
            TransferOption.BUNDLE,
            str(laboratory_bundle),
            TaskArgument.PORT,
            "0",
            TaskArgument.NO_HOLD,
        ]
    )
    bundle = tmp_path / "data" / "scenes" / NAME
    scene = DocumentFile(bundle / BundleFile.SCENE).read(SceneDescription)
    steps = DocumentFile(bundle / scene.query_steps).read(QuerySteps).steps
    assert scene.task == TASK
    assert [step.caller.function for step in steps] == [
        "VesselTaskDemo.the_robot",
        "VesselTransferDemo.the_handles",
        "VesselTransferDemo.the_vessel",
    ]
    assert {step.phase for step in steps} == {StepPhase.SETUP}
    assert steps[2].answers == ["tube_clear"]
    assert capsys.readouterr().out.strip() == f"asked 3 queries; saved {NAME}"
