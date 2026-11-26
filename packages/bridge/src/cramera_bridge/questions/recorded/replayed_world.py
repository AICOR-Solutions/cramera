"""
A recorded run asked about in the very CRAM world it ran in: the world is rebuilt from
the modifications the recording kept and moved to the state of the frame the viewer
shows, so a recorded scene answers with the same classes, instances, presets and hints
as the run did live.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from typing_extensions import Dict, List, Optional

from cramera.scenes import SceneCatalog
from cramera_bridge.documents import DocumentFile
from cramera_bridge.live.world_model import WorldModelView
from cramera_bridge.questions.desk import QuestionDesk
from cramera_bridge.questions.exceptions import UnknownScope
from cramera_bridge.questions.live import WorldQuestionDesk
from cramera_bridge.questions.recorded.paused_world import PAUSED_WORLDS, PausedWorld
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramera_bridge.scenes.world_history import WorldHistory
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.questions import (
    Members,
    PresetCatalog,
    QueryAnswer,
    QueryRequest,
    QueryScope,
    QuestionMatch,
    QuestionRequest,
    Vocabulary,
)
from krrood.adapters.json_serializer import from_json
from semantic_digital_twin.adapters.world_entity_kwargs_tracker import (
    WorldEntityWithIDKwargsTracker,
)
from semantic_digital_twin.world_description.derivatives import Derivatives
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

RECORDED_WORLD_TITLE = "The recorded world"
"""
The title of the desk answering questions about a recorded run's own world.
"""

RECORDED_WORLD_NAME = "recorded_world"
"""
The name of a rebuilt recorded world.
"""

# %% world


@dataclass
class ReplayedWorld:
    """
    A recorded world rebuilt from its history, moved to one frame at a time.
    """

    history: WorldHistory
    """
    The recorded world's model and its state at every frame.
    """

    world: Optional[World] = None
    """
    The rebuilt world, or None before the first frame was shown.
    """

    block_count: int = 0
    """
    How many of the history's blocks built the world.
    """

    frame: Optional[int] = None
    """
    The frame the world shows, or None before one was shown.
    """

    @property
    def frame_count(self) -> int:
        """
        The number of frames of the recording.
        """
        return len(self.history.frames)

    def show(self, frame: int) -> bool:
        """
        Move the world to a frame: its model and every degree of freedom.

        :param frame: A frame of the recording; one past either end shows that end.
        :return: Whether the world was built anew, so its entities are new ones.
        """
        frame = min(max(frame, 0), self.frame_count - 1)
        if frame == self.frame:
            return False
        model = self.history.model_of(frame)
        rebuilt = self.world is None or model.block_count < self.block_count
        if rebuilt:
            self.world = World(name=RECORDED_WORLD_NAME)
            self.block_count = 0
        self.build_up_to(model.block_count)
        self.move_to(frame)
        return rebuilt

    def build_up_to(self, block_count: int) -> None:
        """
        Apply the history's blocks the world lacks, up to a model.

        :param block_count: How many blocks built the model.
        """
        if block_count == self.block_count:
            return
        arguments = WorldEntityWithIDKwargsTracker.from_world(
            self.world
        ).create_kwargs()
        with self.world.modify_world():
            for block in self.history.blocks[self.block_count : block_count]:
                from_json(block, **arguments).apply(world=self.world)
        self.block_count = block_count

    def move_to(self, frame: int) -> None:
        """
        Set every degree of freedom to its value at a frame.

        :param frame: A frame of the recording.
        """
        state = self.history.frames[frame]
        ids = self.history.model_of(frame).ids
        world_state = self.world.state
        if tuple(world_state.ids) == ids:
            world_state.set_derivative(
                Derivatives.position, np.array(state.positions, dtype=float)
            )
        else:
            for identity, position in zip(ids, state.positions):
                if identity in world_state:
                    world_state[identity].position = position
        self.world.notify_state_change()
        self.frame = frame


# %% desk


@dataclass
class ReplayedWorldDesk:
    """
    Answers questions about a recorded run in its own world at the frame the viewer
    shows, with the desk a live run of that world answers with.
    """

    replayed: ReplayedWorld
    """
    The recorded world.
    """

    class_index: WorkspaceClassIndex = field(default_factory=WorkspaceClassIndex)
    """
    The workspace classes a query may name.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """
    Keeps one question at a time moving the world.
    """

    desk: QuestionDesk = field(init=False)
    """
    The desk over the world.
    """

    free_objects: List[Body] = field(init=False, default_factory=list)
    """
    The world's free objects, as the live publisher finds them.
    """

    def __post_init__(self) -> None:
        self.show(0)

    def show(self, frame: int) -> None:
        """
        Move the world to a frame, building the desk anew over a world built anew.

        :param frame: A frame of the recording.
        """
        earlier = self.replayed.world
        block_count = self.replayed.block_count
        rebuilt = self.replayed.show(frame)
        if rebuilt or self.replayed.block_count != block_count:
            self.free_objects = list(
                WorldModelView.of_world(self.replayed.world).objects
            )
        if not rebuilt:
            return
        if earlier is not None and earlier in PAUSED_WORLDS:
            PAUSED_WORLDS.remove(earlier)
        PAUSED_WORLDS.append(self.replayed.world)
        PausedWorld.forget_other_worlds()
        self.desk = WorldQuestionDesk(
            self.replayed.world,
            lambda: self.free_objects,
            self.class_index,
            title=RECORDED_WORLD_TITLE,
        ).desk()

    def preset_catalog(self) -> PresetCatalog:
        """
        :return: The ready-made questions of the world.
        """
        with self.lock:
            return self.desk.preset_catalog()

    def vocabulary(self, scope: QueryScope) -> Vocabulary:
        """
        :param scope: A body of knowledge.
        :return: The names a query of it may use.
        """
        with self.lock:
            return self.desk.vocabulary(scope)

    def members(self, scope: QueryScope, name: str) -> Members:
        """
        :param scope: A body of knowledge.
        :param name: A type's name, a variable's, or a dotted path from one.
        :return: The members that may follow the name's dot.
        """
        with self.lock:
            return self.desk.members(scope, name)

    def answer_query(self, request: QueryRequest) -> QueryAnswer:
        """
        :param request: A query and the frame it is asked at.
        :return: Its answer about the world at that frame.
        """
        with self.lock:
            self.show(request.frame or 0)
            return self.desk.answer_query(request)

    def answer_question(self, request: QuestionRequest) -> QuestionMatch:
        """
        :param request: A plain-language question.
        :return: The ready-made question it asks, or the reply that none does.
        """
        with self.lock:
            return self.desk.answer_question(request)


# %% scenes


@dataclass
class ReplayedWorldDesks:
    """
    The recorded-world desk of each scene that keeps its world, built once on first
    use.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    class_index: WorkspaceClassIndex
    """
    The workspace classes a query may name.
    """

    built: Dict[str, ReplayedWorldDesk] = field(default_factory=dict)
    """
    The desk of each scene built so far.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """
    Builds each scene's desk once.
    """

    def history_file(self, scene: str) -> Optional[Path]:
        """
        :param scene: A bundle name.
        :return: The file keeping the scene's world, or None for a scene keeping none.
        """
        directory = self.catalog.directory_of(scene).path / scene
        description = DocumentFile(directory / BundleFile.SCENE).read_if_present(
            SceneDescription
        )
        if description is None or description.world_history is None:
            return None
        path = directory / description.world_history
        return path if path.is_file() else None

    def offers(self, scene: str) -> bool:
        """
        :param scene: A bundle name.
        :return: Whether the scene keeps the world it was recorded in.
        """
        return scene in self.built or self.history_file(scene) is not None

    def of_scene(self, scene: str) -> ReplayedWorldDesk:
        """
        :param scene: A bundle name that :meth:`offers` a world.
        :return: The scene's desk.
        """
        with self.lock:
            desk = self.built.get(scene)
            if desk is None:
                history = WorldHistory.read(self.history_file(scene))
                if history is None or not history.frames:
                    raise UnknownScope(scope=QueryScope.CURRENT_STATE, offered=[])
                desk = ReplayedWorldDesk(ReplayedWorld(history), self.class_index)
                self.built[scene] = desk
            return desk
