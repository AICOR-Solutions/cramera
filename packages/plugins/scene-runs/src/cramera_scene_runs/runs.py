"""
The runs the viewer offers, started one at a time as processes of their own, stopped
with their whole process group, and told by how they ended.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from typing_extensions import Callable, Optional

from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.scene_runs import (
    SceneRun,
    SceneRunCatalog,
    SceneRunPlaceholder,
    SceneRunsState,
    SceneRunState,
    SceneRunStatus,
)
from cramera_scene_runs.exceptions import (
    InvalidSceneRunCatalog,
    SceneRunBusy,
    SceneRunNotStarted,
    UnknownSceneRun,
)

IDENTIFIER_PATTERN = r"[a-z0-9_]{1,48}"
"""
A run's identifier, short enough that it names a bundle with the time of a start.
"""

RECORDING_TIME = "%Y%m%d_%H%M%S"
"""
How a recording's name says when its run started.
"""

LOG_TAIL = 4000
"""
How many of the newest bytes of a run's output its status shows.
"""

STOP_TIMEOUT = 10.0
"""
How long a run may take to end after it was asked to, in seconds.
"""

STOP_POLL_INTERVAL = 0.05
"""
How often a stopping run is checked, in seconds.
"""

# %% catalog file


@dataclass(frozen=True)
class SceneRunCatalogFile:
    """
    The server's file of the runs the viewer offers.
    """

    path: Path
    """
    The JSON file.
    """

    def read(self) -> SceneRunCatalog:
        """
        Reading the file is where a catalog the viewer cannot offer becomes its error.

        :return: The runs it names.
        :raises InvalidSceneRunCatalog: When the file cannot be read, is no catalog, or
            names a run without a command or with an identifier that is not unique or
            not lowercase letters, digits and ``_``.
        """
        try:
            catalog = SceneRunCatalog.from_json(
                json.loads(self.path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, ProtocolError) as error:
            raise InvalidSceneRunCatalog(self.path, str(error)) from error
        identifiers = [run.identifier for run in catalog.runs]
        for run in catalog.runs:
            if re.fullmatch(IDENTIFIER_PATTERN, run.identifier) is None:
                raise InvalidSceneRunCatalog(
                    self.path, f"{run.identifier!r} is no identifier"
                )
            if identifiers.count(run.identifier) > 1:
                raise InvalidSceneRunCatalog(
                    self.path, f"{run.identifier!r} names two runs"
                )
            if not run.command:
                raise InvalidSceneRunCatalog(
                    self.path, f"{run.identifier!r} has no command"
                )
        return catalog


# %% process


@dataclass
class RunProcess:
    """
    One started run: its process, the name it records under and its output.
    """

    run: SceneRun
    """
    The run.
    """

    recording: str
    """
    The name the run saves its recording under.
    """

    process: subprocess.Popen
    """
    The run's process, which leads a process group of its own.
    """

    log: Path
    """
    The file receiving the run's output.
    """

    stopped: bool = False
    """
    Whether the run was stopped rather than ending on its own.
    """

    @classmethod
    def start(cls, run: SceneRun, recording: str, log: Path) -> RunProcess:
        """
        :param run: An offered run.
        :param recording: The name it saves its recording under.
        :param log: The file receiving its output.
        :return: The started run.
        :raises SceneRunNotStarted: When the operating system cannot start it.
        """
        command = [
            argument.replace(SceneRunPlaceholder.RECORDING, recording)
            for argument in run.command
        ]
        log.parent.mkdir(parents=True, exist_ok=True)
        # the boundary to the operating system, where a refused start becomes an answer
        try:
            with log.open("wb") as output:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as error:
            raise SceneRunNotStarted(run.identifier, str(error)) from error
        return cls(run=run, recording=recording, process=process, log=log)

    def runs(self) -> bool:
        """
        :return: Whether the run's process has not ended.
        """
        return self.process.poll() is None

    def status(self, recorded: Callable[[str], bool]) -> SceneRunStatus:
        """
        :param recorded: Whether a bundle of a name exists.
        :return: How far the run is, with the end of its output.
        """
        return SceneRunStatus(
            identifier=self.run.identifier,
            state=self.state(recorded),
            recording=self.recording,
            log=self.output(),
        )

    def state(self, recorded: Callable[[str], bool]) -> SceneRunState:
        """
        :param recorded: Whether a bundle of a name exists.
        :return: Whether the run runs, was stopped, recorded or failed.
        """
        if self.runs():
            return SceneRunState.RUNNING
        if self.stopped:
            return SceneRunState.STOPPED
        if self.process.returncode == 0 and recorded(self.recording):
            return SceneRunState.RECORDED
        return SceneRunState.FAILED

    def output(self) -> str:
        """
        :return: The newest :data:`LOG_TAIL` bytes of the run's output.
        """
        with self.log.open("rb") as output:
            output.seek(max(0, self.log.stat().st_size - LOG_TAIL))
            return output.read().decode("utf-8", errors="replace")

    def stop(self, timeout: float) -> None:
        """
        Ask the run's process group to end and kill it when it does not end in time;
        stopping an ended run changes nothing.

        :param timeout: How long the run may take to end, in seconds.
        """
        if self.runs():
            self.stopped = True
            os.killpg(self.process.pid, signal.SIGTERM)
            deadline = time.monotonic() + timeout
            while self.runs() and time.monotonic() < deadline:
                time.sleep(STOP_POLL_INTERVAL)
            if self.runs():
                os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait()


# %% runner


def now() -> datetime:
    """
    :return: The current time in UTC.
    """
    return datetime.now(timezone.utc)


@dataclass
class SceneRunner:
    """
    Starts the offered runs one at a time and stops them.
    """

    catalog: SceneRunCatalog
    """
    The runs offered.
    """

    logs: Path
    """
    The directory of the runs' output files.
    """

    recorded: Callable[[str], bool]
    """
    Whether a bundle of a name exists, so a run that ended has recorded.
    """

    clock: Callable[[], datetime] = now
    """
    The time a recording's name gives.
    """

    stop_timeout: float = STOP_TIMEOUT
    """
    How long a run may take to end after it was asked to, in seconds.
    """

    current: Optional[RunProcess] = field(default=None, init=False)
    """
    The run started last, running or ended.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Lets one request at a time start, stop or read the runs.
    """

    def state(self) -> SceneRunsState:
        """
        :return: The runs offered and the one started last.
        """
        with self.lock:
            return self.snapshot()

    def start(self, identifier: str) -> SceneRunsState:
        """
        :param identifier: An offered run.
        :return: The state with the run started.
        :raises UnknownSceneRun: When no such run is offered.
        :raises SceneRunBusy: When another run runs.
        :raises SceneRunNotStarted: When the operating system cannot start it.
        """
        with self.lock:
            run = self.offered(identifier)
            if self.current is not None and self.current.runs():
                raise SceneRunBusy(self.current.run.label)
            recording = f"{identifier}_{self.clock().strftime(RECORDING_TIME)}"
            self.current = RunProcess.start(
                run, recording, self.logs / f"{recording}.log"
            )
            return self.snapshot()

    def stop(self) -> SceneRunsState:
        """
        :return: The state with the run started last stopped, if it ran.
        """
        with self.lock:
            if self.current is not None:
                self.current.stop(self.stop_timeout)
            return self.snapshot()

    def close(self) -> None:
        """
        Stop the run that runs, once the viewer stops serving.
        """
        self.stop()

    def offered(self, identifier: str) -> SceneRun:
        """
        :param identifier: A run's identifier.
        :return: The offered run of that identifier.
        :raises UnknownSceneRun: When no such run is offered.
        """
        for run in self.catalog.runs:
            if run.identifier == identifier:
                return run
        raise UnknownSceneRun(identifier)

    def snapshot(self) -> SceneRunsState:
        """
        :return: The runs offered and the one started last; the caller holds
            :attr:`lock`.
        """
        return SceneRunsState(
            runs=[run.choice() for run in self.catalog.runs],
            current=(
                None if self.current is None else self.current.status(self.recorded)
            ),
        )
