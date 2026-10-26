"""
Keeping uploaded point clouds: each checked file is stored under the hash of its
content, with what checking found next to it, so uploading it again reuses it.

An uploaded scan is written to disk as it arrives and kept as the point cloud it is
turned into.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from importlib.machinery import ModuleSpec
from pathlib import Path

from typing_extensions import Callable, List, Optional

from cramera.http.messages import BodyStream
from cramera_protocol.scene_builder import (
    PointCloudFormat,
    ReservedResourceRoot,
    ScanFormat,
    SceneBuilderLimits,
)
from cramera_scene_builder.exceptions import (
    ContentTooLarge,
    IncompleteUpload,
    ScanConversionUnavailable,
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

    SCAN_PREFIX = ".scan-"
    """
    The hidden directory an uploaded scan is written to while it is converted.
    """


# %% scans

ScanConversion = Callable[[Path, SceneBuilderLimits], bytes]
"""
Turns a scan file into a PLY point cloud within the builder's limits.
"""

ModuleFinder = Callable[[str], Optional[ModuleSpec]]
"""
Finds a top-level module without importing it; :func:`importlib.util.find_spec` outside
of tests.
"""


class ScanModule(StrEnum):
    """
    The modules converting scans needs, the package's ``e57`` extra.
    """

    PYE57 = "pye57"
    """
    Reads E57 files.
    """

    NUMPY = "numpy"
    """
    Samples and thins the points.
    """


CONVERSION_MODULE = "cramera_scene_builder.scans"
"""
The module that converts scans, imported only when :class:`ScanModule` are installed.
"""


@dataclass(frozen=True)
class ScanModules:
    """
    Finds out whether the modules converting scans are installed.
    """

    finder: ModuleFinder = field(default=importlib.util.find_spec)
    """
    Finds a module without importing it.
    """

    def missing(self) -> List[str]:
        """
        :return: The names of the modules that are not installed.
        """
        return [
            module.value for module in ScanModule if self.finder(module.value) is None
        ]

    def conversion(self) -> ScanConversion:
        """
        :return: The function converting scans.
        :raises ScanConversionUnavailable: When a module it needs is missing.
        """
        missing = self.missing()
        if missing:
            raise ScanConversionUnavailable(missing)
        return importlib.import_module(CONVERSION_MODULE).scan_point_cloud


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

    scan_modules: ScanModules = field(default_factory=ScanModules)
    """
    Finds out whether uploaded scans can be converted.
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

    def keep_stream(
        self, file_format: PointCloudFormat, stream: BodyStream
    ) -> ResourceIdentifier:
        """
        Read an uploaded point cloud within the size limit, then keep it.

        :param file_format: The file's format.
        :param stream: The file's bytes as the client sends them.
        :return: The kept file's resource identifier.
        :raises ContentTooLarge: When the file is larger than the builder keeps.
        :raises IncompleteUpload: When the client stops before the declared length.
        """
        if stream.length > self.limits.maximum_point_cloud_bytes:
            raise ContentTooLarge(stream.length, self.limits.maximum_point_cloud_bytes)
        body = stream.read()
        if len(body) < stream.length:
            raise IncompleteUpload(len(body), stream.length)
        return self.keep(file_format, body)

    def keep_scan(
        self, scan_format: ScanFormat, stream: BodyStream
    ) -> ResourceIdentifier:
        """
        Write an uploaded scan to a hidden file chunk by chunk, turn it into a point
        cloud of at most :attr:`SceneBuilderLimits.maximum_points` points, keep that
        cloud as a PLY file and remove the scan.

        :param scan_format: The scan's format.
        :param stream: The scan's bytes as the client sends them.
        :return: The kept point cloud's resource identifier.
        :raises ScanConversionUnavailable: When the modules converting scans are
            missing.
        :raises ContentTooLarge: When the scan is larger than the builder reads.
        :raises IncompleteUpload: When the client stops before the declared length.
        :raises MalformedScan: When the scan cannot be read.
        """
        conversion = self.scan_modules.conversion()
        if stream.length > self.limits.maximum_scan_bytes:
            raise ContentTooLarge(stream.length, self.limits.maximum_scan_bytes)
        if self.directory.is_symlink():
            raise UnsafeStoragePath(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=self.directory, prefix=UploadFile.SCAN_PREFIX
        ) as scratch:
            scan = Path(scratch) / f"scan{scan_format.suffix()}"
            with scan.open("wb") as file:
                for chunk in stream.chunks():
                    file.write(chunk)
            if stream.read_bytes < stream.length:
                raise IncompleteUpload(stream.read_bytes, stream.length)
            cloud = conversion(scan, self.limits)
        return self.keep(PointCloudFormat.PLY, cloud)

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
