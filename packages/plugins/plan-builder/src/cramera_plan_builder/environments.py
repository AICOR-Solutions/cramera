"""
The environments a plan can run in: the viewer's bundles that hold no robot model, and
the semantic annotations each offers a plan's annotation fields.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Dict, List, Tuple

from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.plan_builder import EnvironmentAnnotations
from cramera_plan_builder.workspace import WorkspaceLoader

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


# %% annotations


@dataclass
class EnvironmentAnnotationCache:
    """
    Each environment's semantic annotations, read once for every version of its scene
    description, since building its world takes a moment.
    """

    workspace: WorkspaceLoader
    """
    Reads what the CRAM workspace offers.
    """

    read: Dict[Tuple[Path, int], EnvironmentAnnotations] = field(default_factory=dict)
    """
    The annotations read, by bundle directory and its scene description's modification
    time.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    """
    Keeps two requests from building the same world at once.
    """

    def of(self, directory: Path) -> EnvironmentAnnotations:
        """
        :param directory: An environment bundle.
        :return: Its semantic annotations as a plan run finds them.
        """
        key = (directory, (directory / BundleFile.SCENE).stat().st_mtime_ns)
        with self.lock:
            if key not in self.read:
                self.read[key] = self.workspace.workspace().environment_annotations(
                    directory
                )
            return self.read[key]
