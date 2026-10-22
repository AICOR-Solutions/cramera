"""
Where a bundle keeps its files: the URDF and mesh directory of each model, and the mesh
of each object.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path, PurePosixPath

from cramera_protocol.bundle.files import BundleFile, MeshFormat
from cramera_usd.animation.models import KinematicModel

# %% vocabulary


class FileSuffix(StrEnum):
    """
    The suffixes of the files a bundle holds besides its meshes.
    """

    URDF = ".urdf"
    """
    A model description.
    """


class Decimals(IntEnum):
    """
    The decimals a bundle keeps of its numbers, by what they measure.
    """

    POSITION = 4
    """
    Positions, sizes and directions in metres or unit vectors.
    """

    FIELD_OF_VIEW = 3
    """
    A field of view in degrees.
    """

    CLIP_DISTANCE = 2
    """
    A clipping distance in metres.
    """

    POSE = 6
    """
    The poses of the trajectory.
    """

    DURATION = 3
    """
    Durations in seconds.
    """

    RESIDUAL = 4
    """
    The largest distances and angles of a replay.
    """


ANY_NAME = "*"
"""
The glob pattern matching every name.
"""

# %% layout


@dataclass(frozen=True)
class BundleLayout:
    """
    The files of one bundle directory.
    """

    directory: Path
    """
    The bundle directory.
    """

    def file(self, relative: str) -> Path:
        """
        :param relative: A path relative to the bundle.
        :return: The file in the bundle directory.
        """
        return self.directory / relative

    @staticmethod
    def urdf_file(model: KinematicModel) -> str:
        """
        :param model: A model of the bundle.
        :return: Its URDF file, relative to the bundle: the environment's fixed name, a
            robot's own name.
        """
        if model.robot:
            return f"{model.name}{FileSuffix.URDF}"
        return BundleFile.ENVIRONMENT.value

    @staticmethod
    def mesh_directory(model: KinematicModel) -> PurePosixPath:
        """
        :param model: A model of the bundle.
        :return: The directory of its GLBs, relative to the bundle (and to the URDF).
        """
        meshes = PurePosixPath(BundleFile.MESHES)
        if model.robot:
            return meshes / model.name
        return meshes

    @classmethod
    def mesh_file(cls, model: KinematicModel, link: str) -> str:
        """
        :param model: A model of the bundle.
        :param link: The name of one of its links.
        :return: The link's GLB, relative to the bundle.
        """
        return str(cls.mesh_directory(model) / f"{link}{MeshFormat.GLB}")

    @staticmethod
    def object_mesh(key: str) -> str:
        """
        :param key: An object's key.
        :return: The object's GLB, relative to the bundle.
        """
        return str(PurePosixPath(BundleFile.OBJECT_MESHES) / f"{key}{MeshFormat.GLB}")

    def size(self) -> int:
        """
        :return: The number of bytes the bundle's files take on disk.
        """
        return sum(
            path.stat().st_size
            for path in self.directory.rglob(ANY_NAME)
            if path.is_file()
        )
