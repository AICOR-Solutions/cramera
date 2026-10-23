"""
Replacing the viewer that already holds the port.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys

import pytest

from cramera.command_line import Option, ViewerConfiguration
from cramera.occupant import PortOccupant, PortStillInUse, is_viewer_command
from cramera_protocol.viewer import EnvironmentVariable

HOST = "127.0.0.1"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


@pytest.fixture
def viewer_process(tmp_path):
    port = free_port()
    environment = {**os.environ, EnvironmentVariable.DATA: str(tmp_path)}
    environment.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "cramera.command_line",
            Option.PORT,
            str(port),
            Option.NO_BROWSER,
        ],
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    while "cramera serves" not in process.stderr.readline():
        pass
    yield process, port
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=20)


def test_the_listening_process_is_found_through_proc():
    with socket.socket() as listening:
        listening.bind((HOST, 0))
        listening.listen()
        occupant = PortOccupant(HOST, listening.getsockname()[1])
        assert occupant.pid() == os.getpid()
        assert not occupant.is_free()
        assert not occupant.is_viewer()
    assert occupant.pid() is None
    assert occupant.is_free()


def test_the_viewer_commands_are_recognised():
    assert is_viewer_command(["/env/bin/cramera", "--demo-scenes", "demo"])
    assert is_viewer_command(["/env/bin/python3", "/env/bin/cramera", "--port", "1"])
    assert is_viewer_command(["python", "-m", "cramera.command_line"])
    assert not is_viewer_command(["python", "-m", "http.server", "8711"])
    assert not is_viewer_command(["nginx"])
    assert not is_viewer_command([])


def test_a_viewer_is_also_known_by_its_command_line(viewer_process):
    process, port = viewer_process
    occupant = PortOccupant(HOST, port)
    assert occupant.is_viewer_process(process.pid)
    assert not occupant.is_viewer_process(os.getpid()) or "cramera" in sys.argv[0]
    assert not occupant.is_viewer_process(1)


def test_a_socket_that_is_not_a_viewer_is_not_replaced():
    with socket.socket() as listening:
        listening.bind((HOST, 0))
        listening.listen()
        occupant = PortOccupant(HOST, listening.getsockname()[1])
        with pytest.raises(PortStillInUse) as raised:
            occupant.replace_viewer()
        assert raised.value.pid == os.getpid()


def test_a_viewer_on_the_port_is_stopped_and_the_port_freed(viewer_process):
    process, port = viewer_process
    occupant = PortOccupant(HOST, port)
    assert occupant.is_viewer()
    assert occupant.replace_viewer() == process.pid
    assert process.wait(timeout=20) == 0
    assert occupant.is_free()


def test_the_configuration_replaces_the_viewer_on_its_port(viewer_process, locations):
    process, port = viewer_process
    configuration = ViewerConfiguration(
        locations=locations, port=port, open_browser=False
    )
    server = configuration.start_server()
    try:
        assert server.bound_port() == port
        assert process.wait(timeout=20) == 0
    finally:
        server.stop()


def test_the_viewer_on_the_port_is_kept_when_asked(viewer_process, locations):
    process, port = viewer_process
    configuration = ViewerConfiguration(
        locations=locations, port=port, open_browser=False, replace_viewer=False
    )
    with pytest.raises(OSError):
        configuration.start_server()
    assert process.poll() is None
