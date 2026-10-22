"""
The commands of cramera-cram.
"""

from __future__ import annotations

import logging
import signal
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Sequence

from cramera_cram.coraplex_backend import CoraplexBackendRegistration
from cramera_cram.demo_script import DemoScript

DEMO_ARGUMENTS_SEPARATOR = "--"
"""
Everything after it on a command line is handed to the demo unread.
"""

# %% arguments


@dataclass(frozen=True)
class CommandLine:
    """
    A command line split into the command's own arguments and those after
    :data:`DEMO_ARGUMENTS_SEPARATOR`, which belong to the demo, such as its own options.
    """

    own: List[str]
    """
    The arguments the command reads.
    """

    demo: List[str]
    """
    The arguments handed to the demo unread.
    """

    @classmethod
    def split(cls, arguments: Sequence[str]) -> CommandLine:
        """
        :param arguments: A command's arguments.
        :return: The arguments split at the first separator.
        """
        arguments = list(arguments)
        if DEMO_ARGUMENTS_SEPARATOR not in arguments:
            return cls(own=arguments, demo=[])
        separator = arguments.index(DEMO_ARGUMENTS_SEPARATOR)
        return cls(own=arguments[:separator], demo=arguments[separator + 1 :])


# %% live


class LiveArgument(StrEnum):
    """
    The arguments of ``cramera-live``.
    """

    DEMO = "demo"
    """
    The demo file to run.
    """

    DEMO_ARGUMENTS = "arguments"
    """
    The arguments handed to the demo.
    """


@dataclass(frozen=True)
class LiveCommand:
    """
    Runs a demo file unchanged with the cramera backend selected, then keeps the
    process, and with it the live publisher, up until it is interrupted.

    The viewer is started separately with ``cramera``; this command only publishes.
    """

    demo: DemoScript
    """
    The demo file and its arguments.
    """

    @classmethod
    def parse(cls, arguments: Sequence[str]) -> LiveCommand:
        """
        :param arguments: The command's arguments.
        :return: The command.
        """
        parser = ArgumentParser(
            prog="cramera-live",
            description="Run a CRAM demo and publish it to the cramera viewer.",
        )
        parser.add_argument(LiveArgument.DEMO, type=Path, help="the demo file")
        parser.add_argument(
            LiveArgument.DEMO_ARGUMENTS, nargs="*", help="arguments for the demo"
        )
        command_line = CommandLine.split(arguments)
        options = vars(parser.parse_args(command_line.own))
        return cls(
            DemoScript(
                options[LiveArgument.DEMO].resolve(),
                options[LiveArgument.DEMO_ARGUMENTS] + command_line.demo,
            )
        )

    def run_demo(self) -> None:
        """
        Run the demo as its own ``__main__`` with the cramera backend selected.
        """
        with CoraplexBackendRegistration():
            self.demo.run()


def live(arguments: Optional[Sequence[str]] = None) -> None:
    """
    ``cramera-live demo.py [arguments] [-- demo options]``: run a demo and keep
    publishing until Ctrl-C.

    :param arguments: The arguments, or None for the process's.
    """
    logging.basicConfig(level=logging.INFO)
    command = LiveCommand.parse(sys.argv[1:] if arguments is None else arguments)
    command.run_demo()
    stop_signals = {signal.SIGINT, signal.SIGTERM}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, stop_signals)
    logging.getLogger(__name__).info(
        "The demo finished; the live publisher stays up until interrupted."
    )
    signal.sigwait(stop_signals)
    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
