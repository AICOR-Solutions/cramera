"""
``cramera-workshop``: the packaged scenes directory and the release check.
"""

from __future__ import annotations

import io
import shutil

import pytest

from cramera_workshop.bundle import RESOURCES
from cramera_workshop.command_line import RELEASE_PASSED, WorkshopCommand, main
from cramera_workshop.release import InvalidWorkshopRelease

from .test_release import RECORDING


def test_the_scenes_directory_holds_the_packaged_workshop():
    output = io.StringIO()
    main([WorkshopCommand.SCENES_DIRECTORY], output)
    assert output.getvalue().strip() == str(RESOURCES)


def test_a_complete_recording_passes_the_release_check(dataset, tmp_path):
    recording = tmp_path / RECORDING
    shutil.copytree(dataset / "recordings" / RECORDING, recording)
    output = io.StringIO()
    main([WorkshopCommand.CHECK_RELEASE, str(recording)], output)
    assert output.getvalue().strip() == f"{RECORDING} {RELEASE_PASSED}"


def test_an_incomplete_recording_fails_the_release_check(tmp_path):
    with pytest.raises(InvalidWorkshopRelease):
        main([WorkshopCommand.CHECK_RELEASE, str(tmp_path)], io.StringIO())
