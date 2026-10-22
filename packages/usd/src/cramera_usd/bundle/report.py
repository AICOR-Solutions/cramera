"""
What a conversion read, wrote and left out, as ``conversion_report.json`` holds it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.conversion_report import (
    AnimationSummary,
    ConversionReport,
)
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.residuals import MILLIMETRES_PER_METRE
from cramera_usd.bundle.layout import Decimals
from cramera_usd.scene.stage import ConvertedStage

# %% report


@dataclass(frozen=True)
class ConversionDurations:
    """
    How long a conversion took.
    """

    read_seconds: float
    """
    How long reading the stage took.
    """

    write_seconds: float
    """
    How long writing the bundle took.
    """


@dataclass(frozen=True)
class ReportSummary:
    """
    Collects the conversion report of one bundle.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    converter: str
    """
    The version of the converter.
    """

    unmapped_inputs: Dict[str, List[str]]
    """
    The authored shader inputs no mapping carried over, by material.
    """

    animation: Optional[SceneAnimation]
    """
    The playback, or None.
    """

    def to_protocol(
        self, durations: ConversionDurations, bundle_bytes: int
    ) -> ConversionReport:
        """
        :param durations: How long reading and writing took.
        :param bundle_bytes: The size of the bundle's other files.
        :return: The content of ``conversion_report.json``.
        """
        log = self.stage.log
        return ConversionReport(
            source=str(self.stage.source),
            converter=self.converter,
            read_seconds=round(durations.read_seconds, Decimals.DURATION),
            write_seconds=round(durations.write_seconds, Decimals.DURATION),
            bundle_bytes=bundle_bytes,
            counts={str(key): count for key, count in sorted(log.counts.items())},
            skipped={str(key): count for key, count in sorted(log.skipped.items())},
            skipped_examples=log.skipped_examples,
            excluded=log.excluded,
            detached=log.detached,
            articulations=log.articulations,
            unmapped_inputs=self.unmapped_inputs,
            missing_textures=log.missing_textures,
            warnings=log.warnings,
            animation=None if self.animation is None else self.animation_summary(),
        )

    def animation_summary(self) -> AnimationSummary:
        """
        :return: The report's summary of the playback.
        """
        animation = self.animation
        bodies = animation.body_residuals
        largest_distance = max(
            (residual.largest_distance for residual in bodies), default=0.0
        )
        largest_angle = max(
            (residual.largest_angle for residual in bodies), default=0.0
        )
        return AnimationSummary(
            source=animation.source,
            frame_count=animation.frame_count,
            frames_per_second=animation.frames_per_second,
            largest_body_distance=round(
                MILLIMETRES_PER_METRE * largest_distance, Decimals.RESIDUAL
            ),
            largest_body_angle=round(
                float(numpy.degrees(largest_angle)), Decimals.RESIDUAL
            ),
            beyond_tolerance=[
                residual.path for residual in animation.beyond_tolerance()
            ],
            objects=[moving.key for moving in animation.objects],
            untracked_bodies=animation.untracked_bodies,
        )
