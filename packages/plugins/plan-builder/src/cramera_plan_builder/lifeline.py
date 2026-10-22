"""
The demo's side of its ownership by the viewer: the viewer holds the write end of the
demo's standard input, and the demo ends when that input closes, which the operating
system does when the viewer ends in any way.
"""

from __future__ import annotations

import os
import signal
import threading
from dataclasses import dataclass

from typing_extensions import Callable, Optional

READ_SIZE = 4096
"""
How many bytes of the input are read at once while waiting for its end.
"""

# %% lifeline


@dataclass
class Lifeline:
    """
    Watches an input that stays open while the owning process lives.
    """

    descriptor: int
    """
    The file descriptor of the input; the owner never writes to it, so it only ends.

    It is read unbuffered, so the watching thread holds no lock of a file object the
    interpreter closes when it shuts down.
    """

    end: Optional[Callable[[], None]] = None
    """
    Called once the input ended; None ends this process as a termination request from
    outside would.
    """

    def watch(self) -> threading.Thread:
        """
        :return: The started thread that calls :attr:`end` once the input ends.
        """
        thread = threading.Thread(target=self.follow, daemon=True)
        thread.start()
        return thread

    def follow(self) -> None:
        """
        Read the input until it ends, then call :attr:`end`.
        """
        for _ in iter(lambda: os.read(self.descriptor, READ_SIZE), b""):
            continue
        if self.end is None:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        self.end()
