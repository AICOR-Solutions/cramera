"""
The process that already listens on the viewer's port, and its replacement by the viewer
being started.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import signal
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Iterator, Optional, Sequence

from cramera_protocol.viewer import ViewerInfoKey, ViewerRoute

logger = logging.getLogger(__name__)
"""
The logger of the replacement.
"""

LISTENING = "0A"
"""
The state of a listening socket in ``/proc/net/tcp``.
"""

PROC = Path("/proc")
"""
The process information of the kernel.
"""


class PortStillInUse(OSError):
    """
    The port stayed in use after the process on it was asked to stop.
    """

    def __init__(self, port: int, pid: Optional[int]) -> None:
        super().__init__(errno.EADDRINUSE, f"port {port} is still in use")
        self.port = port
        self.pid = pid


def is_viewer_command(words: Sequence[str]) -> bool:
    """
    :param words: A process's command line.
    :return: Whether it runs the viewer: a program named ``cramera`` (possibly run
        through Python), or Python running ``cramera.command_line``.
    """
    programs = [Path(word).name for word in words[:2]]
    return "cramera" in programs or "cramera.command_line" in words[1:]


@dataclass(frozen=True)
class PortOccupant:
    """
    Whatever listens on the viewer's host and port.
    """

    host: str
    """
    The address the viewer wants to listen on.
    """

    port: int
    """
    The port the viewer wants to listen on.
    """

    def url(self) -> str:
        """
        :return: The base URL of the occupant.
        """
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    def is_viewer(self, timeout: float = 2.0) -> bool:
        """
        :param timeout: How long to wait for the occupant's answer, in seconds.
        :return: Whether the occupant answers the viewer's information route as a
            cramera viewer.
        """
        try:
            with urllib.request.urlopen(
                self.url() + ViewerRoute.INFO, timeout=timeout
            ) as answer:
                information = json.loads(answer.read())
        except (urllib.error.URLError, OSError, ValueError):
            return False
        return isinstance(information, dict) and {
            ViewerInfoKey.VERSION,
            ViewerInfoKey.PROTOCOL_VERSION,
        } <= set(information)

    def is_viewer_process(self, pid: int) -> bool:
        """
        :param pid: A process.
        :return: Whether its command line is a cramera viewer command.
        """
        try:
            arguments = (PROC / str(pid) / "cmdline").read_bytes().split(b"\0")
        except OSError:
            return False
        return is_viewer_command(
            [argument.decode(errors="replace") for argument in arguments if argument]
        )

    def pid(self) -> Optional[int]:
        """
        :return: The process listening on the port, found through ``/proc``; None
            when there is none or it belongs to another user.
        """
        inodes = set(self._listening_inodes())
        if not inodes:
            return None
        for process in PROC.iterdir():
            if not process.name.isdigit():
                continue
            try:
                descriptors = list((process / "fd").iterdir())
            except OSError:
                continue
            for descriptor in descriptors:
                try:
                    target = os.readlink(descriptor)
                except OSError:
                    continue
                if target in inodes:
                    return int(process.name)
        return None

    def _listening_inodes(self) -> Iterator[str]:
        """
        :return: The socket links of the sockets listening on the port, as
            ``/proc/<pid>/fd`` names them.
        """
        for table in ("tcp", "tcp6"):
            try:
                lines = (PROC / "net" / table).read_text().splitlines()[1:]
            except OSError:
                continue
            for line in lines:
                fields = line.split()
                if len(fields) < 10 or fields[3] != LISTENING:
                    continue
                if int(fields[1].rsplit(":", 1)[1], 16) == self.port:
                    yield f"socket:[{fields[9]}]"

    def is_free(self) -> bool:
        """
        :return: Whether nothing accepts connections on the port any more.
        """
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            return probe.connect_ex((self.host, self.port)) != 0

    def replace_viewer(self, timeout: float = 10.0) -> Optional[int]:
        """
        Ask the viewer on the port to stop, if what listens there is one (it answers the
        information route as a viewer, or its command line is the viewer's), and wait
        until the port is free.

        :param timeout: How long to wait for the port, in seconds.
        :return: The process that was stopped, or None when the port was not held by a
            viewer this process may stop.
        :raises PortStillInUse: When the port is still in use after the timeout.
        """
        pid = self.pid()
        if pid is None or pid == os.getpid():
            raise PortStillInUse(self.port, pid)
        if not (self.is_viewer() or self.is_viewer_process(pid)):
            raise PortStillInUse(self.port, pid)
        logger.info("stopping the viewer on port %d (process %d)", self.port, pid)
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_free():
                return pid
            time.sleep(0.1)
        raise PortStillInUse(self.port, pid)
