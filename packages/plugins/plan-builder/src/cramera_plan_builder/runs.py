"""
Running a generated demo as a child process the plan builder owns: one at a time, its
output kept within a bound, stopped with its whole process group, and ended by the demo
itself when the viewer goes away.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import IO, List, Optional

from cramera_plan_builder.demos import DemoDirectory, DemoOption, DemoTemplate
from cramera_plan_builder.exceptions import DemoNotStarted
from cramera_protocol.plan_builder import (
    DemoDocument,
    RunMode,
    RunState,
    RunStatus,
)

READ_SIZE = 4096
"""
How many bytes of the demo's output are read at once.
"""

STOP_TIMEOUT = 5.0
"""
How long a demo may take to end after it was asked to, in seconds, before it is killed.
"""

STOP_POLL_INTERVAL = 0.05
"""
How often a demo that was asked to end is checked, in seconds.
"""

LOG_ENCODING = "utf-8"
"""
The encoding the demo's output is read in; undecodable bytes are replaced.
"""

# %% output


@dataclass
class OutputLog:
    """
    The newest output of a process, at most :attr:`limit` bytes of it; written by the
    reading thread and read by request threads.
    """

    limit: int
    """
    How many of the newest bytes are kept.
    """

    data: bytearray = field(default_factory=bytearray)
    """
    The kept bytes.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    """
    Guards :attr:`data`.
    """

    def append(self, chunk: bytes) -> None:
        """
        :param chunk: Output that arrived; the oldest bytes beyond the limit are
            dropped.
        """
        with self.lock:
            self.data.extend(chunk)
            excess = len(self.data) - self.limit
            if excess > 0:
                del self.data[:excess]

    def text(self) -> str:
        """
        :return: The kept output as text.
        """
        with self.lock:
            return self.data.decode(LOG_ENCODING, errors="replace")

    def follow(self, stream: IO[bytes]) -> None:
        """
        Keep what the stream delivers until it ends.

        :param stream: The process's output.
        """
        for chunk in iter(lambda: stream.read1(READ_SIZE), b""):
            self.append(chunk)
        stream.close()


# %% one process


@dataclass
class DemoProcess:
    """
    One started demo: its process, the thread reading its output, and the pipe whose end
    tells the demo to stop when this process goes away.
    """

    path: Path
    """
    The demo file.
    """

    mode: RunMode
    """
    What the demo does.
    """

    process: subprocess.Popen
    """
    The demo's process, leader of its own process group.
    """

    log: OutputLog
    """
    The demo's newest output.
    """

    reader: threading.Thread
    """
    The thread moving the output into :attr:`log`.
    """

    stopped: bool = False
    """
    Whether the demo was stopped rather than ending on its own.
    """

    @classmethod
    def start(
        cls, command: List[str], path: Path, mode: RunMode, log: OutputLog
    ) -> DemoProcess:
        """
        :param command: The command running the demo.
        :param path: The demo file.
        :param mode: What the demo does.
        :param log: Receives the demo's output.
        :return: The started demo.
        :raises DemoNotStarted: When the operating system cannot start the command.
        """
        # the boundary to the operating system, where a refused start becomes an answer
        try:
            process = subprocess.Popen(
                command,
                cwd=path.parent,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise DemoNotStarted(path, str(error)) from error
        reader = threading.Thread(
            target=log.follow, args=(process.stdout,), daemon=True
        )
        reader.start()
        return cls(path=path, mode=mode, process=process, log=log, reader=reader)

    def state(self) -> RunState:
        """
        :return: Whether the demo runs, ended on its own or was stopped.
        """
        return_code = self.process.poll()
        if return_code is None:
            return RunState.RUNNING
        if self.stopped:
            return RunState.STOPPED
        return RunState.FINISHED if return_code == 0 else RunState.FAILED

    def status(self) -> RunStatus:
        """
        :return: The demo's state and newest output.
        """
        return RunStatus(
            state=self.state(),
            mode=self.mode,
            return_code=self.process.poll(),
            log=self.log.text(),
            path=str(self.path),
        )

    def stop(self, timeout: float = STOP_TIMEOUT) -> None:
        """
        Ask the demo's process group to end, kill it when it does not end in time, and
        release the pipes and the reading thread; stopping an ended demo only releases
        them. A process the demo started that keeps the output open is not waited for
        longer than the timeout.

        :param timeout: How long the demo may take to end, in seconds.
        """
        if self.process.poll() is None:
            self.stopped = True
            self.signal(signal.SIGTERM)
            deadline = time.monotonic() + timeout
            while self.process.poll() is None and time.monotonic() < deadline:
                time.sleep(STOP_POLL_INTERVAL)
            if self.process.poll() is None:
                self.signal(signal.SIGKILL)
        self.process.wait()
        self.reader.join(timeout)
        self.process.stdin.close()

    def signal(self, number: signal.Signals) -> None:
        """
        :param number: A signal for the demo's whole process group; the group exists
            while the demo's process is not reaped, which only :meth:`stop` does.
        """
        os.killpg(self.process.pid, number)


# %% runner


@dataclass
class DemoRunner:
    """
    Starts the demo of a plan, replacing the one that runs, and stops it.
    """

    directory: DemoDirectory
    """
    Where demos are written.
    """

    port: int
    """
    The port started demos publish their world on.
    """

    log_limit: int
    """
    How many of the newest bytes of a demo's output are kept.
    """

    template: DemoTemplate = field(default_factory=DemoTemplate)
    """
    Renders a plan into its demo.
    """

    stop_timeout: float = STOP_TIMEOUT
    """
    How long a demo may take to end after it was asked to, in seconds.
    """

    current: Optional[DemoProcess] = field(default=None, init=False)
    """
    The demo started last, running or ended.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    """
    Lets one request at a time start, stop or read the demo.
    """

    def start(self, demo: DemoDocument, mode: RunMode) -> RunStatus:
        """
        :param demo: A checked plan and its environment.
        :param mode: What the demo does.
        :return: The started demo's state.
        :raises DemoNotStarted: When the operating system cannot start it.
        """
        with self.lock:
            self.release()
            saved = self.directory.write(self.template.render(demo))
            path = Path(saved.path)
            self.current = DemoProcess.start(
                self.command(path, mode), path, mode, OutputLog(self.log_limit)
            )
            return self.current.status()

    def command(self, path: Path, mode: RunMode) -> List[str]:
        """
        :param path: A demo file.
        :param mode: What the demo does.
        :return: The command running it, ending with the viewer's process.
        """
        command = [
            self.directory.interpreter,
            str(path),
            DemoOption.PORT,
            str(self.port),
            DemoOption.LIFELINE,
        ]
        if mode is RunMode.STAGE:
            command.append(DemoOption.STAGE)
        return command

    def stop(self) -> RunStatus:
        """
        :return: The stopped demo's state, or the idle state when none was started.
        """
        with self.lock:
            if self.current is None:
                return RunStatus()
            self.current.stop(self.stop_timeout)
            return self.current.status()

    def status(self) -> RunStatus:
        """
        :return: The state of the demo started last, or the idle state.
        """
        with self.lock:
            return RunStatus() if self.current is None else self.current.status()

    def release(self) -> None:
        """
        Stop the demo started last, if any; the caller holds :attr:`lock`.
        """
        if self.current is not None:
            self.current.stop(self.stop_timeout)
