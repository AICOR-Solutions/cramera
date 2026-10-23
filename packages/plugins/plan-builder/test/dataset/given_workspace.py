"""
A CRAM workspace given by a catalog file, standing in for the installed workspace in
tests that run without CRAM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import List

from cramera_plan_builder.workspace import CramWorkspace
from cramera_protocol.plan_builder import (
    ActionCatalog,
    ObjectModel,
    PlanBuilderCatalog,
    RobotModel,
)

DATASET = Path(__file__).parent
"""
The directory of the test dataset.
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

    def objects(self) -> List[ObjectModel]:
        return self.catalog().objects

    def object_directory(self) -> Path:
        return self.directory

    def surface_types(self) -> List[str]:
        return self.catalog().surface_types

    def action_catalog(self) -> ActionCatalog:
        return ActionCatalog.from_json(
            json.loads(self.actions_file.read_text(encoding="utf-8"))
        )
