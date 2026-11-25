"""
What happens in a recorded run, on the same timeline as its paused world: the pieces it
handles as shape-sorting pieces, which gripper holds which piece from which frame to
which, and the steps, plan and actions of the run, with what is under way at the
paused frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from typing_extensions import Callable, Dict, Iterator, List, Optional

from cramera_bridge.questions.entity import NamedEntity
from cramera_bridge.questions.recorded.entities import (
    RecordedPlanNode,
    RecordedStep,
)
from cramera_bridge.questions.recorded.knowledge_base import RecordedKnowledge
from cramera_protocol.bundle.scene import PlanNodeKind, SceneDescription
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.robots.robot_parts import EndEffector
from semantic_digital_twin.semantic_annotations.semantic_annotations import (
    ShapeSortingPiece,
)
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

PIECE_GRASP_HEIGHT_FRACTION = 0.5
"""
Where on its height a piece is gripped, as a fraction of the height.
"""

FrameSource = Callable[[], int]
"""
Answers the frame the paused world shows.
"""


# %% entities


@dataclass
class Holding(NamedEntity):
    """
    A gripper holding a piece over a stretch of the run.
    """

    gripper: EndEffector
    """
    The gripper holding the piece.
    """

    piece: ShapeSortingPiece
    """
    The piece held.
    """

    step: Optional[RecordedStep]
    """
    The step of the run the piece is held in.
    """

    grasped_at_frame: int
    """
    The frame the piece is grasped at.
    """

    released_at_frame: int
    """
    The frame the piece is let go of at.
    """

    def holds_at(self, frame: int) -> bool:
        """
        :param frame: A frame of the recording.
        :return: Whether the piece is held at that frame.
        """
        return self.grasped_at_frame <= frame < self.released_at_frame


# %% pieces


@dataclass(frozen=True)
class PieceAnnotations:
    """
    Tells the world which of its free objects are pieces of the shape-sorting toy.
    """

    world: World
    """
    The world holding the free objects.
    """

    scene: SceneDescription
    """
    The recorded scene, which says how high each object is.
    """

    def annotate(self, objects: Dict[str, Body]) -> Dict[str, ShapeSortingPiece]:
        """
        :param objects: The free objects by their key.
        :return: The piece each object is, by the object's key.
        """
        heights = {
            description.key: description.height or 0.0
            for description in self.scene.objects
        }
        pieces: Dict[str, ShapeSortingPiece] = {}
        with self.world.modify_world():
            for key, body in objects.items():
                piece = ShapeSortingPiece(
                    root=body,
                    grasp_height=heights.get(key, 0.0) * PIECE_GRASP_HEIGHT_FRACTION,
                    name=PrefixedName(key),
                )
                self.world.add_semantic_annotation(piece)
                pieces[key] = piece
        return pieces


# %% episode


@dataclass
class PausedEpisode:
    """
    The steps, plan and holdings of a recorded run, and what of them is under way at
    the frame the paused world shows.
    """

    recorded: RecordedKnowledge
    """
    The recorded steps and plan of the run.
    """

    pieces: Dict[str, ShapeSortingPiece]
    """
    The pieces of the run by their key.
    """

    holdings: List[Holding] = field(default_factory=list)
    """
    Every holding of the run.
    """

    @classmethod
    def of_run(
        cls,
        recorded: RecordedKnowledge,
        pieces: Dict[str, ShapeSortingPiece],
        grippers: List[EndEffector],
        show_frame: Callable[[int], None],
    ) -> PausedEpisode:
        """
        :param recorded: The recorded steps and plan of the run.
        :param pieces: The pieces of the run by their key.
        :param grippers: The robot's grippers.
        :param show_frame: Moves the world to a frame.
        :return: The run, each holding given the gripper nearest its piece midway
            through the holding.
        """
        episode = cls(recorded=recorded, pieces=pieces)
        steps = {step.name: step for step in recorded.steps}
        for segment in recorded.bundle.scene.segments:
            piece = pieces.get(segment.picks) if segment.picks else None
            if (
                piece is None
                or not grippers
                or segment.attach is None
                or segment.detach is None
            ):
                continue
            show_frame((segment.attach + segment.detach) // 2)
            episode.holdings.append(
                Holding(
                    name=f"{segment.picks} held",
                    gripper=cls.nearest_gripper(piece, grippers),
                    piece=piece,
                    step=steps.get(segment.step),
                    grasped_at_frame=segment.attach,
                    released_at_frame=segment.detach,
                )
            )
        return episode

    @staticmethod
    def nearest_gripper(
        piece: ShapeSortingPiece, grippers: List[EndEffector]
    ) -> EndEffector:
        """
        :param piece: A piece.
        :param grippers: The robot's grippers.
        :return: The gripper whose tool frame is nearest the piece.
        """
        piece_position = piece.root.global_pose.position.to_np()[:3]
        return min(
            grippers,
            key=lambda gripper: float(
                np.linalg.norm(
                    gripper.tool_frame.global_pose.position.to_np()[:3] - piece_position
                )
            ),
        )

    def actions(self) -> List[RecordedPlanNode]:
        """
        :return: The plan's actions, outermost first.
        """
        return [
            node
            for node in self.recorded.plan_nodes
            if node.kind == PlanNodeKind.ACTION
        ]


# %% what is under way


@dataclass(frozen=True)
class StepsUnderWay:
    """
    The steps under way at the shown frame, read afresh at every evaluation.
    """

    episode: PausedEpisode
    frame: FrameSource

    def __iter__(self) -> Iterator[RecordedStep]:
        frame = self.frame()
        return (
            step
            for step in self.episode.recorded.steps
            if step.start_frame <= frame < step.end_frame
        )


@dataclass(frozen=True)
class HoldingsUnderWay:
    """
    The holdings under way at the shown frame, read afresh at every evaluation.
    """

    episode: PausedEpisode
    frame: FrameSource

    def __iter__(self) -> Iterator[Holding]:
        frame = self.frame()
        return (holding for holding in self.episode.holdings if holding.holds_at(frame))


@dataclass(frozen=True)
class PiecesHeld:
    """
    The pieces held at the shown frame, read afresh at every evaluation.
    """

    episode: PausedEpisode
    frame: FrameSource

    def __iter__(self) -> Iterator[ShapeSortingPiece]:
        return (holding.piece for holding in HoldingsUnderWay(self.episode, self.frame))
