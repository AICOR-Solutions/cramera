"""
Serving from a process without network routes: the namespace command, and the viewer's
server answering on an inherited socket.
"""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.request
from http import HTTPStatus

import pytest

from cramera.http.messages import Header
from cramera_offline.exceptions import NetworkIsolationUnavailable
from cramera_offline.isolation import (
    InheritedSocketServer,
    IsolationCommand,
    NetworkNamespace,
)
from cramera_offline.presentation_command import LOOPBACK
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ViewerInfo, ViewerRoute

# %% namespace


class ProcessRecorder:
    """
    Records the commands it is asked to run and start, and answers the probe with a
    fixed exit code.
    """

    def __init__(self, probe_exit_code: int, probe_error: str = ""):
        self.probe_exit_code = probe_exit_code
        self.probe_error = probe_error
        self.run_commands = []
        self.started = []

    def run(self, command, **options):
        self.run_commands.append(command)
        return subprocess.CompletedProcess(
            command, self.probe_exit_code, stdout="", stderr=self.probe_error
        )

    def start(self, command, **options):
        self.started.append((command, options))
        return command


def test_the_program_runs_in_new_user_and_network_namespaces():
    recorder = ProcessRecorder(probe_exit_code=0)
    namespace = NetworkNamespace(run=recorder.run, start=recorder.start)
    with socket.create_server((LOOPBACK, 0)) as listener:
        namespace.launch(["serve"], listener)
        command, options = recorder.started[0]
        assert command == [*namespace.prefix(), "serve", str(listener.fileno())]
        assert options["pass_fds"] == (listener.fileno(),)
    assert IsolationCommand.NETWORK in namespace.prefix()
    assert recorder.run_commands == [[*namespace.prefix(), IsolationCommand.PROBE]]


def test_a_system_without_namespaces_is_reported_before_starting():
    reason = "unshare: write failed /proc/self/uid_map: Operation not permitted"
    recorder = ProcessRecorder(probe_exit_code=1, probe_error=reason)
    namespace = NetworkNamespace(run=recorder.run, start=recorder.start)
    with socket.create_server((LOOPBACK, 0)) as listener:
        with pytest.raises(NetworkIsolationUnavailable) as refused:
            namespace.launch(["serve"], listener)
    assert refused.value.reason == reason
    assert recorder.started == []


# %% inherited socket


def test_the_server_answers_on_an_inherited_socket(answerer):
    with socket.create_server((LOOPBACK, 0)) as listener:
        descriptor = listener.detach()
        with InheritedSocketServer(answerer=answerer, descriptor=descriptor) as server:
            request = urllib.request.Request(
                f"{server.url()}{ViewerRoute.INFO}",
                headers={Header.HOST: f"{LOOPBACK}:{server.port}"},
            )
            with urllib.request.urlopen(request) as response:
                assert response.status == HTTPStatus.OK
                info = ViewerInfo.from_json(json.loads(response.read()))
    assert [plugin.name for plugin in info.plugins] == [PluginName.OFFLINE]
