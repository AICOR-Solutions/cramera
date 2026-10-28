"""
Shared fixtures of the scene runs plugin's tests.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cramera_protocol.scene_runs import SceneRun, SceneRunCatalog, SceneRunPlaceholder

FAKE_RUN = Path(__file__).parent / "dataset" / "fake_run.py"
"""
The stand-in for a robot demo.
"""

START = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
"""
When the tests start their runs.
"""


def fake_run(identifier: str, scenes: Path, behaviour: str, scene=None) -> SceneRun:
    """
    :return: A run of the stand-in that records, fails or waits.
    """
    return SceneRun(
        identifier=identifier,
        label=identifier.replace("_", " "),
        command=[
            sys.executable,
            str(FAKE_RUN),
            str(scenes),
            SceneRunPlaceholder.RECORDING,
            behaviour,
        ],
        scene=scene,
    )


@pytest.fixture
def scenes(tmp_path) -> Path:
    """
    :return: The scenes directory the runs record into.
    """
    directory = tmp_path / "scenes"
    directory.mkdir()
    return directory


@pytest.fixture
def catalog(scenes) -> SceneRunCatalog:
    """
    :return: A run that records, one that fails and one that runs until it is stopped.
    """
    return SceneRunCatalog(
        runs=[
            fake_run("pr2_transfer", scenes, "record", "aicor_medical_lab_pr2"),
            fake_run("fr3_plates", scenes, "fail"),
            fake_run("garmi_apartment", scenes, "wait"),
        ]
    )
