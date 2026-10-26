"""
Turning a laser scan into a point cloud the builder keeps: an E57 file is read scan by
scan in chunks, each point placed by its scan's pose, a random share of them sampled,
and the sample thinned on a voxel grid to at most the builder's number of points, which
are written as a binary PLY vertex cloud with their colours.

This module needs pye57 and numpy, the ``e57`` extra of the package; it is imported
only when they are installed, see :class:`cramera_scene_builder.uploads.ScanModules`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy
import pye57
from typing_extensions import Dict, List, Tuple

from cramera_protocol.scene_builder import SceneBuilderLimits
from cramera_scene_builder.exceptions import MalformedScan, ScanProblem

# %% fields


class E57Field(StrEnum):
    """
    The point fields of an E57 scan the builder reads.
    """

    CARTESIAN_X = "cartesianX"
    CARTESIAN_Y = "cartesianY"
    CARTESIAN_Z = "cartesianZ"
    CARTESIAN_INVALID_STATE = "cartesianInvalidState"
    SPHERICAL_RANGE = "sphericalRange"
    SPHERICAL_AZIMUTH = "sphericalAzimuth"
    SPHERICAL_ELEVATION = "sphericalElevation"
    SPHERICAL_INVALID_STATE = "sphericalInvalidState"
    COLOR_RED = "colorRed"
    COLOR_GREEN = "colorGreen"
    COLOR_BLUE = "colorBlue"
    INTENSITY = "intensity"


CARTESIAN_FIELDS = (E57Field.CARTESIAN_X, E57Field.CARTESIAN_Y, E57Field.CARTESIAN_Z)
"""
The fields of a point given by its coordinates.
"""

SPHERICAL_FIELDS = (
    E57Field.SPHERICAL_RANGE,
    E57Field.SPHERICAL_AZIMUTH,
    E57Field.SPHERICAL_ELEVATION,
)
"""
The fields of a point given by its range and direction.
"""

COLOR_FIELDS = (E57Field.COLOR_RED, E57Field.COLOR_GREEN, E57Field.COLOR_BLUE)
"""
The fields of a point's colour.
"""

VALID_STATE = 0
"""
The invalid state of a point whose coordinates are valid.
"""

INTENSITY_LIMITS = "intensityLimits"
"""
The scan node holding the range of its intensities.
"""


class IntensityLimit(StrEnum):
    """
    The bounds of a scan's intensities.
    """

    MINIMUM = "intensityMinimum"
    MAXIMUM = "intensityMaximum"


# %% sampling

CHUNK_POINTS = 4_000_000
"""
How many points are read at once.
"""

OVERSAMPLING = 8
"""
How many times the builder's number of points are sampled before the sample is thinned
on the voxel grid.
"""

VOXEL_SEARCH_STEPS = 24
"""
How many voxel sizes are tried at most while thinning.
"""

ENOUGH_POINTS = 0.9
"""
The share of the builder's number of points at which a thinned cloud is kept.
"""

GREY = 200
"""
The colour value of points of a scan without colours or intensities.
"""

COLOR_MAXIMUM = 255
"""
The largest value of an 8-bit colour channel.
"""


@dataclass
class ScanSample:
    """
    The sampled points of a scan file in the file's coordinates, with their colours.
    """

    positions: numpy.ndarray
    """
    The positions, one row of three 32-bit floats per point.
    """

    colors: numpy.ndarray
    """
    The colours, one row of three bytes per point.
    """

    def __len__(self) -> int:
        return len(self.positions)

    def thinned(self, maximum: int) -> ScanSample:
        """
        :param maximum: How many points stay at most.
        :return: One point of every cell of the coarsest voxel grid found that keeps at
            most ``maximum`` points, or this sample when it holds no more.
        """
        if len(self) <= maximum:
            return self
        origin = self.positions.min(axis=0)
        extent = float((self.positions.max(axis=0) - origin).max())
        # sizes are searched between a grid of 2^20 cells per axis and one cell
        smallest, largest = extent / 2**20, extent
        kept = numpy.arange(0)
        for _ in range(VOXEL_SEARCH_STEPS):
            size = math.sqrt(smallest * largest)
            cells = self.cells(origin, size)
            if len(cells) > maximum:
                smallest = size
                continue
            largest, kept = size, cells
            if len(cells) >= ENOUGH_POINTS * maximum:
                break
        return ScanSample(positions=self.positions[kept], colors=self.colors[kept])

    def cells(self, origin: numpy.ndarray, size: float) -> numpy.ndarray:
        """
        :param origin: The grid's lowest corner.
        :param size: The edge of a grid cell.
        :return: The index of the first point in every occupied cell.
        """
        indices = numpy.floor((self.positions - origin) / size).astype(numpy.int64)
        shape = indices.max(axis=0) + 1
        keys = numpy.ravel_multi_index(indices.T, tuple(int(axis) for axis in shape))
        return numpy.unique(keys, return_index=True)[1]

    def ply(self) -> bytes:
        """
        :return: The points as a binary little-endian PLY vertex cloud.
        """
        records = numpy.empty(len(self), dtype=PLY_RECORD)
        for axis, name in enumerate(("x", "y", "z")):
            records[name] = self.positions[:, axis]
        for channel, name in enumerate(("red", "green", "blue")):
            records[name] = self.colors[:, channel]
        header = PLY_HEADER.format(count=len(self)).encode("ascii")
        return header + records.tobytes()


PLY_RECORD = numpy.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)
"""
One point of the written cloud.
"""

PLY_HEADER = (
    "ply\n"
    "format binary_little_endian 1.0\n"
    "element vertex {count}\n"
    "property float x\n"
    "property float y\n"
    "property float z\n"
    "property uchar red\n"
    "property uchar green\n"
    "property uchar blue\n"
    "end_header\n"
)
"""
The header of the written cloud.
"""


# %% scans


@dataclass(frozen=True)
class ScanPoints:
    """
    How the points of one scan of an E57 file are read.
    """

    header: pye57.ScanHeader
    """
    The scan's header.
    """

    def fields(self) -> List[E57Field]:
        """
        :return: The fields read: the coordinates, their invalid state, and the colours
            or else the intensity, where the scan has them.
        :raises MalformedScan: When the scan gives neither coordinates nor ranges and
            directions.
        """
        available = set(self.header.point_fields)
        if available.issuperset(CARTESIAN_FIELDS):
            fields = list(CARTESIAN_FIELDS) + [E57Field.CARTESIAN_INVALID_STATE]
        elif available.issuperset(SPHERICAL_FIELDS):
            fields = list(SPHERICAL_FIELDS) + [E57Field.SPHERICAL_INVALID_STATE]
        else:
            raise MalformedScan(ScanProblem.NO_COORDINATES)
        if available.issuperset(COLOR_FIELDS):
            fields += COLOR_FIELDS
        else:
            fields.append(E57Field.INTENSITY)
        return [field for field in fields if field in available]

    def intensity_range(self) -> Tuple[float, float]:
        """
        :return: The lowest and highest intensity the scan declares, else 0 and 1.
        """
        bounds = []
        for limit, default in (
            (IntensityLimit.MINIMUM, 0.0),
            (IntensityLimit.MAXIMUM, 1.0),
        ):
            path = f"{INTENSITY_LIMITS}/{limit.value}"
            defined = self.header.node.isDefined(path)
            bounds.append(
                float(self.header[INTENSITY_LIMITS][limit.value].value())
                if defined
                else default
            )
        return bounds[0], bounds[1]

    def positions(self, values: Dict[E57Field, numpy.ndarray]) -> numpy.ndarray:
        """
        :param values: A chunk's values by field.
        :return: The chunk's positions in the file's coordinates, placed by the scan's
            pose.
        """
        if E57Field.CARTESIAN_X in values:
            local = numpy.stack([values[field] for field in CARTESIAN_FIELDS], axis=1)
        else:
            distance = values[E57Field.SPHERICAL_RANGE]
            azimuth = values[E57Field.SPHERICAL_AZIMUTH]
            elevation = values[E57Field.SPHERICAL_ELEVATION]
            local = numpy.stack(
                [
                    distance * numpy.cos(elevation) * numpy.cos(azimuth),
                    distance * numpy.cos(elevation) * numpy.sin(azimuth),
                    distance * numpy.sin(elevation),
                ],
                axis=1,
            )
        return local @ self.header.rotation_matrix.T + self.header.translation

    def valid(self, values: Dict[E57Field, numpy.ndarray]) -> numpy.ndarray:
        """
        :param values: A chunk's values by field.
        :return: Which points have valid coordinates.
        """
        for field in (
            E57Field.CARTESIAN_INVALID_STATE,
            E57Field.SPHERICAL_INVALID_STATE,
        ):
            if field in values:
                return values[field] == VALID_STATE
        return numpy.ones(len(next(iter(values.values()))), dtype=bool)

    def colors(self, values: Dict[E57Field, numpy.ndarray]) -> numpy.ndarray:
        """
        :param values: A chunk's values by field.
        :return: The chunk's colours: its own, its intensities as grey, else grey.
        """
        count = len(next(iter(values.values())))
        if E57Field.COLOR_RED in values:
            return numpy.stack([values[field] for field in COLOR_FIELDS], axis=1)
        if E57Field.INTENSITY in values:
            lowest, highest = self.intensity_range()
            share = (values[E57Field.INTENSITY] - lowest) / max(highest - lowest, 1e-12)
            grey = numpy.clip(share * COLOR_MAXIMUM, 0, COLOR_MAXIMUM).astype(
                numpy.uint8
            )
            return numpy.repeat(grey[:, None], 3, axis=1)
        return numpy.full((count, 3), GREY, dtype=numpy.uint8)


@dataclass(frozen=True)
class E57Scan:
    """
    An E57 file to be kept as a point cloud.
    """

    path: Path
    """
    The file.
    """

    limits: SceneBuilderLimits
    """
    The builder's limits; the cloud keeps at most
    :attr:`SceneBuilderLimits.maximum_points` points.
    """

    seed: int = 0
    """
    Seeds the sampling, so the same file gives the same cloud.
    """

    def point_cloud(self) -> bytes:
        """
        The reader's errors become the builder's here, at the one place a file from a
        client is opened.

        :return: The thinned points as a binary PLY vertex cloud.
        :raises MalformedScan: When the file is no E57 file the builder reads, or holds
            no valid point.
        """
        try:
            sample = self.sample()
        except pye57.libe57.E57Exception as error:
            raise MalformedScan(ScanProblem.UNREADABLE, str(error)) from error
        if len(sample) == 0:
            raise MalformedScan(ScanProblem.NO_POINTS)
        return sample.thinned(self.limits.maximum_points).ply()

    def sample(self) -> ScanSample:
        """
        :return: A random share of every scan's valid points, about
            :data:`OVERSAMPLING` times the builder's number of points.
        """
        file = pye57.E57(str(self.path))
        try:
            headers = [file.get_header(index) for index in range(file.scan_count)]
            total = sum(header.point_count for header in headers)
            share = min(1.0, OVERSAMPLING * self.limits.maximum_points / max(total, 1))
            generator = numpy.random.default_rng(self.seed)
            positions: List[numpy.ndarray] = []
            colors: List[numpy.ndarray] = []
            for header in headers:
                for chunk_positions, chunk_colors in self.read(
                    file, ScanPoints(header), share, generator
                ):
                    positions.append(chunk_positions)
                    colors.append(chunk_colors)
        finally:
            file.close()
        if not positions:
            return ScanSample(
                positions=numpy.empty((0, 3), numpy.float32),
                colors=numpy.empty((0, 3), numpy.uint8),
            )
        return ScanSample(
            positions=numpy.concatenate(positions), colors=numpy.concatenate(colors)
        )

    @staticmethod
    def read(
        file: pye57.E57,
        scan: ScanPoints,
        share: float,
        generator: numpy.random.Generator,
    ) -> List[Tuple[numpy.ndarray, numpy.ndarray]]:
        """
        :param file: The open E57 file.
        :param scan: The scan to read.
        :param share: The share of points sampled.
        :param generator: Draws the sample.
        :return: The sampled valid points of every chunk, with their colours.
        """
        fields = scan.fields()
        buffers_by_field, buffers = file.make_buffers(
            [field.value for field in fields], CHUNK_POINTS
        )
        reader = scan.header.points.reader(buffers)
        chunks = []
        try:
            count = reader.read()
            while count > 0:
                values = {
                    field: buffers_by_field[field.value][:count] for field in fields
                }
                chosen = (generator.random(count) < share) & scan.valid(values)
                chosen_values = {
                    field: value[chosen] for field, value in values.items()
                }
                positions = scan.positions(chosen_values).astype(numpy.float32)
                finite = numpy.isfinite(positions).all(axis=1)
                colors = scan.colors(chosen_values)
                chunks.append((positions[finite], colors[finite]))
                count = reader.read()
        finally:
            reader.close()
        return chunks


def scan_point_cloud(path: Path, limits: SceneBuilderLimits) -> bytes:
    """
    :param path: An E57 file.
    :param limits: The builder's limits.
    :return: The file as a PLY point cloud of at most the builder's number of points.
    :raises MalformedScan: When the file cannot be read or holds no valid point.
    """
    return E57Scan(path=path, limits=limits).point_cloud()
