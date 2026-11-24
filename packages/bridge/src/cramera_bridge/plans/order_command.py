"""
The command line of the bridge modules the plan builder asks:
``python -m <module> <order file> <answer file> [<expected order file>]`` answers one
order document with one answer document, and reads the order only once its standard
input closes, so it can be started, and its imports done, before the order is written;
meanwhile, it prepares for the order it is told to expect.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Any, Optional, Sequence

from cramera_protocol.document import JsonDocument

# %% command


@dataclass(frozen=True)
class OrderCommand(ABC):
    """
    Answers the order a file holds and writes the answer into another file.
    """

    def main(self, arguments: Sequence[str]) -> None:
        """
        Prepare for the expected order, wait until the standard input closes, then
        answer the order.

        :param arguments: The order's file, the file the answer is written to, and
            optionally the file of the order expected.
        """
        order_file, answer_file, *expected_file = arguments
        self.prepare(
            json.loads(Path(expected_file[0]).read_text(encoding="utf-8"))
            if expected_file
            else None
        )
        sys.stdin.read()
        order = json.loads(Path(order_file).read_text(encoding="utf-8"))
        Path(answer_file).write_text(
            json.dumps(self.answer(order).to_json()), encoding="utf-8"
        )

    def prepare(self, expected: Optional[Any]) -> None:
        """
        Do, before the order comes, work the order is likely to need; whatever it
        builds, the answer must not differ from one prepared for nothing.

        :param expected: The JSON of the order expected, None when none is.
        """

    @abstractmethod
    def answer(self, order: Any) -> JsonDocument:
        """
        :param order: The JSON of the order.
        :return: The answer to the order.
        """
