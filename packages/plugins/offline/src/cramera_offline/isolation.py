"""
Serving the viewer from a process without network routes: the process runs in a new
Linux network namespace, which holds nothing but its own loopback device, and answers on
a listening socket the launching process opened on the host's loopback address.
"""

from __future__ import annotations

import socket
import subprocess
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from http.server import ThreadingHTTPServer

from typing_extensions import Callable, List, Self, Sequence, Type

from cramera.http.server import HttpServer, RequestHandler
from cramera_offline.exceptions import NetworkIsolationUnavailable

# %% namespaces


class IsolationCommand(StrEnum):
    """
    The command and options that start a process in new namespaces.
    """

    UNSHARE = "unshare"
    """
    The util-linux command that runs a program in new namespaces.
    """

    USER = "--user"
    """
    A new user namespace, so an unprivileged user may create the others.
    """

    MAP_ROOT_USER = "--map-root-user"
    """
    Maps the user to root inside the user namespace.
    """

    NETWORK = "--net"
    """
    A new network namespace, holding only an unconfigured loopback device.
    """

    PROBE = "true"
    """
    The program run to find out whether namespaces can be created.
    """


ProcessStarter = Callable[..., subprocess.Popen]
"""
Starts a process; :class:`subprocess.Popen` outside of tests.
"""

ProcessRunner = Callable[..., subprocess.CompletedProcess]
"""
Runs a process to its end; :func:`subprocess.run` outside of tests.
"""


@dataclass
class NetworkNamespace:
    """
    Starts programs in a new user and network namespace.
    """

    run: ProcessRunner = field(default=subprocess.run)
    """
    Runs the probe.
    """

    start: ProcessStarter = field(default=subprocess.Popen)
    """
    Starts the isolated program.
    """

    def prefix(self) -> List[str]:
        """
        :return: The command words that run the words after them in the namespaces.
        """
        return [
            IsolationCommand.UNSHARE,
            IsolationCommand.USER,
            IsolationCommand.MAP_ROOT_USER,
            IsolationCommand.NETWORK,
        ]

    def require_available(self) -> None:
        """
        :raises NetworkIsolationUnavailable: When the current user cannot create the
            namespaces.
        """
        probe = self.run(
            [*self.prefix(), IsolationCommand.PROBE],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            raise NetworkIsolationUnavailable(probe.stderr)

    def launch(
        self, command: Sequence[str], listener: socket.socket
    ) -> subprocess.Popen:
        """
        :param command: The program to run; it receives the descriptor of
            ``listener`` as its last argument.
        :param listener: A listening socket the program inherits.
        :return: The started process.
        :raises NetworkIsolationUnavailable: When the namespaces cannot be created.
        """
        self.require_available()
        descriptor = listener.fileno()
        return self.start(
            [*self.prefix(), *command, str(descriptor)],
            pass_fds=(descriptor,),
        )


# %% inherited socket


@dataclass(kw_only=True)
class InheritedSocketServer(HttpServer):
    """
    The viewer's HTTP server answering on a listening socket it inherited instead of one
    it opens, so it can serve from a namespace without network routes.
    """

    descriptor: int
    """
    The descriptor of the inherited listening socket.
    """

    def start(self) -> Self:
        """
        Adopt the socket and start serving.

        :return: This server.
        """
        listener = socket.socket(fileno=self.descriptor)
        self.host, self.port = listener.getsockname()[:2]
        handler: Type[RequestHandler] = type(
            "BoundRequestHandler", (RequestHandler,), {"answerer": self.answerer}
        )
        self.server = ThreadingHTTPServer(
            (self.host, self.port), handler, bind_and_activate=False
        )
        self.server.socket.close()
        self.server.socket = listener
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self
