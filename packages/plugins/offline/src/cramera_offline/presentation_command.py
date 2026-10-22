"""
``cramera-offline``: prepare a presentation of recorded scenes, check it, export it as a
static site, and serve it on this machine without network access.
"""

from __future__ import annotations

import argparse
import logging
import signal
import socket
import sys
import webbrowser
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path

from typing_extensions import Callable, List, Optional, Sequence, TextIO

from cramera_offline.check_command import ReportText
from cramera_offline.isolation import NetworkNamespace
from cramera_offline.presentation import (
    PresentationDirectory,
    PresentationPreparation,
    PresentationSite,
)
from cramera_offline.presentation_server import PresentationServer
from cramera_protocol.exceptions import ProtocolError

# %% vocabulary


class Action(StrEnum):
    """
    The command's actions.
    """

    PREPARE = "prepare"
    """
    Write a new presentation directory.
    """

    CHECK = "check"
    """
    Check that the presented bundles are complete.
    """

    SERVE = "serve"
    """
    Serve the presentation with the viewer.
    """

    EXPORT_SITE = "export-site"
    """
    Write the presentation as a static site.
    """


class PresentationOption(StrEnum):
    """
    The command's options.
    """

    ACTION = "action"
    """
    What to do.
    """

    PRESENTATION = "presentation"
    """
    The presentation directory.
    """

    STORYBOARD = "--storyboard"
    """
    The storyboard a new presentation shows.
    """

    SCENES = "--scenes"
    """
    A scenes directory the bundles of a new presentation are taken from.
    """

    OUTPUT = "--output"
    """
    The directory a static site is written to.
    """

    HOST = "--host"
    """
    The loopback address to listen on.
    """

    PORT = "--port"
    """
    The port to listen on.
    """

    NO_BROWSER = "--no-browser"
    """
    Do not open the presentation in a browser.
    """

    ISOLATED = "--isolated"
    """
    Serve from a process in a network namespace without routes.
    """

    LISTEN_DESCRIPTOR = "--listen-descriptor"
    """
    The inherited listening socket an isolated server answers on.
    """


class PresentationExit(IntEnum):
    """
    The command's exit codes.
    """

    DONE = 0
    """
    The action succeeded.
    """

    INCOMPLETE = 1
    """
    A presented bundle cannot follow a reference.
    """

    REFUSED = 2
    """
    The action could not be done, for example because the destination holds files.
    """


DEFAULT_PORT = 8713
"""
The port a presentation is served on unless told otherwise; the viewer's own default
stays free.
"""

LOOPBACK = "127.0.0.1"
"""
The address a presentation is served on.
"""

MODULE_OPTION = "-m"
"""
The Python option that runs a module as the program.
"""

# %% options


STOP_SIGNALS = frozenset({signal.SIGINT, signal.SIGTERM})
"""
The signals that stop a served presentation.
"""


@dataclass(frozen=True)
class PresentationOptions:
    """
    What the command was asked to do.
    """

    action: Action
    """
    What to do.
    """

    presentation: Path
    """
    The presentation directory.
    """

    storyboard: Optional[Path] = None
    """
    The storyboard a new presentation shows; needed to prepare one.
    """

    scenes: List[Path] = field(default_factory=list)
    """
    The scenes directories the bundles of a new presentation are taken from.
    """

    output: Optional[Path] = None
    """
    The directory a static site is written to; needed to export one.
    """

    host: str = LOOPBACK
    """
    The loopback address to listen on.
    """

    port: int = DEFAULT_PORT
    """
    The port to listen on.
    """

    open_browser: bool = True
    """
    Whether to open the presentation in a browser.
    """

    isolated: bool = False
    """
    Whether to serve from a process in a network namespace without routes.
    """

    listen_descriptor: Optional[int] = None
    """
    The inherited listening socket an isolated server answers on.
    """

    @classmethod
    def from_arguments(cls, arguments: Optional[Sequence[str]]) -> PresentationOptions:
        """
        :param arguments: The command-line arguments; the process arguments when None.
        :return: The options they give.
        :raises SystemExit: When the arguments are invalid, after argparse printed why.
        """
        parser = argparse.ArgumentParser(
            prog="cramera-offline", description=__doc__.strip().splitlines()[0]
        )
        parser.add_argument(
            PresentationOption.ACTION, type=Action, choices=list(Action)
        )
        parser.add_argument(PresentationOption.PRESENTATION, type=Path)
        parser.add_argument(PresentationOption.STORYBOARD, type=Path, default=None)
        parser.add_argument(
            PresentationOption.SCENES, type=Path, action="append", default=[]
        )
        parser.add_argument(PresentationOption.OUTPUT, type=Path, default=None)
        parser.add_argument(PresentationOption.HOST, default=LOOPBACK)
        parser.add_argument(PresentationOption.PORT, type=int, default=DEFAULT_PORT)
        parser.add_argument(PresentationOption.NO_BROWSER, action="store_true")
        parser.add_argument(PresentationOption.ISOLATED, action="store_true")
        parser.add_argument(
            PresentationOption.LISTEN_DESCRIPTOR, type=int, default=None
        )
        parsed = parser.parse_args(arguments)
        if parsed.action is Action.PREPARE and parsed.storyboard is None:
            parser.error(f"{Action.PREPARE} needs {PresentationOption.STORYBOARD}")
        if parsed.action is Action.EXPORT_SITE and parsed.output is None:
            parser.error(f"{Action.EXPORT_SITE} needs {PresentationOption.OUTPUT}")
        return cls(
            action=parsed.action,
            presentation=parsed.presentation,
            storyboard=parsed.storyboard,
            scenes=parsed.scenes,
            output=parsed.output,
            host=parsed.host,
            port=parsed.port,
            open_browser=not parsed.no_browser,
            isolated=parsed.isolated,
            listen_descriptor=parsed.listen_descriptor,
        )

    def serves_in_this_process(self) -> bool:
        """
        :return: Whether the presentation is served by threads of this process, which
            must find the stop signals blocked.
        """
        return self.action is Action.SERVE and not self.isolated


# %% command


@dataclass
class PresentationCommand:
    """
    The command's actions on one set of options.
    """

    options: PresentationOptions
    """
    What the command was asked to do.
    """

    output: TextIO = sys.stdout
    """
    Where reports and addresses are printed.
    """

    wait_for_stop: Callable[[], None] = field(default=lambda: None)
    """
    Returns when a presentation served in this process is to stop.
    """

    namespace: NetworkNamespace = field(default_factory=NetworkNamespace)
    """
    Starts the isolated server process.
    """

    open_page: Callable[[str], object] = field(default=webbrowser.open)
    """
    Opens an address in the browser.
    """

    def run(self) -> int:
        """
        :return: The exit code of the requested action.
        """
        presentation = PresentationDirectory(self.options.presentation)
        if self.options.action is Action.PREPARE:
            presentation = PresentationPreparation(
                self.options.storyboard, self.options.scenes, presentation.path
            ).prepare()
        if not self.complete(presentation):
            return PresentationExit.INCOMPLETE
        if self.options.action is Action.EXPORT_SITE:
            index = PresentationSite(presentation, self.options.output).write()
            print(
                f"exported {len(index.scenes)} scenes to {self.options.output}",
                file=self.output,
            )
        if self.options.action is Action.SERVE:
            self.serve(presentation)
        return PresentationExit.DONE

    def complete(self, presentation: PresentationDirectory) -> bool:
        """
        :param presentation: A presentation.
        :return: Whether every presented bundle is complete; the reports are printed.
        """
        reports = presentation.check()
        for report in reports:
            print("\n".join(ReportText(report).lines()), file=self.output)
        return all(report.is_complete() for report in reports)

    def serve(self, presentation: PresentationDirectory) -> None:
        """
        :param presentation: A checked presentation.
        """
        if self.options.isolated:
            self.serve_isolated()
            return
        server = PresentationServer(presentation).server(
            self.options.host, self.options.port, self.options.listen_descriptor
        )
        with server:
            address = f"{server.url()}/"
            print(f"presentation ready at {address}", file=self.output, flush=True)
            if self.options.open_browser:
                self.open_page(address)
            self.wait_for_stop()

    def serve_isolated(self) -> None:
        """
        Open the listening socket here, serve from a child process in a network
        namespace that inherits it, and stop the child when this process is asked to
        stop; the signal handlers are restored afterwards.
        """
        with socket.create_server((self.options.host, self.options.port)) as listener:
            host, port = listener.getsockname()[:2]
            process = self.namespace.launch(self.child_command(), listener)
            previous = {
                stop_signal: signal.signal(stop_signal, lambda *_: process.terminate())
                for stop_signal in STOP_SIGNALS
            }
            address = f"http://{host}:{port}/"
            print(f"isolated presentation ready at {address}", file=self.output)
            if self.options.open_browser:
                self.open_page(address)
            process.wait()
            for stop_signal, handler in previous.items():
                signal.signal(stop_signal, handler)

    def child_command(self) -> List[str]:
        """
        :return: The command serving the presentation from an inherited socket; the
            socket's descriptor is appended when the child is started.
        """
        return [
            sys.executable,
            MODULE_OPTION,
            __name__,
            Action.SERVE,
            str(self.options.presentation.resolve()),
            PresentationOption.NO_BROWSER,
            PresentationOption.LISTEN_DESCRIPTOR,
        ]


@dataclass(frozen=True)
class CommandBoundary:
    """
    Where a refused action becomes a message for the person and an exit code.
    """

    action: Callable[[], int]
    """
    Runs the action and returns its exit code.
    """

    error_output: TextIO = field(default_factory=lambda: sys.stderr)
    """
    Where the reason of a refusal is printed; the process's error stream when the
    boundary is created.
    """

    def exit_code(self) -> int:
        """
        The process boundary is where a refused action becomes an exit code, so this is
        where viewer and protocol errors are caught.

        :return: The action's exit code, or :attr:`PresentationExit.REFUSED` after its
            reason was printed.
        """
        try:
            return self.action()
        except ProtocolError as error:
            print(error.message(), file=self.error_output)
            return PresentationExit.REFUSED


def wait_for_stop_signal() -> None:
    """
    Return once the process is interrupted or terminated; the signals must have been
    blocked before the serving threads started.
    """
    signal.sigwait(STOP_SIGNALS)


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """
    Run the requested action.

    :param arguments: The command-line arguments; the process arguments when None.
    :return: The process exit code.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    options = PresentationOptions.from_arguments(arguments)
    if options.serves_in_this_process():
        signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
    command = PresentationCommand(options, wait_for_stop=wait_for_stop_signal)
    return CommandBoundary(command.run).exit_code()


if __name__ == "__main__":
    sys.exit(main())
