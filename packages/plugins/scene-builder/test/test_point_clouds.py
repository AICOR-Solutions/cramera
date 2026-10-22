"""
Reading PLY and PCD point clouds within bounds, and the display samples the browser
receives.
"""

from __future__ import annotations

import struct
from array import array
from dataclasses import replace

import pytest

from cramera_protocol.scene_builder import PointCloudEncoding, PointCloudFormat
from cramera_scene_builder.exceptions import (
    MalformedPointCloud,
    PointCloudProblem,
    TooManyPoints,
)
from cramera_scene_builder.point_clouds import (
    SAMPLE_HEADER,
    SAMPLE_VALUE,
    PointCloudFile,
)
from cramera_scene_builder.resources import POINT_CLOUD_FORMATS

from .conftest import DATASET

POINT_CLOUDS = DATASET / "point_clouds"
"""
The point cloud files of the tests.
"""

COLORED_CLOUDS = {
    "colored_ascii.ply": PointCloudEncoding.ASCII,
    "colored_binary_le.ply": PointCloudEncoding.BINARY_LITTLE_ENDIAN,
    "colored_binary_be.ply": PointCloudEncoding.BINARY_BIG_ENDIAN,
    "colored_ascii.pcd": PointCloudEncoding.ASCII,
    "colored_binary.pcd": PointCloudEncoding.BINARY,
}
"""
The same three coloured points in every encoding the builder reads.
"""

COLORED_POSITIONS = [1.0, 2.0, 3.0, -4.0, 0.5, 6.0, 7.0, 8.0, 9.0]
"""
The positions of the coloured clouds' points, as their ASCII files write them.
"""

COLORED_COLORS = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
"""
The colours of the coloured clouds' points: red, green and blue.
"""


def cloud(name: str, limits) -> PointCloudFile:
    path = POINT_CLOUDS / name
    return PointCloudFile(POINT_CLOUD_FORMATS[path.suffix], path.read_bytes(), limits)


# %% metadata


@pytest.mark.parametrize("name, encoding", COLORED_CLOUDS.items())
def test_every_encoding_is_read(limits, name, encoding):
    metadata = cloud(name, limits).check()
    assert metadata.encoding is encoding
    assert metadata.file_format is POINT_CLOUD_FORMATS[(POINT_CLOUDS / name).suffix]
    assert metadata.point_count == metadata.finite_point_count == 3


def test_points_with_missing_coordinates_are_counted_apart(limits):
    metadata = cloud("missing_measurements.pcd", limits).check()
    assert (metadata.point_count, metadata.finite_point_count) == (3, 1)


# %% samples


@pytest.mark.parametrize("name", COLORED_CLOUDS)
def test_a_sample_holds_positions_and_colors_in_the_files_coordinates(limits, name):
    sample = cloud(name, limits).sample()
    assert list(sample.positions) == COLORED_POSITIONS
    assert list(sample.colors) == pytest.approx(COLORED_COLORS)


def test_a_sample_leaves_out_missing_measurements(limits):
    sample = cloud("missing_measurements.pcd", limits).sample()
    assert list(sample.positions) == [4.0, 5.0, 6.0]
    assert sample.colors is None


def test_a_sample_keeps_every_nth_point_within_its_limit(limits):
    bounded = replace(limits, maximum_sample_points=2)
    sample = cloud("many_points.ply", bounded).sample()
    assert sample.point_count() == 2
    assert list(sample.positions) == [0.0, 0.0, 0.0, 3.0, 0.0, 0.0]


def test_sample_bytes_start_with_the_count_and_whether_colors_follow(limits):
    sample = cloud("colored_ascii.ply", limits).sample()
    data = sample.to_bytes()
    count, colored = SAMPLE_HEADER.unpack_from(data)
    values = array(SAMPLE_VALUE)
    values.frombytes(data[SAMPLE_HEADER.size :])
    assert (count, colored) == (sample.point_count(), 1)
    assert list(values) == pytest.approx(COLORED_POSITIONS + COLORED_COLORS)


# %% refusals


@pytest.mark.parametrize(
    "name, problem",
    [
        ("empty.ply", PointCloudProblem.EMPTY),
        ("unterminated_header.ply", PointCloudProblem.HEADER_INCOMPLETE),
        ("not_ply.ply", PointCloudProblem.NOT_PLY),
        ("faces.ply", PointCloudProblem.NOT_VERTICES),
        ("list_property.ply", PointCloudProblem.LIST_PROPERTY),
        ("unknown_scalar.ply", PointCloudProblem.UNKNOWN_SCALAR_TYPE),
        ("unknown_declaration.ply", PointCloudProblem.UNKNOWN_DECLARATION),
        ("missing_z.ply", PointCloudProblem.MISSING_COORDINATES),
        ("truncated.ply", PointCloudProblem.TRUNCATED),
        ("truncated_binary.ply", PointCloudProblem.TRUNCATED),
        ("short_record.ply", PointCloudProblem.RECORD_SHAPE),
        ("not_a_number.ply", PointCloudProblem.INVALID_NUMBER),
        ("channel_out_of_range.ply", PointCloudProblem.INVALID_NUMBER),
        ("infinite.ply", PointCloudProblem.COORDINATE_OUT_OF_RANGE),
        ("compressed.pcd", PointCloudProblem.UNSUPPORTED_ENCODING),
        ("old_version.pcd", PointCloudProblem.UNSUPPORTED_VERSION),
        ("dimension_mismatch.pcd", PointCloudProblem.DIMENSION_MISMATCH),
        ("no_finite_points.pcd", PointCloudProblem.NO_FINITE_POINTS),
        ("short_viewpoint.pcd", PointCloudProblem.INVALID_VIEWPOINT),
        ("narrow_color.pcd", PointCloudProblem.INVALID_COLOR),
        ("inconsistent_fields.pcd", PointCloudProblem.INVALID_FIELDS),
    ],
)
def test_malformed_files_are_refused_with_their_problem(limits, name, problem):
    with pytest.raises(MalformedPointCloud) as refused:
        cloud(f"invalid/{name}", limits).check()
    assert refused.value.problem is problem


def test_a_cloud_declaring_too_many_points_is_refused(limits):
    bounded = replace(limits, maximum_points=4)
    with pytest.raises(TooManyPoints) as refused:
        cloud("many_points.ply", bounded).check()
    assert (refused.value.count, refused.value.limit) == (5, bounded.maximum_points)


def test_binary_records_are_read_in_the_declared_byte_order(limits):
    body = (POINT_CLOUDS / "colored_binary_be.ply").read_bytes()
    header, records = body.split(b"end_header\n")
    first = struct.unpack_from(">fff", records)
    assert list(PointCloudFile(PointCloudFormat.PLY, body, limits).sample().positions)[
        :3
    ] == list(first)


@pytest.mark.parametrize("name", ["colored_ascii.ply", "missing_measurements.pcd"])
def test_the_browser_tests_decode_the_samples_the_server_writes(limits, name):
    browser_fixture = (
        DATASET.parent / "js" / "dataset" / f"{name.split('.')[0]}_sample.bin"
    )
    assert cloud(name, limits).sample().to_bytes() == browser_fixture.read_bytes()
