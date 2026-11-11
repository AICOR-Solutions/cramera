"""
Asking cramera-bridge in a child process of its own: a command module of the bridge is
handed an order document in a file and writes its answer document into another, so the
plan builder never imports CRAM and every request starts from a fresh world.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, List

from cramera_plan_builder.exceptions import CramUnavailable, PlanBuilderError
from cramera_plan_builder.workspace import CramModules
from cramera_protocol.document import JsonDocument

# %% files


class ProcessFile(StrEnum):
    """
    The files a bridge process reads and writes in its own directory.
    """

    ORDER = "order.json"
    """
    What the bridge is asked.
    """

    ANSWER = "answer.json"
    """
    What it answers.
    """


class InterpreterOption(StrEnum):
    """
    The options of the interpreter running a bridge command.
    """

    RUN_MODULE = "-m"
    """
    Runs a module as the program.
    """


class BridgeModule(StrEnum):
    """
    The command modules of cramera-bridge the plan builder runs.
    """

    SCANNER = "cramera_bridge.plans.scanning"
    """
    Scans the scene.
    """

    VALIDATOR = "cramera_bridge.plans.validating"
    """
    Validates a plan.
    """

    REACH = "cramera_bridge.plans.reaching"
    """
    Measures what a robot model reaches.
    """

    MIRROR = "cramera_bridge.plans.mirroring"
    """
    Mirrors where the real robot stands.
    """


# %% process


@dataclass(frozen=True)
class BridgeProcess(ABC):
    """
    Answers an order with a command module of cramera-bridge, one process per order.
    """

    interpreter: str = field(default=sys.executable)
    """
    The Python interpreter that runs the module.
    """

    timeout: float = 300.0
    """
    How long the process may take, in seconds.
    """

    output_limit: int = 4096
    """
    How many of the newest characters of a failed process's output its error shows.
    """

    modules: CramModules = field(default_factory=CramModules)
    """
    Finds out whether the CRAM workspace the module needs is installed.
    """

    @property
    @abstractmethod
    def module(self) -> BridgeModule:
        """
        The command module that answers.
        """

    @abstractmethod
    def describe_failure(self, output: str) -> PlanBuilderError:
        """
        :param output: The newest output of a process that ended without an answer.
        :return: The error the failed process is reported as.
        """

    def answer(self, order: JsonDocument) -> Any:
        """
        :param order: What the module is asked.
        :return: The JSON of the module's answer.
        :raises CramUnavailable: Without the CRAM workspace.
        :raises PlanBuilderError: As :meth:`describe_failure` says, when the process ends
            without an answer.
        """
        missing = self.modules.missing()
        if missing:
            raise CramUnavailable(missing)
        with tempfile.TemporaryDirectory() as directory:
            order_file = Path(directory) / ProcessFile.ORDER
            answer_file = Path(directory) / ProcessFile.ANSWER
            order_file.write_text(json.dumps(order.to_json()), encoding="utf-8")
            finished = subprocess.run(
                self.command(order_file, answer_file),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self.timeout,
            )
            if finished.returncode != 0 or not answer_file.is_file():
                output = finished.stdout.decode("utf-8", errors="replace")
                raise self.describe_failure(output[-self.output_limit :])
            return json.loads(answer_file.read_text(encoding="utf-8"))

    def command(self, order_file: Path, answer_file: Path) -> List[str]:
        """
        :param order_file: The file holding the order.
        :param answer_file: The file the answer is written to.
        :return: The command running the module.
        """
        return [
            self.interpreter,
            InterpreterOption.RUN_MODULE,
            self.module,
            str(order_file),
            str(answer_file),
        ]
