"""
The trajectory, ``trajectory.json``: joint values and poses, one entry per frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.geometry import Pose

# %% trajectory


class TrajectoryKey(StrEnum):
    """
    The keys of ``trajectory.json``.
    """

    FRAMES_PER_SECOND = "framesPerSecond"
    """
    How many frames make one second.
    """

    LEGACY_FRAMES_PER_SECOND = "fps"
    """
    The key the earliest recordings used for :attr:`FRAMES_PER_SECOND`.
    """

    FRAMES = "frames"
    """
    The joint values per frame.
    """

    FRAME_TIMES = "at"
    """
    The wall-clock time of each frame.
    """

    BASE = "base"
    """
    The robot's root pose per frame.
    """

    MODEL_BASES = "modelBases"
    """
    The root pose of every robot instance per frame.
    """

    OBJECTS = "objects"
    """
    The pose of every free object per frame.
    """

    BODY_POSES = "bodyPoses"
    """
    The pose of loose bodies of a physics scene per frame.
    """


@dataclass(kw_only=True)
class Trajectory(JsonDocument):
    """
    The content of ``trajectory.json``.

    Every list holds one entry per frame.
    """

    frames: List[Dict[str, float]] = document_field(TrajectoryKey.FRAMES)
    """
    The value of every movable joint, by its prefixed name, per frame.
    """

    frames_per_second: Optional[float] = document_field(
        TrajectoryKey.FRAMES_PER_SECOND,
        legacy_keys=(TrajectoryKey.LEGACY_FRAMES_PER_SECOND,),
        default=None,
    )
    """
    How many frames make one second.
    """

    frame_times: List[float] = document_field(
        TrajectoryKey.FRAME_TIMES, default_factory=list
    )
    """
    The wall-clock time of each frame in seconds since the epoch.
    """

    base: List[Pose] = document_field(TrajectoryKey.BASE, default_factory=list)
    """
    The robot's root pose per frame.
    """

    model_bases: List[Dict[str, Pose]] = document_field(
        TrajectoryKey.MODEL_BASES, default_factory=list
    )
    """
    The root pose of every robot instance, by its identifier, per frame.
    """

    objects: List[Dict[str, Pose]] = document_field(
        TrajectoryKey.OBJECTS, default_factory=list
    )
    """
    The pose of every free object, by its key, per frame.
    """

    body_poses: List[Dict[str, Pose]] = document_field(
        TrajectoryKey.BODY_POSES, default_factory=list
    )
    """
    The pose of every loose body of a physics scene, by its name, per frame.
    """

    def frame_count(self) -> int:
        """
        :return: How many frames the trajectory holds.
        """
        return len(self.frames)
