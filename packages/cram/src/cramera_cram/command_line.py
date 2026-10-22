"""
The commands of cramera-cram.
"""

from __future__ import annotations

import logging
import os
import runpy
import signal
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Sequence

# %% live


class VisualizationVariable(StrEnum):
    """
    The coraplex environment variable selecting the visualization backend, and the value
    selecting cramera's.
    """

    BACKEND = "CORAPLEX_VISUALIZATION"
    """
    Names the backend.
    """

    CRAMERA = "cramera"
    """
    Selects the cramera backend.
    """


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

    demo: Path
    """
    The demo file.
    """

    demo_arguments: List[str]
    """
    The arguments handed to the demo.
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
        options = vars(parser.parse_args(list(arguments)))
        return cls(
            demo=options[LiveArgument.DEMO].resolve(),
            demo_arguments=list(options[LiveArgument.DEMO_ARGUMENTS]),
        )

    def run_demo(self) -> None:
        """
        Run the demo as its own ``__main__`` with the cramera backend selected; the
        demo's directory comes first on the import path, as when it runs directly.
        """
        os.environ.setdefault(
            VisualizationVariable.BACKEND, VisualizationVariable.CRAMERA
        )
        sys.path.insert(0, str(self.demo.parent))
        original_arguments = sys.argv
        sys.argv = [str(self.demo), *self.demo_arguments]
        runpy.run_path(str(self.demo), run_name="__main__")
        sys.argv = original_arguments


def live(arguments: Optional[Sequence[str]] = None) -> None:
    """
    ``cramera-live demo.py [arguments]``: run a demo and keep publishing until Ctrl-C.

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


# %% onboard
