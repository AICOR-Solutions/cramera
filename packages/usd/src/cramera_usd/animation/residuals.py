"""
How far a playback strays from its recording, for one body or joint.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

from cramera_protocol.bundle.residuals import ResidualKind, ResidualRow
from cramera_usd.animation.deviation import PoseDeviation, ResidualTolerance
from cramera_usd.animation.models import LinkPlacement

# %% constants

MILLIMETRES_PER_METRE = 1e3
"""
The number of millimetres in a metre.
"""

RESIDUAL_DECIMALS = 4
"""
The decimals kept of the distances and angles a residual reports.
"""

# %% residual


@dataclass(eq=False)
class Residual:
    """
    How far the playback strays from the recording for one body or joint.
    """

    kind: ResidualKind
    """
    What is measured.
    """

    path: str
    """
    The USD path of the body or joint.
    """

    placement: LinkPlacement
    """
    The model and name of the link or joint in the bundle.
    """

    deviation: PoseDeviation
    """
    The error per frame.
    """

    tolerance: ResidualTolerance
    """
    The tolerance that picks the worst frame.
    """

    @property
    def largest_distance(self) -> float:
        """
        The largest position error in metres.
        """
        return self.deviation.largest_distance

    @property
    def largest_angle(self) -> float:
        """
        The largest orientation error in radians.
        """
        return self.deviation.largest_angle

    @property
    def frame(self) -> int:
        """
        The frame deviating most.
        """
        return self.deviation.worst_frame(self.tolerance)

    def within(self, tolerance: ResidualTolerance) -> bool:
        """
        :param tolerance: A tolerance.
        :return: Whether every frame lies within it.
        """
        return self.deviation.within(tolerance)

    def row(self) -> ResidualRow:
        """
        :return: The residual as a row of the residuals table.
        """
        return ResidualRow(
            kind=self.kind,
            path=self.path,
            name=self.placement.link,
            model=self.placement.model,
            largest_distance=round(
                self.largest_distance * MILLIMETRES_PER_METRE, RESIDUAL_DECIMALS
            ),
            largest_angle=round(
                float(numpy.degrees(self.largest_angle)), RESIDUAL_DECIMALS
            ),
            frame=self.frame,
            within_tolerance=self.within(self.tolerance),
        )
