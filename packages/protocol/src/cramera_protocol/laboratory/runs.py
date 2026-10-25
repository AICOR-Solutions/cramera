"""
Robot task demos the laboratory runs on request, such as the PR2 vessel transfer:

whether one runs, how it ended, and the recording it saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Optional

from cramera_protocol.document import JsonDocument, document_field

# %% runs


class LaboratoryTask(StrEnum):
    """
    The bridge commands implementing the laboratory's native tasks.
    """

    TRANSFER = "cramera_bridge.laboratory.command"
    """
    The PR2 vessel transfer, given the laboratory bundle's path.
    """


class TransferOption(StrEnum):
    """
    The transfer command's laboratory input.
    """

    BUNDLE = "--bundle"
    """
    The directory of the laboratory scene bundle.
    """

    PREVIEW = "--preview"
    """
    Prepare the initial robot laboratory in this local scenes directory.
    """

    RECORDING = "--recording"
    """
    The name under which this run saves its recording.
    """

    LIVE_URL_FILE = "--live-url-file"
    """
    The local file receiving the started live publisher's URL.
    """

    PORT = "--port"
    """
    The live publisher's port; zero selects an available local port.
    """


class TaskRecording(StrEnum):
    """
    The recorded results of the laboratory's native tasks.
    """

    TRANSFER = "aicor_medical_lab_pr2_transfer"
    """
    A PR2 carries the vessel from A1 to A3.
    """


class TaskRunState(StrEnum):
    """
    How far a requested task demo is.
    """

    UNAVAILABLE = "unavailable"
    """
    The CRAM workspace is missing, so the demo cannot run here.
    """

    IDLE = "idle"
    """
    The demo has not run since the viewer started, and no recording exists.
    """

    RUNNING = "running"
    """
    The demo runs.
    """

    RECORDED = "recorded"
    """
    The demo's recording exists.
    """

    FAILED = "failed"
    """
    The demo ended without saving a recording.
    """


class TaskRunKey(StrEnum):
    """
    The keys of a task demo's state.
    """

    STATE = "state"
    """
    How far the demo is.
    """

    SCENE = "scene"
    """
    The recording's bundle.
    """

    ERROR = "error"
    """
    Why the demo failed.
    """

    LIVE_URL = "liveUrl"
    """
    The live publisher's base URL while the local demo is running.
    """

    CAN_RUN = "canRun"
    """
    Whether the local environment can start another native run.
    """


@dataclass(kw_only=True)
class TaskRun(JsonDocument):
    """
    The state of a task demo the laboratory runs on request.
    """

    state: TaskRunState = document_field(TaskRunKey.STATE)
    """
    How far the demo is.
    """

    scene: str = document_field(TaskRunKey.SCENE)
    """
    The bundle the demo saves its recording as.
    """

    error: Optional[str] = document_field(TaskRunKey.ERROR, default=None)
    """
    The end of the demo's output when it failed; None otherwise.
    """

    live_url: Optional[str] = document_field(TaskRunKey.LIVE_URL, default=None)
    """
    The live publisher's base URL, only while this demo runs and publishes.
    """

    can_run: Optional[bool] = document_field(TaskRunKey.CAN_RUN, default=None)
    """
    Whether the current local environment can execute the native demo.
    """
