"""
Keeping uploaded point clouds: each checked file is stored under the hash of its
content, with what checking found next to it, so uploading it again reuses it.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cramera_protocol.scene_builder import (
    PointCloudFormat,
    ReservedResourceRoot,
    SceneBuilderLimits,
)
from cramera_scene_builder.exceptions import (
    ContentTooLarge,
    StoredContentMismatch,
    UnsafeStoragePath,
)
from cramera_scene_builder.point_clouds import PointCloudFile
from cramera_scene_builder.resources import PointCloudMetadataFile, ResourceIdentifier

# %% files


class UploadFile(StrEnum):
    """
    The prefixes of files being written to the point cloud directory.
    """

    POINT_CLOUD_PREFIX = ".upload-"
    """
    A point cloud being written, hidden until it is complete.
    """

    METADATA_PREFIX = ".metadata-"
    """
    A description being written, hidden until it is complete.
    """


# %% store


@dataclass(frozen=True)
class PointCloudStore:
    """
    The directory of uploaded point clouds, the library's root
    :attr:`ReservedResourceRoot.POINT_CLOUDS`.
    """

    directory: Path
    """
    The point cloud directory.
    """

    limits: SceneBuilderLimits
    """
    The builder's limits.
    """

    def keep(self, file_format: PointCloudFormat, body: bytes) -> ResourceIdentifier:
        """
        Check every record of an uploaded file, then keep it.

        :param file_format: The file's format.
        :param body: The file's bytes.
        :return: The kept file's resource identifier.
        :raises ContentTooLarge: When the file is larger than the builder keeps.
        :raises MalformedPointCloud: When the file cannot be read.
        :raises TooManyPoints: When the file declares too many points.
        :raises UnsafeStoragePath: When a storage location is a symbolic link.
        :raises StoredContentMismatch: When a kept file of the same name has another
            content.
        """
        if len(body) > self.limits.maximum_point_cloud_bytes:
            raise ContentTooLarge(len(body), self.limits.maximum_point_cloud_bytes)
        metadata = PointCloudFile(file_format, body, self.limits).check()
        if self.directory.is_symlink():
            raise UnsafeStoragePath(self.directory)
        name = f"{hashlib.sha256(body).hexdigest()}{file_format.suffix()}"
        target = self.directory / name
        if target.is_symlink():
            raise UnsafeStoragePath(target)
        self.directory.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            self.write(target, body, UploadFile.POINT_CLOUD_PREFIX)
        elif not target.is_file() or target.read_bytes() != body:
            raise StoredContentMismatch(target)
        metadata_file = PointCloudMetadataFile(target).path()
        if metadata_file.is_symlink():
            raise UnsafeStoragePath(metadata_file)
        text = json.dumps(metadata.to_json(), allow_nan=False) + "\n"
        self.write(metadata_file, text.encode("utf-8"), UploadFile.METADATA_PREFIX)
        return ResourceIdentifier(ReservedResourceRoot.POINT_CLOUDS, name)

    def write(self, target: Path, content: bytes, prefix: UploadFile) -> None:
        """
        :param target: Where the content goes.
        :param content: The content.
        :param prefix: The prefix of the hidden file the content is written to first.
        """
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=self.directory, prefix=prefix, delete=False
        ) as temporary:
            temporary.write(content)
        os.replace(temporary.name, target)
