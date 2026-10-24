"""
The whole stack as a person runs it: the viewer with every plugin, the plan builder's
demos, ``cramera-live`` and coraplex's own demos, against the CRAM workspace and ROS 2.

The scenarios need what ``scripts/install_stack.py`` installs and a sourced ROS 2; they
are skipped where either is missing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import pytest
from typing_extensions import Any, Dict, Iterator, List, Optional

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.viewer import EnvironmentVariable, ViewerRoute

STACK_MODULES = ("coraplex", "cramera_bridge", "cramera_plan_builder", "rclpy")
"""
The modules the scenarios need: the CRAM workspace, the bridge, the plan builder and ROS
2's Python client.
"""

LOCALHOST = "127.0.0.1"
"""
Where the scenarios' servers listen.
"""

STARTUP_TIMEOUT = 120.0
"""
How long a server may take to answer, in seconds.
"""

REQUEST_TIMEOUT = 120.0
"""
How long one request may take, in seconds; a plan builder catalog reads the whole
workspace.
"""

POLL_INTERVAL = 1.0
"""
How often a scenario looks at what a server reports, in seconds.
"""

STOP_TIMEOUT = 60.0
"""
How long a server is given to end once asked to, in seconds.
"""

if not all(importlib.util.find_spec(module) for module in STACK_MODULES):
    pytest.skip(
        "the end-to-end scenarios need the whole stack (scripts/install_stack.py) and "
        "a sourced ROS 2",
        allow_module_level=True,
    )

# %% the CRAM workspace


@dataclass(frozen=True)
class CoraplexResources:
    """
    The worlds, objects and demos of the installed coraplex.
    """

    root: Path
    """
    The coraplex directory of the CRAM workspace, which holds ``resources`` and
    ``demos``.
    """

    @classmethod
    def installed(cls) -> CoraplexResources:
        """
        :return: The resources of the coraplex that is imported.
        """
        import coraplex

        return cls(Path(coraplex.__file__).resolve().parents[2])

    def world(self, name: str) -> Path:
        """
        :param name: A world's file name, such as ``apartment.urdf``.
        :return: The world's URDF.
        """
        return self.root / "resources" / "worlds" / name

    def demo(self, name: str) -> Path:
        """
        :param name: A demo's directory, such as ``coraplex_bullet_world_demo``.
        :return: The demo's script.
        """
        return self.root / "demos" / name / "demo.py"


@pytest.fixture(scope="session")
def coraplex_resources() -> CoraplexResources:
    """
    :return: The worlds, objects and demos of the installed coraplex.
    """
    return CoraplexResources.installed()


# %% HTTP


@dataclass(frozen=True)
class JsonClient:
    """
    Reads and posts JSON documents at one server.
    """

    base: str
    """
    The server's address, such as ``http://127.0.0.1:8791``.
    """

    def get(self, route: str) -> Any:
        """
        :param route: A route below the address.
        :return: The decoded answer.
        """
        with urllib.request.urlopen(
            self.base + route, timeout=REQUEST_TIMEOUT
        ) as answer:
            return json.loads(answer.read())

    def post(self, route: str, body: Any = None) -> Any:
        """
        :param route: A route below the address.
        :param body: The JSON body; an empty document when None.
        :return: The decoded answer.
        :raises AssertionError: When the server refuses the request, with its reason.
        """
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps({} if body is None else body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as answer:
                return json.loads(answer.read())
        except urllib.error.HTTPError as error:
            raise AssertionError(
                f"POST {route} answered {error.code}: {error.read().decode()}"
            ) from error

    def status_of(self, route: str) -> int:
        """
        :param route: A route below the address.
        :return: The HTTP status the server answers a GET of it with.
        """
        try:
            with urllib.request.urlopen(
                self.base + route, timeout=REQUEST_TIMEOUT
            ) as answer:
                return answer.status
        except urllib.error.HTTPError as error:
            return error.code

    def wait_until_answering(self, route: str, process: subprocess.Popen) -> None:
        """
        :param route: A route the server answers once it is up.
        :param process: The server's process.
        :raises AssertionError: When the process ends or does not answer in time.
        """
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            assert process.poll() is None, f"the server ended with {process.returncode}"
            try:
                self.get(route)
                return
            except (urllib.error.URLError, ConnectionError):
                threading.Event().wait(POLL_INTERVAL)
        raise AssertionError(f"{self.base}{route} did not answer in time")


def free_port() -> int:
    """
    :return: A port nothing listens on now.
    """
    with socket.socket() as probe:
        probe.bind((LOCALHOST, 0))
        return probe.getsockname()[1]


# %% servers


@dataclass
class ServerProcess:
    """
    A command of the stack running as its own process group, with its output in a log.
    """

    command: List[str]
    """
    The command.
    """

    environment: Dict[str, str]
    """
    The command's environment.
    """

    log: Path
    """
    Where its output goes.
    """

    process: Optional[subprocess.Popen] = field(default=None, init=False)
    """
    The process, while started.
    """

    def start(self) -> ServerProcess:
        """
        :return: This server, started.
        """
        with self.log.open("wb") as output:
            self.process = subprocess.Popen(
                self.command,
                env=self.environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return self

    def stop(self) -> None:
        """
        Interrupt the process group, as Ctrl-C does, and kill it if it does not end.
        """
        if self.process is None or self.process.poll() is not None:
            return
        os.killpg(self.process.pid, signal.SIGINT)
        try:
            self.process.wait(STOP_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(STOP_TIMEOUT)

    def output(self) -> str:
        """
        :return: What the process wrote so far.
        """
        return self.log.read_text(errors="replace")


@dataclass
class Viewer:
    """
    The ``cramera`` viewer with every installed plugin, on a data directory and a scenes
    directory of the scenario's own.
    """

    data: Path
    """
    The viewer's data directory, whose ``scenes`` recordings are saved into.
    """

    scenes: Optional[Path]
    """
    The shared scenes directory, which holds the environments the builder offers, if
    any.
    """

    server: ServerProcess
    """
    The viewer's process.
    """

    client: JsonClient
    """
    Reads the viewer's routes.
    """

    def scene_names(self) -> List[str]:
        """
        :return: The names of every scene the viewer lists.
        """
        return [
            entry.name
            for entry in SceneIndex.from_json(
                self.client.get(ViewerRoute.SCENES)
            ).scenes
        ]


def stack_environment(data: Path, scenes: Optional[Path] = None) -> Dict[str, str]:
    """
    :param data: The data directory recordings are saved into.
    :param scenes: The shared scenes directory, if any.
    :return: The scenario's environment for a command of the stack.
    """
    environment = dict(os.environ, **{EnvironmentVariable.DATA: str(data)})
    if scenes is not None:
        environment[EnvironmentVariable.SCENES] = str(scenes)
    return environment


def start_viewer(work: Path, data: Path, scenes: Optional[Path] = None) -> Viewer:
    """
    :param work: A directory for the viewer's log.
    :param data: The viewer's data directory.
    :param scenes: The shared scenes directory, if any.
    :return: The viewer, answering.
    """
    port = free_port()
    server = ServerProcess(
        [
            shutil.which("cramera"),
            "--port",
            str(port),
            "--no-browser",
            "--keep-running",
        ],
        stack_environment(data, scenes),
        work / "viewer.log",
    ).start()
    client = JsonClient(f"http://{LOCALHOST}:{port}")
    try:
        client.wait_until_answering(ViewerRoute.INFO, server.process)
    except AssertionError:
        server.stop()
        raise
    return Viewer(data=data, scenes=scenes, server=server, client=client)


# %% replaying a saved scene


MESH_REFERENCE = re.compile(r'filename="([^"]+)"')
"""
Finds the files a URDF's meshes are read from.
"""


@dataclass(frozen=True)
class SceneReplay:
    """
    A saved scene as the viewer serves it for replaying: its description and every file
    the browser loads to show it.
    """

    viewer: Viewer
    """
    The viewer serving the scene.
    """

    name: str
    """
    The scene's name.
    """

    def route(self, file: str) -> str:
        """
        :param file: A file of the scene, relative to its bundle.
        :return: The route the viewer serves it at.
        """
        return f"{ViewerRoute.SCENE_FILES}{self.name}/{file}"

    def description(self) -> SceneDescription:
        """
        :return: The scene's description.
        """
        return SceneDescription.from_json(
            self.viewer.client.get(self.route(BundleFile.SCENE))
        )

    def trajectory(self) -> Trajectory:
        """
        :return: The scene's recorded frames.
        """
        return Trajectory.from_json(
            self.viewer.client.get(self.route(self.description().trajectory))
        )

    def files(self) -> List[str]:
        """
        :return: Every file the browser loads to replay the scene: the trajectory and
            statecharts, every model's URDF and the meshes it references, and every
            object's mesh.
        """
        description = self.description()
        files = [description.trajectory] + (
            [description.statecharts] if description.statecharts else []
        )
        for model in description.models:
            files.append(model.urdf)
            urdf = (self.viewer.data / "scenes" / self.name / model.urdf).read_text()
            files.extend(MESH_REFERENCE.findall(urdf))
        files.extend(entry.mesh for entry in description.objects if entry.mesh)
        return sorted(set(files))

    def unserved_files(self) -> List[str]:
        """
        :return: The files of :meth:`files` the viewer does not serve.
        """
        return [
            file
            for file in self.files()
            if self.viewer.client.status_of(self.route(file)) != HTTPStatus.OK
        ]
