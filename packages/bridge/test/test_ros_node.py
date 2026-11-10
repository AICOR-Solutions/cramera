"""
The node spun on a thread of its own.
"""

from __future__ import annotations

# %% Imports
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("rclpy")

# %% ending


def test_a_process_spinning_a_node_ends_normally() -> None:
    ended = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parent / "dataset" / "spinning_node_process.py"),
        ],
        capture_output=True,
        timeout=60,
    )

    assert ended.returncode == 0, ended.stderr
