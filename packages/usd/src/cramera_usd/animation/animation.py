"""
Everything a bundle needs to play a recording back, and how well it does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy
from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.residuals import ResidualsTable
from cramera_usd.animation.deviation import ResidualTolerance
from cramera_usd.animation.models import (
    AnimatedObject,
    NO_MODEL,
    KinematicModel,
    LinkPlacement,
    RobotModel,
)
from cramera_usd.animation.residuals import Residual
from cramera_usd.animation.run_record import StepSegment
from cramera_usd.geometry.transforms import TransformTrack

# %% animation


@dataclass(eq=False)
class SceneAnimation:
    """
    Everything a bundle needs to play a recording back, and how well it does.
    """

    frames_per_second: float
    """
    The playback rate.
    """

    frame_count: int
    """
    The number of playback frames.
    """

    models: List[KinematicModel]
    """
    The environment model, then the robot model if there is one.
    """

    joint_values: Dict[str, numpy.ndarray]
    """
    The value per frame of every movable joint of the models, by trajectory key.
    """

    base: Optional[TransformTrack]
    """
    The world pose of the robot's root link per frame, or None without a robot.
    """

    objects: List[AnimatedObject]
    """
    The links played back by their world poses.
    """

    segments: List[StepSegment]
    """
    The labelled stretches of the playback.
    """

    body_residuals: List[Residual]
    """
    How far each recorded body is replayed from where it was recorded.
    """

    joint_residuals: List[Residual]
    """
    How much recorded motion each movable joint cannot make.
    """

    placements: Dict[str, LinkPlacement]
    """
    Where each converted link ended up, by converted link name; links without geometry
    that were turned into objects have none.
    """

    untracked_bodies: List[str] = field(default_factory=list)
    """
    Recorded bodies no link stands for.
    """

    tolerance: ResidualTolerance = field(default_factory=ResidualTolerance)
    """
    The tolerance the residuals are judged by.
    """

    source: str = ""
    """
    Where the body poses were recorded or sampled.
    """

    @property
    def robot(self) -> Optional[RobotModel]:
        """
        The robot model, or None.
        """
        return next(
            (model for model in self.models if isinstance(model, RobotModel)), None
        )

    @property
    def residuals(self) -> List[Residual]:
        """
        The body residuals, then the joint residuals.
        """
        return self.body_residuals + self.joint_residuals

    def beyond_tolerance(self) -> List[Residual]:
        """
        :return: The residuals exceeding the tolerance.
        """
        return [
            residual
            for residual in self.residuals
            if not residual.within(self.tolerance)
        ]

    def residuals_table(self) -> ResidualsTable:
        """
        :return: The residuals as the table ``residuals.csv`` holds.
        """
        return ResidualsTable(rows=[residual.row() for residual in self.residuals])

    def placement_of(self, link: str) -> LinkPlacement:
        """
        :param link: The converted name of a link.
        :return: Where the link ended up; a link turned into nothing has no model.
        """
        return self.placements.get(link, LinkPlacement(NO_MODEL, link))
