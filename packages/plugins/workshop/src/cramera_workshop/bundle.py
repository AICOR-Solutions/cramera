"""
The workshop's scene bundle: where it is, and what its scene description says about the
workshop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import List

from cramera.confinement import ConfinedDirectory
from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import ObjectDescription, SceneDescription
from cramera_protocol.workshop import (
    AssetRights,
    WorkshopDescription,
    WorkshopSemantics,
)
from cramera_workshop.exceptions import NotAWorkshopBundle

RESOURCES = Path(__file__).parent / "resources"
"""
The scenes directory of the bundles this package ships.
"""

# %% names


class WorkshopBundleName(StrEnum):
    """
    The bundles this package ships.
    """

    AICOR_WORKSHOP = "aicor_workshop"
    """
    The AICOR wood workshop.
    """


# %% bundle


@dataclass(frozen=True)
class WorkshopBundle:
    """
    A scene bundle that describes a workshop.
    """

    directory: Path
    """
    The bundle directory.
    """

    scene: SceneDescription
    """
    The bundle's scene description.
    """

    workshop: WorkshopDescription
    """
    The workshop the scene describes.
    """

    asset_rights: AssetRights
    """
    The rights of the bundle's original assets.
    """

    @classmethod
    def read(cls, directory: Path) -> WorkshopBundle:
        """
        :param directory: A bundle directory.
        :return: The bundle.
        :raises NotAWorkshopBundle: When the scene describes no workshop or names no
            asset rights.
        """
        scene = SceneDescription.from_json(
            json.loads((directory / BundleFile.SCENE).read_text(encoding="utf-8"))
        )
        workshop = WorkshopDescription.of_scene(scene.extensions)
        rights = AssetRights.of_scene(scene.extensions)
        if workshop is None or rights is None:
            raise NotAWorkshopBundle(directory)
        return cls(
            directory=directory, scene=scene, workshop=workshop, asset_rights=rights
        )

    @classmethod
    def packaged(cls) -> WorkshopBundle:
        """
        :return: The AICOR workshop this package ships.
        """
        return cls.read(RESOURCES / WorkshopBundleName.AICOR_WORKSHOP)

    @classmethod
    def shown_or_packaged(cls, catalog: SceneCatalog) -> WorkshopBundle:
        """
        :param catalog: The scenes the viewer shows.
        :return: The AICOR workshop the viewer shows, so the contact world matches the
            geometry on screen; the packaged one when the viewer shows none.
        """
        name = WorkshopBundleName.AICOR_WORKSHOP
        if catalog.index().entry(name) is None:
            return cls.packaged()
        return cls.read(catalog.directory_of(name).path / name)

    def file(self, relative: str) -> Path:
        """
        :param relative: A file of the bundle, relative to its directory.
        :return: The file.
        :raises PathOutsideDirectory: When the path leaves the bundle.
        :raises FileNotInDirectory: When the bundle has no such file.
        """
        return ConfinedDirectory(self.directory).file(relative)

    def semantics(self) -> WorkshopSemantics:
        """
        :return: The bundle's handle frames.
        """
        return WorkshopSemantics.from_json(
            json.loads(self.file(BundleFile.SEMANTICS).read_text(encoding="utf-8"))
        )

    def movable_objects(self) -> List[ObjectDescription]:
        """
        :return: The scene's objects that have a URDF of their own, in scene order.
        """
        return [item for item in self.scene.objects if item.urdf is not None]
