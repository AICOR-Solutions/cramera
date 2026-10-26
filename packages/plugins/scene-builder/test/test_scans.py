"""
Turning E57 laser scans into point clouds, and keeping uploaded scans as such clouds.
"""

from __future__ import annotations

import io
import json
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace

import pytest

numpy = pytest.importorskip("numpy")
pye57 = pytest.importorskip("pye57")

from cramera.http.messages import BodyStream
from cramera_protocol.scene_builder import (
    PointCloudFormat,
    ReservedResourceRoot,
    ResourceDescription,
    ResourceKind,
    ScanFormat,
    SceneBuilderCatalog,
    SceneBuilderLimits,
    SceneBuilderRoute,
)
from cramera_scene_builder.exceptions import (
    ContentTooLarge,
    IncompleteUpload,
    MalformedScan,
    ScanConversionUnavailable,
    ScanProblem,
    UnsafeStoragePath,
)
from cramera_scene_builder.point_clouds import PointCloudFile
from cramera_scene_builder.scans import E57Field, E57Scan, ScanPoints, ScanSample
from cramera_scene_builder.uploads import PointCloudStore, ScanModule, ScanModules

# %% scan files


def write_scan(
    path: Path,
    positions: numpy.ndarray,
    colors: numpy.ndarray = None,
    intensities: numpy.ndarray = None,
    invalid: numpy.ndarray = None,
    translation=(0.0, 0.0, 0.0),
) -> Path:
    """
    :return: An E57 file of one scan of the given points, placed by the translation.
    """
    data = {
        E57Field.CARTESIAN_X.value: positions[:, 0].astype(float),
        E57Field.CARTESIAN_Y.value: positions[:, 1].astype(float),
        E57Field.CARTESIAN_Z.value: positions[:, 2].astype(float),
    }
    if colors is not None:
        for channel, field in enumerate(
            (E57Field.COLOR_RED, E57Field.COLOR_GREEN, E57Field.COLOR_BLUE)
        ):
            data[field.value] = colors[:, channel].astype(numpy.uint8)
    if intensities is not None:
        data[E57Field.INTENSITY.value] = intensities.astype(float)
    if invalid is not None:
        data[E57Field.CARTESIAN_INVALID_STATE.value] = invalid.astype(numpy.int8)
    file = pye57.E57(str(path), mode="w")
    file.write_scan_raw(
        data,
        name="scan",
        rotation=numpy.array([1.0, 0, 0, 0]),
        translation=numpy.array(translation),
    )
    file.close()
    return path


def grid(count: int) -> numpy.ndarray:
    """
    :return: ``count`` points spread over a room of 4 by 3 by 2.5 metres.
    """
    generator = numpy.random.default_rng(1)
    return generator.random((count, 3)) * numpy.array([4.0, 3.0, 2.5])


def kept_points(body: bytes, limits: SceneBuilderLimits) -> int:
    """
    :return: The number of points of a written cloud, after the builder checked it.
    """
    return PointCloudFile(PointCloudFormat.PLY, body, limits).check().point_count


@pytest.fixture
def small_limits(limits) -> SceneBuilderLimits:
    """
    :return: Limits keeping at most 500 points.
    """
    return replace(limits, maximum_points=500)


# %% conversion


def test_a_scan_becomes_a_cloud_the_builder_reads(tmp_path, limits):
    positions = grid(100)
    colors = numpy.tile(numpy.array([[10, 120, 230]]), (100, 1))
    path = write_scan(tmp_path / "room.e57", positions, colors=colors)
    sample = E57Scan(path, limits).sample()
    assert len(sample) == 100
    assert numpy.allclose(
        numpy.sort(sample.positions, axis=0), numpy.sort(positions, axis=0), atol=1e-5
    )
    assert (sample.colors == [10, 120, 230]).all()
    assert kept_points(E57Scan(path, limits).point_cloud(), limits) == 100


def test_a_scan_is_placed_by_its_pose(tmp_path, limits):
    positions = grid(10)
    path = write_scan(tmp_path / "moved.e57", positions, translation=(1.0, 2.0, -135.0))
    sample = E57Scan(path, limits).sample()
    expected = positions + numpy.array([1.0, 2.0, -135.0])
    assert numpy.allclose(
        numpy.sort(sample.positions, axis=0), numpy.sort(expected, axis=0), atol=1e-4
    )


def test_a_large_scan_is_thinned_to_the_builders_number_of_points(
    tmp_path, small_limits
):
    path = write_scan(tmp_path / "large.e57", grid(20_000))
    count = kept_points(E57Scan(path, small_limits).point_cloud(), small_limits)
    assert 0.5 * small_limits.maximum_points <= count <= small_limits.maximum_points


def test_thinning_keeps_points_spread_over_the_whole_scan():
    positions = numpy.concatenate([numpy.zeros((5000, 3)), numpy.ones((10, 3)) * 5])
    sample = ScanSample(
        positions=positions.astype(numpy.float32),
        colors=numpy.zeros((len(positions), 3), numpy.uint8),
    )
    thinned = sample.thinned(maximum=4)
    assert len(thinned) == 2
    assert {tuple(row) for row in thinned.positions} == {(0, 0, 0), (5, 5, 5)}


def test_points_of_an_invalid_state_are_left_out(tmp_path, limits):
    invalid = numpy.array([0, 2, 0, 1])
    path = write_scan(tmp_path / "partly.e57", grid(4), invalid=invalid)
    assert len(E57Scan(path, limits).sample()) == 2


def test_intensities_become_grey_where_a_scan_has_no_colours(tmp_path, limits):
    path = write_scan(
        tmp_path / "grey.e57", grid(3), intensities=numpy.array([0.0, 0.5, 1.0])
    )
    sample = E57Scan(path, limits).sample()
    assert sorted(sample.colors[:, 0].tolist()) == [0, 127, 255]
    assert (sample.colors[:, 0] == sample.colors[:, 2]).all()


def test_a_scan_without_colours_or_intensities_is_grey():
    scan = ScanPoints(SimpleNamespace(point_fields=[]))
    values = {E57Field.CARTESIAN_X: numpy.zeros(2)}
    assert scan.colors(values).tolist() == [[200, 200, 200], [200, 200, 200]]


def test_spherical_points_are_turned_into_coordinates():
    header = SimpleNamespace(
        point_fields=[
            field.value
            for field in (
                E57Field.SPHERICAL_RANGE,
                E57Field.SPHERICAL_AZIMUTH,
                E57Field.SPHERICAL_ELEVATION,
            )
        ],
        rotation_matrix=numpy.eye(3),
        translation=numpy.zeros(3),
    )
    scan = ScanPoints(header)
    assert E57Field.SPHERICAL_RANGE in scan.fields()
    values = {
        E57Field.SPHERICAL_RANGE: numpy.array([2.0, 1.0]),
        E57Field.SPHERICAL_AZIMUTH: numpy.array([numpy.pi / 2, 0.0]),
        E57Field.SPHERICAL_ELEVATION: numpy.array([0.0, numpy.pi / 2]),
    }
    assert numpy.allclose(scan.positions(values), [[0, 2, 0], [0, 0, 1]], atol=1e-9)


def test_a_scan_without_coordinates_is_refused():
    with pytest.raises(MalformedScan) as refused:
        ScanPoints(SimpleNamespace(point_fields=[E57Field.INTENSITY.value])).fields()
    assert refused.value.problem is ScanProblem.NO_COORDINATES


def test_a_file_that_is_no_scan_is_refused(tmp_path, limits):
    path = tmp_path / "notes.e57"
    path.write_bytes(b"these are not scanned points")
    with pytest.raises(MalformedScan) as refused:
        E57Scan(path, limits).point_cloud()
    assert refused.value.problem is ScanProblem.UNREADABLE
    assert "cannot be read" in refused.value.message()


def test_a_scan_without_valid_points_is_refused(tmp_path, limits, monkeypatch):
    # pye57 writes no scan without a valid point, so the reading is left out
    empty = ScanSample(
        positions=numpy.empty((0, 3), numpy.float32),
        colors=numpy.empty((0, 3), numpy.uint8),
    )
    monkeypatch.setattr(E57Scan, "sample", lambda scan: empty)
    with pytest.raises(MalformedScan) as refused:
        E57Scan(tmp_path / "invalid.e57", limits).point_cloud()
    assert refused.value.problem is ScanProblem.NO_POINTS


# %% uploads


@pytest.fixture
def store(storage, limits) -> PointCloudStore:
    return PointCloudStore(storage.point_clouds, limits)


def stream_of(body: bytes, length: int = None) -> BodyStream:
    """
    :return: A request body of the bytes, declared ``length`` long.
    """
    return BodyStream(
        source=io.BytesIO(body), length=len(body) if length is None else length
    )


def test_an_uploaded_scan_is_kept_as_a_ply_cloud(store, tmp_path, limits):
    body = write_scan(tmp_path / "room.e57", grid(50)).read_bytes()
    identifier = store.keep_scan(ScanFormat.E57, stream_of(body))
    assert identifier.root == ReservedResourceRoot.POINT_CLOUDS
    assert identifier.path.endswith(PointCloudFormat.PLY.suffix())
    kept = (store.directory / identifier.path).read_bytes()
    assert kept_points(kept, limits) == 50
    assert [
        path.name
        for path in store.directory.iterdir()
        if path.name.startswith(".scan-")
    ] == []


def test_a_scan_upload_without_the_conversion_modules_is_refused(storage, limits):
    finder = lambda name: None if name == ScanModule.PYE57 else object()
    store = PointCloudStore(storage.point_clouds, limits, ScanModules(finder))
    with pytest.raises(ScanConversionUnavailable) as refused:
        store.keep_scan(ScanFormat.E57, stream_of(b"scan"))
    assert refused.value.missing == ["pye57"]
    assert "cramera-scene-builder[e57]" in refused.value.message()


def test_a_scan_larger_than_the_limit_is_refused_before_it_is_read(storage, limits):
    store = PointCloudStore(storage.point_clouds, replace(limits, maximum_scan_bytes=3))
    stream = stream_of(b"four")
    with pytest.raises(ContentTooLarge):
        store.keep_scan(ScanFormat.E57, stream)
    assert stream.read_bytes == 0


def test_a_scan_upload_into_a_linked_directory_is_refused(storage, limits, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    storage.point_clouds.parent.mkdir(parents=True, exist_ok=True)
    storage.point_clouds.symlink_to(target)
    store = PointCloudStore(storage.point_clouds, limits)
    with pytest.raises(UnsafeStoragePath):
        store.keep_scan(ScanFormat.E57, stream_of(b"scan"))


def test_a_scan_upload_that_ends_early_is_refused(store):
    with pytest.raises(IncompleteUpload) as refused:
        store.keep_scan(ScanFormat.E57, stream_of(b"half", length=8))
    assert (refused.value.received, refused.value.declared) == (4, 8)


def test_a_point_cloud_upload_that_ends_early_is_refused(store):
    with pytest.raises(IncompleteUpload):
        store.keep_stream(PointCloudFormat.PLY, stream_of(b"ply\n", length=8))


def test_a_streamed_point_cloud_larger_than_the_limit_is_refused(storage, limits):
    store = PointCloudStore(
        storage.point_clouds, replace(limits, maximum_point_cloud_bytes=3)
    )
    with pytest.raises(ContentTooLarge):
        store.keep_stream(PointCloudFormat.PLY, stream_of(b"four"))


def test_an_uploaded_scan_joins_the_library_as_a_ply_cloud(get, post, tmp_path):
    body = write_scan(tmp_path / "room.e57", grid(20)).read_bytes()
    answer = post(f"{SceneBuilderRoute.POINT_CLOUDS}{ScanFormat.E57}", body)
    assert answer.status is HTTPStatus.OK, answer.body
    uploaded = ResourceDescription.from_json(json.loads(answer.body))
    offered = SceneBuilderCatalog.from_json(
        json.loads(get(SceneBuilderRoute.CATALOG).body)
    )
    assert uploaded.kind is ResourceKind.POINT_CLOUD
    assert uploaded.point_cloud.file_format is PointCloudFormat.PLY
    assert uploaded in offered.resources


def test_a_malformed_scan_upload_is_unprocessable(post):
    answer = post(f"{SceneBuilderRoute.POINT_CLOUDS}{ScanFormat.E57}", b"no scan")
    assert answer.status is HTTPStatus.UNPROCESSABLE_ENTITY
