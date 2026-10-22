"""
World poses of rigid bodies at a fixed rate, from a recorded trace file or sampled from
a stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

import numpy
from typing_extensions import Dict, Self

from cramera_usd.exceptions import TraceIncomplete, TraceNotFound
from cramera_usd.geometry.transforms import TransformTrack

# %% constants

SCALAR_FIRST_TO_LAST = (1, 2, 3, 0)
"""
The order taking a quaternion ``[w, x, y, z]`` to ``[x, y, z, w]``.
"""

ROUNDING_ALLOWANCE = 1e-9
"""
Added before rounding a frame count down, so a duration that is a whole number of frames
apart from rounding errors keeps its last frame.
"""

# %% trace files


class TraceArray(StrEnum):
    """
    The arrays of a body trace file, as the twin's recorder names them.
    """

    BODIES = "bodies"
    """
    The USD paths of the recorded bodies.
    """

    POSITIONS = "pos"
    """
    ``(frames, bodies, 3)`` world positions in metres.
    """

    QUATERNIONS = "quat"
    """
    ``(frames, bodies, 4)`` world orientations as quaternions, scalar first.
    """

    SAMPLE_RATE = "sample_hz"
    """
    The number of frames per second.
    """


# %% trace


@dataclass
class BodyTrace:
    """
    World poses of rigid bodies at a fixed rate, by USD path.
    """

    frames_per_second: float
    """
    The number of frames per second.
    """

    poses: Dict[str, TransformTrack] = field(default_factory=dict)
    """
    The pose track of every recorded body.
    """

    frame_count: int = 1
    """
    The number of frames.
    """

    source: str = ""
    """
    Where the poses were recorded or sampled.
    """

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        :param path: A ``.npz`` file as the twin's recorder writes it: body paths,
            positions, scalar-first quaternions and the sample rate.
        :return: The trace it holds.
        :raises TraceNotFound: When the file does not exist.
        :raises TraceIncomplete: When the file lacks one of the arrays.
        """
        if not path.is_file():
            raise TraceNotFound(path)
        arrays = numpy.load(path, allow_pickle=False)
        missing = [name.value for name in TraceArray if name.value not in arrays.files]
        if missing:
            raise TraceIncomplete(path, missing)
        positions = arrays[TraceArray.POSITIONS.value]
        quaternions = arrays[TraceArray.QUATERNIONS.value][
            ..., list(SCALAR_FIRST_TO_LAST)
        ]
        return cls(
            float(arrays[TraceArray.SAMPLE_RATE.value]),
            {
                str(body): TransformTrack.of_positions(
                    positions[:, index], quaternions[:, index]
                )
                for index, body in enumerate(arrays[TraceArray.BODIES.value])
            },
            len(positions),
            str(path),
        )

    def resampled(self, frames_per_second: float) -> Self:
        """
        :param frames_per_second: The new rate.
        :return: The trace at the new rate over the same duration, each new frame
            taking the nearest recorded frame.
        """
        duration = (self.frame_count - 1) / self.frames_per_second
        count = FrameCount(duration, frames_per_second).count()
        frames = numpy.minimum(
            numpy.rint(
                numpy.arange(count) * self.frames_per_second / frames_per_second
            ).astype(int),
            self.frame_count - 1,
        )
        return replace(
            self,
            frames_per_second=frames_per_second,
            poses={path: track.at(frames) for path, track in self.poses.items()},
            frame_count=count,
        )


@dataclass(frozen=True)
class FrameCount:
    """
    The frames a span of time holds at a rate, its first and last instant included.
    """

    duration: float
    """
    The span in seconds.
    """

    frames_per_second: float
    """
    The rate.
    """

    def count(self) -> int:
        """
        :return: The number of frames, both ends included.
        """
        return (
            int(
                numpy.floor(self.duration * self.frames_per_second + ROUNDING_ALLOWANCE)
            )
            + 1
        )
