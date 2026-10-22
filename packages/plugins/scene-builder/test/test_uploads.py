"""
Keeping uploaded point clouds under the hash of their content.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from cramera_protocol.scene_builder import (
    PointCloudFormat,
    PointCloudMetadata,
    ReservedResourceRoot,
)
from cramera_scene_builder.exceptions import (
    ContentTooLarge,
    MalformedPointCloud,
    StoredContentMismatch,
    UnsafeStoragePath,
)
from cramera_scene_builder.point_clouds import PointCloudFile
from cramera_scene_builder.resources import PointCloudMetadataFile
from cramera_scene_builder.uploads import PointCloudStore

from .conftest import DATASET

CLOUD = DATASET / "point_clouds" / "colored_ascii.ply"
"""
A valid point cloud to upload.
"""


@pytest.fixture
def store(storage, limits) -> PointCloudStore:
    return PointCloudStore(storage.point_clouds, limits)


def test_a_kept_cloud_is_named_after_its_content(store, limits):
    body = CLOUD.read_bytes()
    identifier = store.keep(PointCloudFormat.PLY, body)
    expected = f"{hashlib.sha256(body).hexdigest()}{PointCloudFormat.PLY.suffix()}"
    assert (identifier.root, identifier.path) == (
        ReservedResourceRoot.POINT_CLOUDS,
        expected,
    )
    assert (store.directory / expected).read_bytes() == body


def test_what_checking_found_is_kept_next_to_the_cloud(store, limits):
    body = CLOUD.read_bytes()
    identifier = store.keep(PointCloudFormat.PLY, body)
    kept = PointCloudMetadataFile(store.directory / identifier.path).read()
    assert kept == PointCloudFile(PointCloudFormat.PLY, body, limits).check()


def test_uploading_the_same_cloud_again_reuses_it(store):
    body = CLOUD.read_bytes()
    assert store.keep(PointCloudFormat.PLY, body) == store.keep(
        PointCloudFormat.PLY, body
    )
    assert len(list(store.directory.glob(f"*{PointCloudFormat.PLY.suffix()}"))) == 1


def test_a_malformed_cloud_is_not_kept(store):
    with pytest.raises(MalformedPointCloud):
        store.keep(PointCloudFormat.PCD, CLOUD.read_bytes())
    assert not store.directory.exists()


def test_a_cloud_larger_than_the_limit_is_refused(store):
    body = CLOUD.read_bytes()
    bounded = replace(store, limits=replace(store.limits, maximum_point_cloud_bytes=8))
    with pytest.raises(ContentTooLarge) as refused:
        bounded.keep(PointCloudFormat.PLY, body)
    assert (refused.value.size, refused.value.limit) == (
        len(body),
        bounded.limits.maximum_point_cloud_bytes,
    )


def test_a_kept_file_of_another_content_is_refused(store):
    body = CLOUD.read_bytes()
    identifier = store.keep(PointCloudFormat.PLY, body)
    (store.directory / identifier.path).write_bytes(b"changed")
    with pytest.raises(StoredContentMismatch):
        store.keep(PointCloudFormat.PLY, body)


def test_a_linked_storage_directory_is_refused(store, workspace):
    target = workspace / "elsewhere"
    target.mkdir()
    store.directory.parent.mkdir(parents=True)
    store.directory.symlink_to(target)
    with pytest.raises(UnsafeStoragePath):
        store.keep(PointCloudFormat.PLY, CLOUD.read_bytes())


def test_a_linked_metadata_file_is_refused(store, workspace):
    body = CLOUD.read_bytes()
    identifier = store.keep(PointCloudFormat.PLY, body)
    metadata = PointCloudMetadataFile(store.directory / identifier.path).path()
    metadata.unlink()
    metadata.symlink_to(workspace / "elsewhere.json")
    with pytest.raises(UnsafeStoragePath):
        store.keep(PointCloudFormat.PLY, body)


def test_a_cloud_without_metadata_is_listed_without_it(store, library):
    body = CLOUD.read_bytes()
    identifier = store.keep(PointCloudFormat.PLY, body)
    PointCloudMetadataFile(store.directory / identifier.path).path().unlink()
    assert library.resource(identifier).point_cloud is None


def test_a_listed_cloud_carries_its_metadata(store, library):
    identifier = store.keep(PointCloudFormat.PLY, CLOUD.read_bytes())
    metadata_file = PointCloudMetadataFile(store.directory / identifier.path).path()
    assert library.resource(identifier).point_cloud == PointCloudMetadata.from_json(
        json.loads(metadata_file.read_text(encoding="utf-8"))
    )
