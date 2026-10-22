"""
``cramera-export``: conversion into a staging directory, the gate, and publication by
rename.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cramera_protocol.bundle.files import BundleFile, ScenesDirectoryFile
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.bundle.scene import SceneDescription
from cramera_usd.bundle.index import NO_ROBOT
from cramera_usd.bundle.json_file import JsonFile
from cramera_usd.commands.export_scene import (
    ExportCommand,
    ExportExit,
    ExportOption,
    ExportParser,
)
from cramera_usd.commands.import_scene import ImportOption, ImportParser
from cramera_usd.exceptions import ViewerNotInstalled
from cramera_usd.export.gate import (
    BenchOnly,
    ExportGate,
    NothingLeftOut,
    ReplayNamesRobot,
    RobotsLeftOut,
)
from cramera_usd.export.import_process import (
    DEFAULT_MEMORY_LIMIT,
    MEMORY_CAP_PROGRAM,
    NO_MEMORY_LIMIT,
    ImportArguments,
    ImportEnvironment,
    ImportProcess,
)
from cramera_usd.export.lens import RenderLens
from cramera_usd.export.screenshot import ViewerScreenshot
from cramera_usd.export.staging import StagingName
from cramera_usd.locations import DefaultDirectory, ScenesLocations
from cramera_protocol.viewer import EnvironmentVariable

from .dataset.exports import ENVIRONMENT_NAME, environment, export
from .dataset.runs import ARM, PHYSICS, RECORD, TRACE
from .dataset.stages import Stage

STAGE_ARGUMENTS = [
    str(Stage.ROBOT_MARKERS.path),
    ImportOption.NAME,
    "cell",
    ImportOption.ENVIRONMENT_NAME,
    ENVIRONMENT_NAME,
]
"""
The arguments every test export starts with.
"""

# %% helpers


def index_of(scenes: Path) -> SceneIndex:
    """
    :param scenes: A scenes directory.
    :return: Its index.
    """
    return SceneIndex.from_json(JsonFile(scenes / ScenesDirectoryFile.INDEX).read())


def staging_directories(scenes: Path) -> list:
    """
    :param scenes: A scenes directory.
    :return: The staging directories left in it.
    """
    return sorted(scenes.glob(f"{StagingName.PREFIX}*"))


# %% options


@pytest.mark.parametrize(
    "option",
    [
        [ImportOption.TRACE, str(TRACE)],
        [ImportOption.ROBOT, ARM],
        [ImportOption.RECORD, str(RECORD)],
        [ImportOption.FRAMES_PER_SECOND, "2"],
        [ImportOption.KEEP_ROBOTS],
    ],
)
def test_replay_options_are_refused_without_a_replay(tmp_path, option, capsys):
    with pytest.raises(SystemExit):
        ExportParser(tmp_path).parse([*STAGE_ARGUMENTS, *option])
    assert option[0] in capsys.readouterr().err
    request = ExportParser(tmp_path).parse(
        [*STAGE_ARGUMENTS, ExportOption.REPLAY, *option]
    )
    assert request.replay


def test_an_export_needs_its_environment_name(tmp_path, capsys):
    with pytest.raises(SystemExit):
        ExportParser(tmp_path).parse(STAGE_ARGUMENTS[:3])
    assert ImportOption.ENVIRONMENT_NAME in capsys.readouterr().err


def test_focal_length_and_field_of_view_are_refused_together(tmp_path):
    with pytest.raises(SystemExit):
        ExportParser(tmp_path).parse(
            [
                *STAGE_ARGUMENTS,
                ExportOption.FOCAL,
                "16",
                ImportOption.CAMERA_FIELD_OF_VIEW,
                "60",
            ]
        )


@pytest.mark.parametrize("focal_length, field_of_view", [(16.0, 70.22), (24.0, 50.23)])
def test_focal_length_of_a_final_render_gives_its_vertical_field_of_view(
    focal_length, field_of_view
):
    assert RenderLens(focal_length).vertical_field_of_view() == field_of_view


def test_focal_length_becomes_the_camera_field_of_view(tmp_path):
    width, height, focal_length = 1280, 800, 16.0
    request = ExportParser(tmp_path).parse(
        [
            *STAGE_ARGUMENTS,
            ExportOption.FOCAL,
            str(focal_length),
            ExportOption.RENDER_SIZE,
            str(width),
            str(height),
        ]
    )
    assert (
        request.options.camera_field_of_view
        == RenderLens(focal_length, width, height).vertical_field_of_view()
    )


def test_import_arguments_reproduce_the_import_options(tmp_path):
    request = ExportParser(tmp_path).parse(
        [
            *STAGE_ARGUMENTS,
            ExportOption.REPLAY,
            ImportOption.PRIM,
            "/World",
            ImportOption.EXCLUDE,
            "/World/Robots/Walker",
            ImportOption.EXPOSURE,
            "1.1",
            ImportOption.CAMERA_POSITION,
            "1",
            "2",
            "3",
            ImportOption.CAMERA_TARGET,
            "0",
            "0",
            "0",
            ImportOption.TRACE,
            str(TRACE),
            ImportOption.FRAMES_PER_SECOND,
            "2",
            ImportOption.ROBOT,
            ARM,
            ImportOption.KEEP_ROBOTS,
            ImportOption.VARIANT,
            PHYSICS.prim_path,
            PHYSICS.variant_set,
            PHYSICS.variant,
            ImportOption.RECORD,
            str(RECORD),
        ]
    )
    staging = tmp_path / "staging"
    arguments = ImportArguments(request.options).to_list(staging)
    reparsed = ImportParser().parser("cramera-import").parse_args(arguments)
    expected = vars(request.options) | {"out": staging}
    assert {key: value for key, value in vars(reparsed).items()} == {
        key: expected[key] for key in vars(reparsed)
    }


def test_the_export_directory_defaults_to_the_shared_scenes(tmp_path):
    shared = tmp_path / "shared"
    assert (
        ScenesLocations(
            {EnvironmentVariable.SCENES: str(shared)}, tmp_path
        ).export_directory()
        == shared
    )
    assert (
        ScenesLocations({}, tmp_path).export_directory()
        == tmp_path / DefaultDirectory.SHARED_SCENES
    )


def test_the_import_directory_defaults_to_the_local_scenes(tmp_path):
    data = tmp_path / "data"
    assert (
        ScenesLocations(
            {EnvironmentVariable.DATA: str(data)}, tmp_path
        ).import_directory()
        == data / DefaultDirectory.SCENES
    )
    assert ScenesLocations({}, tmp_path).import_directory() == (
        tmp_path / DefaultDirectory.DATA / DefaultDirectory.SCENES
    )


# %% conversion process


def test_the_conversion_runs_without_a_cap_when_switched_off():
    command = ImportProcess({ImportEnvironment.MEMORY_LIMIT: NO_MEMORY_LIMIT}).command(
        ["stage.usda"]
    )
    assert MEMORY_CAP_PROGRAM not in command


def test_the_conversion_is_capped_where_systemd_runs(monkeypatch):
    monkeypatch.setattr(
        "cramera_usd.export.import_process.shutil.which", lambda program: program
    )
    command = ImportProcess({}).command(["stage.usda"])
    assert command[0] == MEMORY_CAP_PROGRAM
    assert any(DEFAULT_MEMORY_LIMIT in part for part in command)


# %% gate


def test_an_environment_gate_proves_the_robots_are_out():
    checks = ExportGate.of_export(ENVIRONMENT_NAME, False, False, []).checks
    assert any(isinstance(check, RobotsLeftOut) for check in checks)
    assert any(isinstance(check, BenchOnly) for check in checks)


def test_a_gate_of_a_twin_without_robots_wants_nothing_left_out():
    checks = ExportGate.of_export(ENVIRONMENT_NAME, False, True, []).checks
    assert any(isinstance(check, NothingLeftOut) for check in checks)


def test_a_replay_gate_wants_the_robot_named():
    checks = ExportGate.of_export(ENVIRONMENT_NAME, True, False, []).checks
    assert any(isinstance(check, ReplayNamesRobot) for check in checks)
    assert not any(isinstance(check, RobotsLeftOut) for check in checks)


# %% exports


def test_an_environment_without_its_robots_is_published(tmp_path):
    assert export(Stage.ROBOT_MARKERS, tmp_path, "cell") is ExportExit.PUBLISHED
    entry = index_of(tmp_path).entry("cell")
    assert (entry.robot, entry.environment) == (NO_ROBOT, ENVIRONMENT_NAME)
    assert (tmp_path / "cell" / BundleFile.SCENE).is_file()
    assert staging_directories(tmp_path) == []


def test_a_newer_export_replaces_the_published_bundle(tmp_path):
    export(Stage.ROBOT_MARKERS, tmp_path, "cell")
    task = "second export"
    assert (
        export(Stage.ROBOT_MARKERS, tmp_path, "cell", ImportOption.TASK, task)
        is ExportExit.PUBLISHED
    )
    scene = SceneDescription.from_json(
        JsonFile(tmp_path / "cell" / BundleFile.SCENE).read()
    )
    assert scene.task == task
    assert staging_directories(tmp_path) == []


def test_an_export_that_left_nothing_out_is_not_published(tmp_path, capsys):
    exit_code = export(Stage.JOINTED_CABINET, tmp_path, "cabinet")
    assert exit_code is ExportExit.REJECTED
    assert not (tmp_path / "cabinet").exists()
    assert not (tmp_path / ScenesDirectoryFile.INDEX).exists()
    (staging,) = staging_directories(tmp_path)
    assert (staging / "cabinet" / BundleFile.SCENE).is_file()


def test_a_twin_declared_without_robots_is_published(tmp_path):
    exit_code = export(
        Stage.JOINTED_CABINET, tmp_path, "cabinet", ExportOption.NO_ROBOTS
    )
    assert exit_code is ExportExit.PUBLISHED


def test_a_robot_part_beside_the_marked_robot_fails_the_gate(tmp_path, capsys):
    assert export(Stage.DETACHED_GRIPPER, tmp_path, "gripper") is ExportExit.REJECTED
    printed = capsys.readouterr().out
    assert "/World/Robots/RoverGripper/Palm" in printed


def test_an_exclusion_is_reported_before_publishing(tmp_path):
    exit_code = export(
        Stage.ROBOT_MARKERS, tmp_path, "cell", ImportOption.EXCLUDE, "/World/Robots"
    )
    assert exit_code is ExportExit.PUBLISHED


def test_a_failed_import_publishes_nothing_and_leaves_no_staging(tmp_path, dataset):
    request = ExportParser(tmp_path).parse(
        [
            str(dataset / "missing.usda"),
            ImportOption.NAME,
            "missing",
            ImportOption.ENVIRONMENT_NAME,
            ENVIRONMENT_NAME,
        ]
    )
    assert ExportCommand(request, environment()).run() is ExportExit.REJECTED
    assert list(tmp_path.iterdir()) == []


def test_a_replay_keeps_its_robot_and_is_published(tmp_path):
    exit_code = export(
        Stage.TWO_JOINT_ARM,
        tmp_path,
        "arm_run",
        ExportOption.REPLAY,
        ImportOption.VARIANT,
        PHYSICS.prim_path,
        PHYSICS.variant_set,
        PHYSICS.variant,
        ImportOption.TRACE,
        str(TRACE),
        ImportOption.ROBOT,
        ARM,
        ImportOption.FRAMES_PER_SECOND,
        "2",
    )
    assert exit_code is ExportExit.PUBLISHED
    assert index_of(tmp_path).entry("arm_run").robot != NO_ROBOT


def test_a_screenshot_without_the_viewer_is_refused_before_converting(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(ViewerScreenshot, "available", lambda self: False)
    with pytest.raises(ViewerNotInstalled):
        export(
            Stage.ROBOT_MARKERS,
            tmp_path,
            "cell",
            ExportOption.SHOT,
            str(tmp_path / "shot.png"),
        )
    assert list(tmp_path.iterdir()) == []
