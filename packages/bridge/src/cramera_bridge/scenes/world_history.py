"""
The recorded world itself: the CRAM world's model, as the modifications that built it,
and the value of every degree of freedom at every frame of the recording, so a recorded
run is rebuilt as the very world it ran in.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from typing_extensions import Any, Dict, List, Optional, Sequence, Tuple

from krrood.adapters.json_serializer import to_json
from semantic_digital_twin.world import World

WORLD_HISTORY_FORMAT = 1
"""
The layout of the world history file this bridge writes and reads.
"""


class WorldHistoryKey(StrEnum):
    """
    The keys of the world history file.
    """

    FORMAT = "format"
    """
    The layout the file follows.
    """

    BLOCKS = "blocks"
    """
    The world's modification blocks, oldest first, as CRAM serializes them.
    """

    VERSIONS = "versions"
    """
    Each model the world went through during the recording.
    """

    BLOCK_COUNT = "blockCount"
    """
    How many of the blocks built a model.
    """

    IDS = "ids"
    """
    The degrees of freedom of a model, in the order of its state.
    """

    FRAMES = "frames"
    """
    The world's state at each frame.
    """

    VERSION = "version"
    """
    The model a frame shows, as its index among the versions.
    """

    POSITIONS = "positions"
    """
    The position of every degree of freedom at a frame, in the order of its model's
    ids.
    """


# %% capture


@dataclass(frozen=True)
class WorldStateCapture:
    """
    The world as one frame of a recording saw it.
    """

    block_count: int
    """
    How many modification blocks had built the world.
    """

    ids: Tuple[UUID, ...]
    """
    The degrees of freedom of the world, in the order of its state; one tuple shared by
    the frames of one model.
    """

    positions: Tuple[float, ...]
    """
    The position of every degree of freedom, in the order of the ids.
    """


@dataclass
class WorldStateCapturer:
    """
    Captures the world's state for each frame, sharing the ids of frames of one model.
    """

    ids_by_block_count: Dict[int, Tuple[UUID, ...]] = field(default_factory=dict)
    """
    The ids of each model seen, by how many blocks built it.
    """

    def capture(self, world: World) -> WorldStateCapture:
        """
        :param world: The recorded world, held still by its lock.
        :return: Its model's place in its history and its state.
        """
        block_count = len(world.modification_history)
        ids = tuple(world.state.ids)
        known = self.ids_by_block_count.get(block_count)
        if known != ids:
            self.ids_by_block_count[block_count] = ids
            known = ids
        return WorldStateCapture(
            block_count=block_count,
            ids=known,
            positions=tuple(float(value) for value in world.state.positions),
        )


# %% history


@dataclass(frozen=True)
class ModelVersion:
    """
    One model the world went through during the recording.
    """

    block_count: int
    """
    How many of the history's blocks built it.
    """

    ids: Tuple[UUID, ...]
    """
    Its degrees of freedom, in the order of its state.
    """


@dataclass(frozen=True)
class FrameState:
    """
    The world's state at one frame.
    """

    version: int
    """
    The model the frame shows, as its index among the history's versions.
    """

    positions: Tuple[float, ...]
    """
    The position of every degree of freedom, in the order of the model's ids.
    """


@dataclass(frozen=True)
class WorldHistory:
    """
    A recorded world's model and its state at every frame.
    """

    blocks: List[Dict[str, Any]]
    """
    The world's modification blocks, oldest first, serialized.
    """

    versions: List[ModelVersion]
    """
    The models the world went through.
    """

    frames: List[FrameState]
    """
    The state at each frame.
    """

    @classmethod
    def of_captures(
        cls, world: World, captures: Sequence[WorldStateCapture]
    ) -> WorldHistory:
        """
        :param world: The recorded world, held still by its lock.
        :param captures: The world as each frame saw it.
        :return: The history, holding the blocks up to the last model a frame saw.
        """
        versions: List[ModelVersion] = []
        frames: List[FrameState] = []
        for capture in captures:
            version = ModelVersion(capture.block_count, capture.ids)
            if not versions or versions[-1] != version:
                versions.append(version)
            frames.append(FrameState(len(versions) - 1, capture.positions))
        block_count = max((version.block_count for version in versions), default=0)
        blocks = [to_json(block) for block in world.modification_history[:block_count]]
        return cls(blocks=blocks, versions=versions, frames=frames)

    def trimmed(self, kept: slice) -> WorldHistory:
        """
        :param kept: The frames to keep.
        :return: The history of those frames, keeping every model.
        """
        return WorldHistory(self.blocks, self.versions, self.frames[kept])

    def model_of(self, frame: int) -> ModelVersion:
        """
        :param frame: A frame of the history.
        :return: The model the frame shows.
        """
        return self.versions[self.frames[frame].version]

    # %% file

    def write(self, path: Path) -> None:
        """
        :param path: The gzipped file to write.
        """
        document = {
            WorldHistoryKey.FORMAT: WORLD_HISTORY_FORMAT,
            WorldHistoryKey.BLOCKS: self.blocks,
            WorldHistoryKey.VERSIONS: [
                {
                    WorldHistoryKey.BLOCK_COUNT: version.block_count,
                    WorldHistoryKey.IDS: [str(identity) for identity in version.ids],
                }
                for version in self.versions
            ],
            WorldHistoryKey.FRAMES: [
                {
                    WorldHistoryKey.VERSION: frame.version,
                    WorldHistoryKey.POSITIONS: list(frame.positions),
                }
                for frame in self.frames
            ],
        }
        with gzip.open(path, "wt", encoding="utf-8") as file:
            json.dump(document, file)

    @classmethod
    def read(cls, path: Path) -> Optional[WorldHistory]:
        """
        :param path: A gzipped file :meth:`write` wrote.
        :return: Its history, or None for a file of another layout.
        """
        with gzip.open(path, "rt", encoding="utf-8") as file:
            document = json.load(file)
        if document.get(WorldHistoryKey.FORMAT) != WORLD_HISTORY_FORMAT:
            return None
        return cls(
            blocks=document[WorldHistoryKey.BLOCKS],
            versions=[
                ModelVersion(
                    entry[WorldHistoryKey.BLOCK_COUNT],
                    tuple(UUID(identity) for identity in entry[WorldHistoryKey.IDS]),
                )
                for entry in document[WorldHistoryKey.VERSIONS]
            ],
            frames=[
                FrameState(
                    entry[WorldHistoryKey.VERSION],
                    tuple(entry[WorldHistoryKey.POSITIONS]),
                )
                for entry in document[WorldHistoryKey.FRAMES]
            ],
        )
