"""
The composed stage at the time it is read, with the change into metres and Z up.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from pxr import Usd, UsdGeom
from typing_extensions import Self

from cramera_usd.geometry.transforms import (
    HOMOGENEOUS_SIZE,
    SPACE_DIMENSIONS,
    RigidTransform,
)

# %% constants

Y_UP_TO_Z_UP = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))
"""
The rotation taking a Y-up frame into a Z-up frame.
"""

# %% frame


@dataclass
class StageFrame:
    """
    The composed stage at its initial time, with the change into metres and Z up.
    """

    stage: Usd.Stage
    """
    The composed stage.
    """

    time: Usd.TimeCode
    """
    The time the stage is read at: its start time when it has a time range.
    """

    correction: numpy.ndarray
    """
    The 4x4 matrix taking stage coordinates into metres with Z up.
    """

    meters_per_unit: float
    """
    The stage's length unit in metres.
    """

    transforms: UsdGeom.XformCache
    """
    The cache of world transforms at :attr:`time`.
    """

    @classmethod
    def of_stage(cls, stage: Usd.Stage) -> Self:
        """
        :param stage: A composed stage.
        :return: Its frame.
        """
        meters_per_unit = UsdGeom.GetStageMetersPerUnit(stage)
        time = (
            Usd.TimeCode(stage.GetStartTimeCode())
            if stage.HasAuthoredTimeCodeRange()
            else Usd.TimeCode.Default()
        )
        return cls(
            stage=stage,
            time=time,
            correction=cls.correction_of(stage, meters_per_unit),
            meters_per_unit=meters_per_unit,
            transforms=UsdGeom.XformCache(time),
        )

    @staticmethod
    def correction_of(stage: Usd.Stage, meters_per_unit: float) -> numpy.ndarray:
        """
        :param stage: A composed stage.
        :param meters_per_unit: The stage's length unit in metres.
        :return: The 4x4 matrix taking the stage's coordinates into metres with Z up.
        """
        correction = numpy.eye(HOMOGENEOUS_SIZE) * meters_per_unit
        correction[SPACE_DIMENSIONS, SPACE_DIMENSIONS] = 1.0
        if UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.y:
            correction[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = (
                numpy.array(Y_UP_TO_Z_UP) * meters_per_unit
            )
        return correction

    def world_matrix(self, prim: Usd.Prim) -> numpy.ndarray:
        """
        :param prim: A prim.
        :return: The prim's local-to-world matrix in metres with Z up, acting on column
            vectors.
        """
        local_to_world = numpy.array(self.transforms.GetLocalToWorldTransform(prim)).T
        return self.correction @ local_to_world

    def world_pose(self, prim: Usd.Prim) -> RigidTransform:
        """
        :param prim: A prim.
        :return: The rigid part of the prim's world transform.
        """
        return RigidTransform.rigid_part(self.world_matrix(prim))
