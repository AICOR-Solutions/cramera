"""
The scenes index, ``index.json``: the bundles of a scenes directory, as the viewer's
pickers offer them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion

# %% names


class ReservedSceneName(StrEnum):
    """
    Bundle names the viewer and the live publisher keep for themselves.
    """

    LIVE = "__live__"
    """
    The throwaway bundle of the world a running demo shows right now.
    """

    RECORDING = "__recording__"
    """
    The bundle a live recording is written to before it is saved under a name.
    """


@dataclass
class InvalidSceneName(ProtocolError):
    """
    A bundle name that is not a valid directory name for a bundle.
    """

    name: str
    """
    The name that was given.
    """

    def message(self) -> str:
        return (
            f"{self.name!r} is not a scene name: use 1 to 64 letters, digits, "
            f"'_' or '-', and not one of {[member.value for member in ReservedSceneName]}."
        )


@dataclass(frozen=True)
class SceneName:
    """
    A validated bundle name, which is also the bundle's directory name.
    """

    text: str
    """
    The name.
    """

    def __post_init__(self) -> None:
        if not self.is_valid(self.text):
            raise InvalidSceneName(self.text)

    @staticmethod
    def is_valid(text: str) -> bool:
        """
        :param text: A proposed bundle name.
        :return: Whether it is 1 to 64 letters, digits, ``_`` or ``-`` and not
            reserved.
        """
        return re.fullmatch(r"[A-Za-z0-9_-]{1,64}", text) is not None and text not in {
            member.value for member in ReservedSceneName
        }


# %% index


class IndexEntryKey(StrEnum):
    """
    The keys of one bundle in the scenes index.
    """

    NAME = "name"
    """
    The bundle's name.
    """

    ROBOT = "robot"
    """
    The robot's display name.
    """

    ENVIRONMENT = "environment"
    """
    The environment's display name.
    """

    TASK = "task"
    """
    The task the bundle shows.
    """

    VERSION = "version"
    """
    The revision of the recording.
    """


@dataclass(kw_only=True)
class SceneIndexEntry(JsonDocument):
    """
    One bundle as the viewer's pickers offer it.
    """

    name: str = document_field(IndexEntryKey.NAME)
    """
    The bundle's name.
    """

    robot: str = document_field(IndexEntryKey.ROBOT, default="")
    """
    The robot's display name, empty for a bundle without a robot.
    """

    environment: Optional[str] = document_field(IndexEntryKey.ENVIRONMENT, default=None)
    """
    The environment's display name, or None for a bundle without an environment.
    """

    task: Optional[str] = document_field(IndexEntryKey.TASK, default=None)
    """
    The task the bundle shows.
    """

    version: Optional[str] = document_field(IndexEntryKey.VERSION, default=None)
    """
    The revision of the recording, when one task was recorded several times.
    """


class IndexKey(StrEnum):
    """
    The keys of ``index.json``.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The protocol version the index was written with.
    """

    DEFAULT = "default"
    """
    The bundle the viewer opens first.
    """

    SCENES = "scenes"
    """
    The bundles.
    """


@dataclass(kw_only=True)
class SceneIndex(JsonDocument):
    """
    The content of ``index.json``.
    """

    format_version: ProtocolVersion = document_field(
        IndexKey.FORMAT_VERSION, default=UNVERSIONED
    )
    """
    The protocol version the index was written with.
    """

    default: Optional[str] = document_field(IndexKey.DEFAULT, default=None)
    """
    The bundle the viewer opens first, or None to open the first entry.
    """

    scenes: List[SceneIndexEntry] = document_field(
        IndexKey.SCENES, default_factory=list
    )
    """
    The bundles, in the order the pickers offer them.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)

    def entry(self, name: str) -> Optional[SceneIndexEntry]:
        """
        :param name: A bundle name.
        :return: The entry of that bundle, or None when the index does not list it.
        """
        return next((entry for entry in self.scenes if entry.name == name), None)
