"""
Scanning the scene for a plan's objects: each scan runs cramera-bridge's scanner as a
child process of its own, which perceives through the robot's camera and answers with
the plan's objects after the scan.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import List

from cramera_plan_builder.exceptions import CramUnavailable, ScanFailed
from cramera_plan_builder.workspace import CramModules
from cramera_protocol.detection import SceneScan, SceneScanOrder

# %% files


class ScanFile(StrEnum):
    """
    The files a scan's process reads and writes in its own directory.
    """

    ORDER = "order.json"
    """
    What is scanned.
    """

    SCAN = "scan.json"
    """
    The scan.
    """


class ScanCommandPart(StrEnum):
    """
    The fixed parts of the command running the scanner.
    """

    RUN_MODULE = "-m"
    """
    The interpreter's option running a module as the program.
    """

    SCANNER = "cramera_bridge.plans.scanning"
    """
    The module of cramera-bridge that scans the scene as a command.
    """


# %% scanner


@dataclass(frozen=True)
class SceneScans:
    """
    Scans the scene, one process per scan.
    """

    interpreter: str = field(default=sys.executable)
    """
    The Python interpreter that runs the scanner.
    """

    timeout: float = 300.0
    """
    How long a scan may take, in seconds.
    """

    output_limit: int = 4096
    """
    How many of the newest characters of a failed scan's output its error shows.
    """

    modules: CramModules = field(default_factory=CramModules)
    """
    Finds out whether the CRAM workspace the scanner needs is installed.
    """

    def scan(self, order: SceneScanOrder) -> SceneScan:
        """
        :param order: The plan, the region and the scene the camera sees.
        :return: The plan's objects after the scan.
        :raises CramUnavailable: Without the CRAM workspace.
        :raises ScanFailed: When the scanner ends without a scan.
        """
        missing = self.modules.missing()
        if missing:
            raise CramUnavailable(missing)
        with tempfile.TemporaryDirectory() as directory:
            order_file = Path(directory) / ScanFile.ORDER
            scan_file = Path(directory) / ScanFile.SCAN
            order_file.write_text(json.dumps(order.to_json()), encoding="utf-8")
            finished = subprocess.run(
                self.command(order_file, scan_file),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=self.timeout,
            )
            if finished.returncode != 0 or not scan_file.is_file():
                output = finished.stdout.decode("utf-8", errors="replace")
                raise ScanFailed(output[-self.output_limit :])
            return SceneScan.from_json(
                json.loads(scan_file.read_text(encoding="utf-8"))
            )

    def command(self, order_file: Path, scan_file: Path) -> List[str]:
        """
        :param order_file: The file holding what is scanned.
        :param scan_file: The file the scan is written to.
        :return: The command running the scanner.
        """
        return [
            self.interpreter,
            ScanCommandPart.RUN_MODULE,
            ScanCommandPart.SCANNER,
            str(order_file),
            str(scan_file),
        ]
