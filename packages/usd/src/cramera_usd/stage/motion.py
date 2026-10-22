"""
Sampling the world poses of prims whose transforms change over a stage's time samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy
from pxr import Usd, UsdGeom
from typing_extensions import List

from cramera_usd.animation.trace import BodyTrace, FrameCount
from cramera_usd.geometry.transforms import HOMOGENEOUS_SIZE, TransformTrack
from cramera_usd.stage.frame import StageFrame

# %% motion


@dataclass
class StageMotion:
    """
    Samples the world poses of prims whose transforms change over the stage's time
    samples.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    source: Path
    """
    The stage file, named as the source of the sampled poses.
    """

    def trace(self, paths: List[str], frames_per_second: float) -> BodyTrace:
        """
        :param paths: The paths of the prims to sample.
        :param frames_per_second: The sample rate.
        :return: The rigid world poses of the moving prims among them, sampled at the
            rate over the time samples of their transforms; one frame when none of them
            moves.
        """
        stage = self.frame.stage
        prims = [
            prim
            for path in paths
            if (prim := stage.GetPrimAtPath(path)) and self.transforms_of(prim)
        ]
        if not prims:
            return BodyTrace(frames_per_second, source=str(self.source))
        sample_times = sorted(
            {
                time
                for prim in prims
                for transform in self.transforms_of(prim)
                for time in transform.GetTimeSamples()
            }
        )
        rate = stage.GetTimeCodesPerSecond()
        count = FrameCount(
            (sample_times[-1] - sample_times[0]) / rate, frames_per_second
        ).count()
        matrices = numpy.zeros((len(prims), count, HOMOGENEOUS_SIZE, HOMOGENEOUS_SIZE))
        for index in range(count):
            transforms = UsdGeom.XformCache(
                Usd.TimeCode(sample_times[0] + index * rate / frames_per_second)
            )
            for prim_index, prim in enumerate(prims):
                matrices[prim_index, index] = (
                    self.frame.correction
                    @ numpy.array(transforms.GetLocalToWorldTransform(prim)).T
                )
        return BodyTrace(
            frames_per_second,
            {
                prim.GetPath().pathString: TransformTrack.rigid_part(
                    matrices[prim_index]
                )
                for prim_index, prim in enumerate(prims)
            },
            count,
            str(self.source),
        )

    @staticmethod
    def transforms_of(prim: Usd.Prim) -> List[UsdGeom.Xformable]:
        """
        :param prim: A prim.
        :return: The transforms of the prim and its ancestors that might change over
            time.
        """
        transforms = []
        while prim and not prim.IsPseudoRoot():
            transform = UsdGeom.Xformable(prim)
            if transform and transform.TransformMightBeTimeVarying():
                transforms.append(transform)
            prim = prim.GetParent()
        return transforms
