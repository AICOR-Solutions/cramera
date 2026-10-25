"""
Robot task demos the laboratory runs on request, each in a process of its own with the
CRAM workspace, so the viewer stays responsive and runs without CRAM itself.

The process is the plugin's own: it is started on request, its output goes to a log file
in the viewer's data directory, and it is ended on request or viewer shutdown.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import List, Optional, Sequence

from cramera.locations import DataLocations
from cramera_protocol.bundle.files import BundleFile
from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_protocol.laboratory.runs import (
    LaboratoryTask,
    TaskRecording,
    TaskRun,
    TaskRunState,
    TransferOption,
)
from cramera_protocol.viewer import EnvironmentVariable

LOG_DIRECTORY = "laboratory"
"""
The folder of the viewer's data directory the demos' logs are written to.
"""

LOG_SUFFIX = ".log"
"""
The suffix of a demo's log file.
"""

ERROR_LINES = 12
"""
How many of the log's last lines a failure reports.
"""

PYTHON_MODULE_FLAG = "-m"
"""
The interpreter's flag that runs a module.
"""

BRIDGE_PACKAGES = ("cramera_bridge",)
"""
The optional package exposing the native transfer through a process boundary.
"""

STOP_TIMEOUT = 3.0
"""
Seconds a child receives to terminate before it is killed on shutdown.
"""

# %% process


@dataclass
class TaskProcess:
    """
    Runs one task demo in its own process and reports how far it is.
    """

    command: List[str]
    """
    The command that runs the demo.
    """

    scene: str
    """
    The bundle the demo saves its recording as.
    """

    locations: DataLocations
    """
    Where the viewer keeps its scenes; the demo saves into the same local scenes.
    """

    packages: Sequence[str] = BRIDGE_PACKAGES
    """
    The packages the demo needs.
    """

    process: Optional[subprocess.Popen] = field(default=None, init=False)
    """
    The demo's process, once started.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    """
    Serializes starting, stopping and reading the process.
    """

    @property
    def log(self) -> Path:
        """
        The demo's log file.
        """
        return self.locations.data / LOG_DIRECTORY / f"{self.scene}{LOG_SUFFIX}"

    def available(self) -> bool:
        """
        :return: Whether every package the demo needs is installed.
        """
        if any(importlib.util.find_spec(package) is None for package in self.packages):
            return False
        if "cramera_bridge" in self.packages:
            if importlib.util.find_spec("cramera_bridge.laboratory") is None:
                return False
            if importlib.util.find_spec(LaboratoryTask.TRANSFER) is None:
                return False
            from cramera_bridge.laboratory.command import missing_libraries

            return not missing_libraries()
        return True

    def recorded(self) -> bool:
        """
        :return: Whether the local scenes hold the demo's recording.
        """
        return (self.locations.local_scenes / self.scene / BundleFile.SCENE).is_file()

    @classmethod
    def of_task(
        cls, task: LaboratoryTask, scene: TaskRecording, locations: DataLocations
    ) -> TaskProcess:
        """
        :param task: A demo of the laboratory.
        :param scene: The bundle it saves its recording as.
        :param locations: Where the viewer keeps its scenes.
        :return: The demo, run as a module of this interpreter.
        """
        return cls(
            command=[
                sys.executable,
                PYTHON_MODULE_FLAG,
                task.value,
                TransferOption.BUNDLE.value,
                str(RESOURCES_DIRECTORY / LaboratoryResource.BENCH),
            ],
            scene=scene.value,
            locations=locations,
        )

    def state(self) -> TaskRun:
        """
        :return: How far the demo is.
        """
        with self.lock:
            return self.state_locked()

    def state_locked(self) -> TaskRun:
        """
        :return: How far the demo is; the caller holds :attr:`lock`.
        """
        if self.process is not None and self.process.poll() is None:
            return TaskRun(state=TaskRunState.RUNNING, scene=self.scene)
        if self.recorded():
            return TaskRun(state=TaskRunState.RECORDED, scene=self.scene)
        if self.process is not None:
            return TaskRun(
                state=TaskRunState.FAILED, scene=self.scene, error=self.last_output()
            )
        if not self.available():
            return TaskRun(state=TaskRunState.UNAVAILABLE, scene=self.scene)
        return TaskRun(state=TaskRunState.IDLE, scene=self.scene)

    def last_output(self) -> str:
        """
        :return: The last lines the demo wrote.
        """
        lines = self.log.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-ERROR_LINES:])

    def start(self) -> TaskRun:
        """
        Run the demo unless it runs, its recording exists or it cannot run here.

        :return: How far the demo is.
        """
        with self.lock:
            current = self.state_locked()
            if current.state not in (TaskRunState.IDLE, TaskRunState.FAILED):
                return current
            self.log.parent.mkdir(parents=True, exist_ok=True)
            environment = {
                **os.environ,
                EnvironmentVariable.DATA.value: str(self.locations.data),
            }
            with self.log.open("w", encoding="utf-8") as output:
                self.process = subprocess.Popen(
                    self.command,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=environment,
                )
            return self.state_locked()

    def stop(self) -> TaskRun:
        """
        End a running demo and wait for it.

        :return: How far the demo is.
        """
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            return self.state_locked()
