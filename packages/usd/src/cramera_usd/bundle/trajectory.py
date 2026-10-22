"""
The frames a converted bundle plays back, as ``trajectory.json`` holds them.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Dict, List

from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.geometry import Pose
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.bundle.layout import Decimals
from cramera_usd.geometry.transforms import RigidTransform

# %% constants

STATIC_FRAMES_PER_SECOND = 1.0
"""
The rate of the single frame of a static scene.
"""

# %% trajectories


@dataclass(frozen=True)
class StaticTrajectory:
    """
    One frame holding the initial value of every movable joint.
    """

    joint_values: Dict[str, float]
    """
    The value of every movable joint, by trajectory key.
    """

    def to_protocol(self) -> Trajectory:
        """
        :return: The content of ``trajectory.json``.
        """
        return Trajectory(
            frames=[self.joint_values],
            frames_per_second=STATIC_FRAMES_PER_SECOND,
            base=[RigidTransform().to_protocol()],
            objects=[{}],
        )


@dataclass(frozen=True)
class AnimatedTrajectory:
    """
    The frames of a recorded playback; without a robot the base stays at the origin.
    """

    animation: SceneAnimation
    """
    The playback.
    """

    def to_protocol(self) -> Trajectory:
        """
        :return: The content of ``trajectory.json``.
        """
        animation = self.animation
        return Trajectory(
            frames=self.frames(),
            frames_per_second=animation.frames_per_second,
            base=self.base(),
            objects=self.objects(),
        )

    def frames(self) -> List[Dict[str, float]]:
        """
        :return: The joint values by trajectory key, per frame.
        """
        keys = list(self.animation.joint_values)
        if not keys:
            return [{} for _ in range(self.animation.frame_count)]
        columns = [self.animation.joint_values[key].tolist() for key in keys]
        return [dict(zip(keys, row)) for row in zip(*columns)]

    def base(self) -> List[Pose]:
        """
        :return: The robot's base pose per frame.
        """
        if self.animation.base is None:
            return [RigidTransform().to_protocol()] * self.animation.frame_count
        return self.animation.base.poses(Decimals.POSE)

    def objects(self) -> List[Dict[str, Pose]]:
        """
        :return: The pose of every object by key, per frame.
        """
        tracks = {
            moving.key: moving.poses.poses(Decimals.POSE)
            for moving in self.animation.objects
        }
        return [
            {key: poses[frame] for key, poses in tracks.items()}
            for frame in range(self.animation.frame_count)
        ]
