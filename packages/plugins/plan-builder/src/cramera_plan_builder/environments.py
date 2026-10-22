"""
The environments a plan can run in: the viewer's bundles that hold no robot model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing_extensions import List

from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError

# %% environments


@dataclass(frozen=True)
class EnvironmentBundles:
    """
    The bundles of the viewer's scenes a robot task can start from.
    """

    scenes: SceneCatalog
    """
    The scenes the viewer shows.
    """

    def entries(self) -> List[SceneIndexEntry]:
        """
        :return: The index entries of the bundles without a robot model, in the order
            the viewer lists them.
        """
        return [
            entry for entry in self.scenes.index().scenes if self.is_environment(entry)
        ]

    def is_environment(self, entry: SceneIndexEntry) -> bool:
        """
        A bundle the index lists may still be damaged; it must not hide its readable
        neighbours, so this is the one place where reading its scene becomes a yes or
        no.

        :param entry: A bundle of the index.
        :return: Whether its scene reads and holds no robot model.
        """
        if entry.robot:
            return False
        scene_file = self.scenes.bundle_file(entry.name, BundleFile.SCENE)
        try:
            scene = SceneDescription.from_json(
                json.loads(scene_file.read_text(encoding="utf-8"))
            )
        except (ValueError, ProtocolError):
            return False
        return not any(model.robot for model in scene.models)
