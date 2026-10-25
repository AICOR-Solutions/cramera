"""
A CRAM workspace given by a catalog file, standing in for the installed workspace in
tests that run without CRAM.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Dict, List, Set

from cramera_plan_builder.workspace import CramWorkspace
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.bundle.scene import ModelDescription, SceneDescription
from cramera_protocol.plan_builder import (
    ActionCatalog,
    LoadedEnvironment,
    ObjectModel,
    PlanBuilderCatalog,
    RobotModel,
)

DATASET = Path(__file__).parent
"""
The directory of the test dataset.
"""

ROBOT_MESH = "milk.stl"
"""
The mesh of the object directory a written robot description names as its body.
"""


@dataclass(frozen=True)
class GivenWorkspace(CramWorkspace):
    """
    Offers the robots, objects and surfaces a catalog file lists, the action schemas an
    action file lists, and the test object directory.
    """

    catalog_file: Path = DATASET / "workspace.json"
    """
    The catalog file.
    """

    directory: Path = DATASET / "objects"
    """
    The object directory.
    """

    actions_file: Path = DATASET / "actions.json"
    """
    The action file, schemas as the installed workspace discovers them.
    """

    def catalog(self) -> PlanBuilderCatalog:
        """
        :return: The catalog the file holds.
        """
        return PlanBuilderCatalog.from_json(
            json.loads(self.catalog_file.read_text(encoding="utf-8"))
        )

    def robots(self) -> List[RobotModel]:
        return self.catalog().robots

    def write_robot_description(self, name: str, directory: Path) -> Path:
        """
        Write a description of one link whose body is :data:`ROBOT_MESH`.
        """
        meshes = directory / "meshes"
        meshes.mkdir(parents=True)
        shutil.copyfile(self.directory / ROBOT_MESH, meshes / ROBOT_MESH)
        urdf = directory / f"{name}.urdf"
        urdf.write_text(
            f'<robot name="{name}"><link name="base"><visual><geometry>'
            f'<mesh filename="meshes/{ROBOT_MESH}"/></geometry></visual></link></robot>',
            encoding="utf-8",
        )
        return urdf

    def write_environment(
        self, source: Path, scenes: Path, taken: Set[str]
    ) -> LoadedEnvironment:
        """
        Copy the file into a bundle named after it, its meshes left behind.
        """
        name = source.stem
        bundle = scenes / name
        bundle.mkdir(parents=True)
        shutil.copyfile(source, bundle / source.name)
        description = SceneDescription(
            name=name,
            environment_name=name,
            models=[
                ModelDescription(name=name, urdf=source.name, prefix="", robot=False)
            ],
        )
        (bundle / BundleFile.SCENE).write_text(
            json.dumps(description.to_json()), encoding="utf-8"
        )
        return LoadedEnvironment(entry=SceneIndexEntry(name=name, environment=name))

    def objects(self) -> List[ObjectModel]:
        return self.catalog().objects

    def object_directory(self) -> Path:
        return self.directory

    def surface_types(self) -> List[str]:
        return self.catalog().surface_types

    def saved_surface_types(self) -> Dict[str, str]:
        return self.catalog().saved_surface_types

    def action_catalog(self) -> ActionCatalog:
        return ActionCatalog.from_json(
            json.loads(self.actions_file.read_text(encoding="utf-8"))
        )
