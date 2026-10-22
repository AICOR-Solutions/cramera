"""
Robot task demos the laboratory runs on request, such as the PR2 vessel transfer: whether
one runs, how it ended, and the recording it saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Optional

from cramera_protocol.document import JsonDocument, document_field

# %% runs


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
