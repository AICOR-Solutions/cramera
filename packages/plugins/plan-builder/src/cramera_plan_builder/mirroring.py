"""
Mirroring where the real robot stands while the plan builder is attached to it, before
and between runs: cramera-bridge's posture mirror runs as a child process for as long as
the plan builder does, and its newest report is what the builder's 3D view shows the
robot in while no run publishes a world. The mirror only reads the drivers' joint
states; it commands nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from dataclasses import dataclass, field

from typing_extensions import IO, Optional

from cramera_plan_builder.bridge_processes import BridgeModule, InterpreterOption
from cramera_plan_builder.workspace import CramModules
from cramera_protocol.plan_builder import RobotPosture

# %% mirror


@dataclass
class PostureMirror:
    """
    Runs cramera-bridge's posture mirror and keeps the posture it reported last.
    """

    interpreter: str = field(default=sys.executable)
    """
    The Python interpreter that runs the mirror.
    """

    modules: CramModules = field(default_factory=CramModules)
    """
    Finds out whether the CRAM workspace the mirror needs is installed.
    """

    process: Optional[subprocess.Popen] = field(default=None, init=False)
    """
    The mirror's process once started, else None.
    """

    latest: RobotPosture = field(default_factory=RobotPosture, init=False)
    """
    The posture the mirror reported last; empty before its first report.
    """

    def start(self) -> None:
        """
        Start the mirror unless it runs already or the CRAM workspace is missing, and
        follow its reports on a thread of its own; it ends with the plan builder, since
        its standard input closes then.
        """
        if self.process is not None or self.modules.missing():
            return
        self.process = subprocess.Popen(
            [self.interpreter, InterpreterOption.RUN_MODULE, BridgeModule.MIRROR],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        threading.Thread(
            target=self.follow, args=(self.process.stdout,), daemon=True
        ).start()

    def follow(self, reports: IO[str]) -> None:
        """
        :param reports: The mirror's output, one posture as JSON per line, each kept as
            :attr:`latest` until it ends.
        """
        for line in reports:
            self.latest = RobotPosture.from_json(json.loads(line))

    def close(self) -> None:
        """
        End the mirror, if it was started.
        """
        if self.process is None:
            return
        self.process.stdin.close()
        self.process.terminate()
        self.process.wait()
