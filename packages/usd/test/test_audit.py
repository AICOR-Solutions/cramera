"""
``cramera-audit-robots``: the separation of robots and environment in a composed twin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cramera_usd.audit.report import AuditCheckName, AuditDetail, AuditReport
from cramera_usd.bundle.json_file import JsonFile
from cramera_usd.commands.audit_robots import AuditCommand, AuditExit, AuditOption
from cramera_usd.exceptions import StageNotFound, StageUnreadable

from .dataset.stages import Stage

# %% twins

TWIN = "twin/workshop.usda"
"""
A twin whose root layer composes a robots layer and an environment layer.
"""

EMPTY_ROBOT = "twin/empty_robot.usda"
"""
A twin whose one robot lies outside the robots scope and has no geometry.
"""

# %% helpers


def run(stage: Path, tmp_path: Path, *options: str) -> tuple:
    """
    :param stage: A twin's root layer.
    :param tmp_path: A directory for the report.
    :param options: Further command line options.
    :return: The exit code and the written report.
    """
    report = tmp_path / "separation.json"
    command = AuditCommand.from_arguments(
        [str(stage), AuditOption.JSON, str(report), *options]
    )
    exit_code = command.run()
    return exit_code, AuditReport.from_json(JsonFile(report).read())


def failed(report: AuditReport) -> list:
    """
    :param report: An audit report.
    :return: The checks that failed.
    """
    return [line.check for line in report.lines if not line.passed]


# %% checks


def test_a_twin_composed_of_its_two_layers_passes(dataset, tmp_path):
    exit_code, report = run(dataset / TWIN, tmp_path)
    assert exit_code is AuditExit.PASSED
    assert [line.check for line in report.lines] == list(AuditCheckName)
    assert (report.passed, report.total) == (len(AuditCheckName), len(AuditCheckName))
    assert report.robots == ["/World/Robots/Arm"]


def test_a_single_layer_twin_fails_the_layer_checks(tmp_path):
    exit_code, report = run(Stage.ROBOT_MARKERS.path, tmp_path)
    assert exit_code is AuditExit.FAILED
    assert failed(report) == [
        AuditCheckName.LAYERS_COMPOSED,
        AuditCheckName.SCOPE_HOLDS_ROBOTS_ONLY,
        AuditCheckName.ROBOTS_TYPED,
        AuditCheckName.ENVIRONMENT_WITHOUT_ROBOTS,
        AuditCheckName.ROBOTS_LAYER_CONFINED,
        AuditCheckName.NO_JOINT_TO_ROBOTS,
    ]


def test_the_report_names_what_a_check_found(tmp_path):
    _, report = run(Stage.ROBOT_MARKERS.path, tmp_path)
    lines = {line.check: line for line in report.lines}
    assert lines[AuditCheckName.SCOPE_HOLDS_ROBOTS_ONLY].details[
        AuditDetail.FOREIGN
    ] == ["/World/Robots/Pedestal"]
    assert lines[AuditCheckName.NO_JOINT_TO_ROBOTS].details[AuditDetail.CROSSING] == [
        "/World/Joints/Tow",
        "/World/Joints/Dock",
        "/World/Joints/Grip",
    ]


def test_a_twin_without_robots_skips_the_layer_checks(tmp_path):
    exit_code, report = run(Stage.JOINTED_CABINET.path, tmp_path, AuditOption.NO_ROBOTS)
    assert exit_code is AuditExit.PASSED
    assert {line.check for line in report.lines}.isdisjoint(
        {
            AuditCheckName.LAYERS_COMPOSED,
            AuditCheckName.ENVIRONMENT_WITHOUT_ROBOTS,
            AuditCheckName.ROBOTS_LAYER_CONFINED,
        }
    )


def test_a_twin_declared_without_robots_must_mark_none(tmp_path):
    _, report = run(Stage.ROBOT_MARKERS.path, tmp_path, AuditOption.NO_ROBOTS)
    assert AuditCheckName.MARKED_ROBOTS in failed(report)


def test_a_robot_outside_its_scope_without_geometry_fails(dataset, tmp_path):
    _, report = run(dataset / EMPTY_ROBOT, tmp_path)
    assert {
        AuditCheckName.ROBOTS_IN_SCOPE,
        AuditCheckName.ROBOTS_HAVE_GEOMETRY,
    } <= set(failed(report))


# %% output


def test_every_outcome_is_printed(dataset, tmp_path, capsys):
    run(dataset / TWIN, tmp_path)
    printed = capsys.readouterr().out
    assert all(check.value in printed for check in AuditCheckName)


# %% refusals


def test_a_missing_stage_is_refused(dataset):
    with pytest.raises(StageNotFound):
        AuditCommand.from_arguments([str(dataset / "missing.usda")]).run()


def test_a_file_that_is_no_stage_is_refused(dataset):
    with pytest.raises(StageUnreadable):
        AuditCommand.from_arguments([str(dataset / "two_joint_arm_record.json")]).run()
