"""
Scenes a viewer runs on request, one at a time, such as robot demos whose queries a
phone steps through: which runs the server offers, which one runs, and the recording it
saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% names


class SceneRunsName(StrEnum):
    """
    The names of the scene runs plugin.
    """

    PLUGIN = "scene-runs"
    """
    The plugin's name and route segment.
    """


class SceneRunsVariable(StrEnum):
    """
    The environment variables the scene runs plugin reads.
    """

    CATALOG = "CRAMERA_SCENE_RUNS"
    """
    The JSON file of the runs the viewer offers, a :class:`SceneRunCatalog`; without it
    the viewer offers none.
    """


class SceneRunsRoute(StrEnum):
    """
    The plugin's routes, below its prefix.
    """

    STATE = "state"
    """
    The runs offered and the one started last.
    """

    START = "start/"
    """
    The prefix starting a run: ``start/<identifier>``.
    """

    STOP = "stop"
    """
    Stops the run that runs.
    """


class SceneRunPlaceholder(StrEnum):
    """
    What a run's command names and the viewer fills in when it starts the run.
    """

    RECORDING = "{recording}"
    """
    The name the run saves its recording under, new for every start.
    """


class SceneRunState(StrEnum):
    """
    How far the run started last is.
    """

    RUNNING = "running"
    """
    The run runs.
    """

    RECORDED = "recorded"
    """
    The run ended and its recording exists.
    """

    FAILED = "failed"
    """
    The run ended without a recording, other than on request.
    """

    STOPPED = "stopped"
    """
    The run was stopped on request.
    """


# %% catalog


class SceneRunKey(StrEnum):
    """
    The keys of a run the viewer offers.
    """

    IDENTIFIER = "identifier"
    """
    The run's name in routes: lowercase letters, digits and ``_``.
    """

    LABEL = "label"
    """
    What people call the run.
    """

    COMMAND = "command"
    """
    The program and arguments that perform the run.
    """

    SCENE = "scene"
    """
    A recording of the run to replay.
    """


class SceneRunCatalogKey(StrEnum):
    """
    The keys of the file of the runs the viewer offers.
    """

    RUNS = "runs"
    """
    The runs, in the order they are offered.
    """


@dataclass(kw_only=True)
class SceneRun(JsonDocument):
    """
    A run the viewer offers, as the server's catalog file names it.
    """

    identifier: str = document_field(SceneRunKey.IDENTIFIER)
    """
    The run's name in routes.
    """

    label: str = document_field(SceneRunKey.LABEL)
    """
    What people call the run.
    """

    command: List[str] = document_field(SceneRunKey.COMMAND)
    """
    The program and its arguments; :attr:`SceneRunPlaceholder.RECORDING` in an argument
    becomes the recording's name.

    It stays on the server: pages see only
    :class:`SceneRunChoice`.
    """

    scene: Optional[str] = document_field(SceneRunKey.SCENE, default=None)
    """
    A recording of the run to replay, or None.
    """

    def choice(self) -> SceneRunChoice:
        """
        :return: The run as pages see it, without its command.
        """
        return SceneRunChoice(
            identifier=self.identifier, label=self.label, scene=self.scene
        )


@dataclass(kw_only=True)
class SceneRunCatalog(JsonDocument):
    """
    The runs the viewer offers.
    """

    runs: List[SceneRun] = document_field(SceneRunCatalogKey.RUNS, default_factory=list)
    """
    The runs, in the order they are offered.
    """


# %% state


@dataclass(kw_only=True)
class SceneRunChoice(JsonDocument):
    """
    A run the viewer offers, as pages see it.
    """

    identifier: str = document_field(SceneRunKey.IDENTIFIER)
    """
    The run's name in routes.
    """

    label: str = document_field(SceneRunKey.LABEL)
    """
    What people call the run.
    """

    scene: Optional[str] = document_field(SceneRunKey.SCENE, default=None)
    """
    A recording of the run to replay, or None.
    """


class SceneRunStatusKey(StrEnum):
    """
    The keys of the state of the run started last.
    """

    IDENTIFIER = "identifier"
    """
    Which run it is.
    """

    STATE = "state"
    """
    How far it is.
    """

    RECORDING = "recording"
    """
    The name it saves its recording under.
    """

    LOG = "log"
    """
    The end of its output.
    """


@dataclass(kw_only=True)
class SceneRunStatus(JsonDocument):
    """
    The state of the run started last.
    """

    identifier: str = document_field(SceneRunStatusKey.IDENTIFIER)
    """
    Which run it is.
    """

    state: SceneRunState = document_field(SceneRunStatusKey.STATE)
    """
    How far it is.
    """

    recording: str = document_field(SceneRunStatusKey.RECORDING)
    """
    The name it saves its recording under.
    """

    log: str = document_field(SceneRunStatusKey.LOG, default="")
    """
    The end of its output.
    """


class SceneRunsStateKey(StrEnum):
    """
    The keys of what the plugin offers and runs.
    """

    RUNS = "runs"
    """
    The runs offered.
    """

    CURRENT = "current"
    """
    The run started last.
    """


@dataclass(kw_only=True)
class SceneRunsState(JsonDocument):
    """
    The runs the viewer offers and the one started last.
    """

    runs: List[SceneRunChoice] = document_field(
        SceneRunsStateKey.RUNS, default_factory=list
    )
    """
    The runs offered.
    """

    current: Optional[SceneRunStatus] = document_field(
        SceneRunsStateKey.CURRENT, default=None
    )
    """
    The run started last, or None before the first start.
    """
