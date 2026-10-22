"""
``cramera-offline``: preparing, checking, exporting and serving a presentation.
"""

from __future__ import annotations

import io
import json
import shutil
import socket
import sys
import urllib.request
from http import HTTPStatus

import pytest

from cramera.http.messages import Header
from cramera_offline.exceptions import NetworkIsolationUnavailable, PresentationExists
from cramera_offline.isolation import NetworkNamespace
from cramera_offline.presentation import PresentationPreparation
from cramera_offline.presentation_command import (
    LOOPBACK,
    MODULE_OPTION,
    Action,
    PresentationCommand,
    PresentationExit,
    PresentationOption,
    PresentationOptions,
    main,
)
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.offline import PresentationFile, Storyboard
from cramera_protocol.viewer import ViewerRoute

# %% options


def test_the_options_are_read_from_the_command_line(tmp_path, storyboard_file):
    options = PresentationOptions.from_arguments(
        [
            Action.PREPARE,
            str(tmp_path),
            PresentationOption.STORYBOARD,
            str(storyboard_file),
            PresentationOption.SCENES,
            str(tmp_path / "a"),
            PresentationOption.SCENES,
            str(tmp_path / "b"),
            PresentationOption.NO_BROWSER,
            PresentationOption.ISOLATED,
        ]
    )
    assert options.action is Action.PREPARE
    assert options.scenes == [tmp_path / "a", tmp_path / "b"]
    assert (options.open_browser, options.isolated) == (False, True)


@pytest.mark.parametrize("action", [Action.PREPARE, Action.EXPORT_SITE])
def test_an_action_without_its_input_is_refused(tmp_path, action):
    with pytest.raises(SystemExit):
        PresentationOptions.from_arguments([action, str(tmp_path)])


@pytest.mark.parametrize(
    "arguments, served_here",
    [
        ([Action.SERVE], True),
        ([Action.SERVE, PresentationOption.ISOLATED], False),
        ([Action.CHECK], False),
    ],
)
def test_only_a_server_of_this_process_waits_for_the_stop_signals(
    tmp_path, arguments, served_here
):
    options = PresentationOptions.from_arguments(
        [arguments[0], str(tmp_path), *arguments[1:]]
    )
    assert options.serves_in_this_process() is served_here


# %% actions


@pytest.fixture
def prepared(tmp_path, recorded_scenes, storyboard_file):
    """
    :return: A presentation directory prepared from the complete bundle.
    """
    return (
        PresentationPreparation(
            storyboard_file, [recorded_scenes], tmp_path / "presentation"
        )
        .prepare()
        .path
    )


def test_prepare_writes_and_checks_a_presentation(
    tmp_path, recorded_scenes, storyboard_file
):
    destination = tmp_path / "presentation"
    output = io.StringIO()
    options = PresentationOptions(
        action=Action.PREPARE,
        presentation=destination,
        storyboard=storyboard_file,
        scenes=[recorded_scenes],
    )
    assert PresentationCommand(options, output=output).run() == PresentationExit.DONE
    assert (destination / PresentationFile.STORYBOARD).is_file()
    assert "complete" in output.getvalue()


def test_check_fails_for_an_incomplete_bundle(prepared, broken_bundle):
    storyboard = Storyboard.from_json(
        json.loads((prepared / PresentationFile.STORYBOARD).read_text())
    )
    shutil.rmtree(prepared / storyboard.scene_names()[0])
    shutil.copytree(broken_bundle, prepared / storyboard.scene_names()[0])
    options = PresentationOptions(action=Action.CHECK, presentation=prepared)
    exit_code = PresentationCommand(options, output=io.StringIO()).run()
    assert exit_code == PresentationExit.INCOMPLETE


def test_export_site_writes_the_index_of_the_presented_bundles(tmp_path, prepared):
    site = tmp_path / "site"
    options = PresentationOptions(
        action=Action.EXPORT_SITE, presentation=prepared, output=site
    )
    assert PresentationCommand(options, output=io.StringIO()).run() == (
        PresentationExit.DONE
    )
    index = SceneIndex.from_json(
        json.loads((site / ViewerRoute.SCENES.strip("/")).read_text())
    )
    assert (
        index.default
        == Storyboard.from_json(
            json.loads((prepared / PresentationFile.STORYBOARD).read_text())
        )
        .chapters[0]
        .scene
    )


def test_main_runs_the_requested_action(prepared):
    assert main([Action.CHECK, str(prepared)]) == PresentationExit.DONE


# %% serving


def test_serve_answers_until_asked_to_stop_and_opens_the_page(prepared):
    opened = []
    answered = []

    def ask_while_serving() -> None:
        address = opened[0]
        request = urllib.request.Request(
            f"{address}{ViewerRoute.SCENES.lstrip('/')}",
            headers={Header.HOST: address.split("/")[2]},
        )
        with urllib.request.urlopen(request) as response:
            answered.append(response.status)

    options = PresentationOptions(action=Action.SERVE, presentation=prepared, port=0)
    command = PresentationCommand(
        options,
        output=io.StringIO(),
        wait_for_stop=ask_while_serving,
        open_page=opened.append,
    )
    assert command.run() == PresentationExit.DONE
    assert answered == [HTTPStatus.OK]


class StoppedProcess:
    """
    A process that has already ended when it is waited for.
    """

    def __init__(self):
        self.terminated = False

    def wait(self) -> int:
        return 0

    def terminate(self) -> None:
        self.terminated = True


class LaunchRecorder(NetworkNamespace):
    """
    A namespace that records the launched commands instead of starting them.
    """

    def __init__(self):
        super().__init__()
        self.launched = []

    def launch(self, command, listener):
        self.launched.append((command, listener.getsockname()))
        return StoppedProcess()


def test_isolated_serving_launches_the_server_on_an_inherited_socket(prepared):
    recorder = LaunchRecorder()
    opened = []
    options = PresentationOptions(
        action=Action.SERVE, presentation=prepared, port=0, isolated=True
    )
    command = PresentationCommand(
        options, output=io.StringIO(), namespace=recorder, open_page=opened.append
    )
    assert command.run() == PresentationExit.DONE
    launched, (host, port) = recorder.launched[0]
    assert launched == [
        sys.executable,
        MODULE_OPTION,
        PresentationCommand.__module__,
        Action.SERVE,
        str(prepared.resolve()),
        PresentationOption.NO_BROWSER,
        PresentationOption.LISTEN_DESCRIPTOR,
    ]
    assert opened == [f"http://{host}:{port}/"]


class RefusingNamespace(NetworkNamespace):
    """
    A namespace on a system that does not allow creating one.
    """

    def launch(self, command, listener):
        raise NetworkIsolationUnavailable("no user namespaces")


def test_isolated_serving_without_namespaces_is_refused(prepared):
    namespace = RefusingNamespace()
    options = PresentationOptions(
        action=Action.SERVE, presentation=prepared, port=0, isolated=True
    )
    with pytest.raises(NetworkIsolationUnavailable):
        PresentationCommand(options, output=io.StringIO(), namespace=namespace).run()


# %% refusals


def test_a_refused_action_is_reported_without_a_traceback(
    tmp_path, storyboard_file, recorded_scenes, capsys
):
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "notes.txt").write_text("keep", encoding="utf-8")
    exit_code = main(
        [
            Action.PREPARE,
            str(taken),
            PresentationOption.STORYBOARD,
            str(storyboard_file),
            PresentationOption.SCENES,
            str(recorded_scenes),
        ]
    )
    assert exit_code == PresentationExit.REFUSED
    assert capsys.readouterr().err.strip() == PresentationExists(taken).message()
