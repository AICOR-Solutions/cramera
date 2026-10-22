"""
The laboratories the plugin ships and their installation into the viewer's local scenes.

A laboratory is a scene bundle whose ``scene.json`` adds the bench, and for the expanded
room the instrument collection. Installing copies the bundle without its Blender
sources, so the viewer shows it like any recording.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Tuple

from cramera.locations import DataLocations
from cramera_laboratory.scene_files import LocalSceneIndex
from cramera_laboratory.exceptions import (
    MissingLaboratoryBundle,
    NotALaboratory,
    UnknownLaboratory,
)
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.laboratory.layout import (
    BenchLayout,
    InstrumentCollection,
    LaboratorySceneKey,
)
from cramera_protocol.rights import AssetRights

RESOURCES_DIRECTORY = Path(__file__).parent / "resources"
"""
The assets the plugin ships.
"""

STAGING_PREFIX = ".install_"
"""
The prefix of the folder a laboratory is copied into before it takes its place.
"""

# %% names


class LaboratoryResource(StrEnum):
    """
    The folders of :data:`RESOURCES_DIRECTORY`.
    """

    BENCH = "aicor_medical_lab"
    """
    The bench laboratory: one workbench with its instruments.
    """

    EXPANDED = "aicor_medical_lab_large"
    """
    The expanded laboratory room with its workstations and fifteen more instruments.
    """

    DEVICES = "laboratory_devices"
    """
    The independent device folders.
    """

    MANUALS = "centrifuge_manuals"
    """
    The centrifuge manual editions.
    """


class AuthoringFile(StrEnum):
    """
    The file patterns of authoring sources an installed laboratory leaves out.
    """

    BLENDER = "*.blend"
    """
    Blender scenes.
    """

    BLENDER_BACKUP = "*.blend1"
    """
    Blender's backups.
    """


class RightsFile(StrEnum):
    """
    The rights record beside each asset folder.
    """

    RECORD = "rights.json"
    """
    The machine-readable record.
    """


# %% one laboratory


@dataclass
class LaboratoryBundle:
    """
    A laboratory scene bundle: its scene description with the bench it adds.
    """

    directory: Path
    """
    The bundle directory.
    """

    description: SceneDescription = field(init=False)
    """
    The bundle's scene description.
    """

    def __post_init__(self) -> None:
        self.directory = Path(self.directory).expanduser().resolve()
        scene_file = self.directory / BundleFile.SCENE
        if not scene_file.is_file():
            raise MissingLaboratoryBundle(self.directory)
        self.description = SceneDescription.from_json(
            json.loads(scene_file.read_text(encoding="utf-8"))
        )
        if LaboratorySceneKey.LABORATORY not in self.description.extensions:
            raise NotALaboratory(self.directory)

    @property
    def name(self) -> str:
        """
        The bundle's folder name.
        """
        return self.directory.name

    def title(self) -> str:
        """
        :return: The laboratory's display name.
        """
        return self.description.environment_name or self.description.name

    def bench(self) -> BenchLayout:
        """
        :return: The bench the bundle adds.
        """
        return BenchLayout.from_json(
            self.description.extensions[LaboratorySceneKey.LABORATORY]
        )

    def instruments(self) -> Optional[InstrumentCollection]:
        """
        :return: The expanded room's instrument collection, None for the bench alone.
        """
        data = self.description.extensions.get(LaboratorySceneKey.INSTRUMENTS)
        return None if data is None else InstrumentCollection.from_json(data)

    def asset_rights(self) -> AssetRights:
        """
        :return: The terms of the bundle's assets, from its rights record.
        """
        return AssetRights.from_json(
            json.loads((self.directory / RightsFile.RECORD).read_text(encoding="utf-8"))
        )

    def copy_to(self, destination: Path) -> None:
        """
        Copy the bundle with every notice and licence, but without its authoring
        sources, so a person's copy carries the assets' terms.

        :param destination: The new bundle folder, which must not exist.
        """
        shutil.copytree(
            self.directory,
            destination,
            ignore=shutil.ignore_patterns(*AuthoringFile),
        )


# %% shelf


@dataclass(frozen=True)
class LaboratoryShelf:
    """
    The laboratories the plugin ships.
    """

    directory: Path = RESOURCES_DIRECTORY
    """
    The folder holding the laboratory bundles.
    """

    names: Tuple[str, ...] = (LaboratoryResource.BENCH, LaboratoryResource.EXPANDED)
    """
    The laboratories' folder names, in the order they are offered.
    """

    def laboratories(self) -> List[LaboratoryBundle]:
        """
        :return: Every laboratory, in the order they are offered.
        """
        return [LaboratoryBundle(self.directory / name) for name in self.names]

    def laboratory(self, name: str) -> LaboratoryBundle:
        """
        :param name: A laboratory's folder name.
        :return: The laboratory.
        :raises UnknownLaboratory: When the shelf has no such laboratory.
        """
        if name not in self.names:
            raise UnknownLaboratory(name, [str(known) for known in self.names])
        return LaboratoryBundle(self.directory / name)


# %% installation


@dataclass(frozen=True)
class LaboratoryInstallation:
    """
    Copies laboratories into the viewer's local scenes and registers them in its index,
    so the scene picker offers them.
    """

    locations: DataLocations
    """
    Where the viewer keeps its scenes.
    """

    def installed(self, name: str) -> bool:
        """
        :param name: A bundle name.
        :return: Whether the local scenes hold a bundle of that name.
        """
        return (self.locations.local_scenes / name / BundleFile.SCENE).is_file()

    def install(self, laboratory: LaboratoryBundle, name: str) -> str:
        """
        Copy a laboratory under a name unless the local scenes hold it already.

        The copy is staged beside its destination and moved in whole, so the scenes
        directory never holds half a laboratory.

        :param laboratory: The laboratory.
        :param name: The bundle name to install it as.
        :return: The bundle name.
        """
        if self.installed(name):
            return name
        scenes = self.locations.local_scenes
        scenes.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f"{STAGING_PREFIX}{name}.", dir=scenes))
        laboratory.copy_to(staging / name)
        (staging / name).rename(scenes / name)
        staging.rmdir()
        self.register(laboratory.description, name)
        return name

    def register(self, description: SceneDescription, name: str) -> None:
        """
        :param description: The installed bundle's description.
        :param name: The installed bundle's name.
        """
        LocalSceneIndex(self.locations.local_scenes).register(
            SceneIndexEntry(
                name=name,
                robot=description.robot_name or "",
                environment=description.environment_name,
                task=description.task,
            )
        )
