"""
``cramera-upgrade-bundle``: copy a scene bundle and rewrite its documents in the current
protocol version, optionally with new picker labels.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, Optional, Sequence, Type

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.statecharts import Statecharts
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.document import JsonDocument
from cramera_protocol.version import CURRENT_VERSION

# %% options


class UpgradeOption(StrEnum):
    """
    The command's options.
    """

    ROBOT_NAME = "--robot-name"
    """
    The robot's display name.
    """

    ENVIRONMENT_NAME = "--environment-name"
    """
    The environment's display name.
    """

    TASK = "--task"
    """
    The task's display name.
    """


# %% upgrade


@dataclass(frozen=True)
class BundleLabels:
    """
    The picker labels to write into an upgraded bundle; None keeps a label.
    """

    robot_name: Optional[str] = None
    """
    The robot's display name.
    """

    environment_name: Optional[str] = None
    """
    The environment's display name.
    """

    task: Optional[str] = None
    """
    The task's display name.
    """

    def applied_to(self, scene: SceneDescription) -> SceneDescription:
        """
        :param scene: A scene description.
        :return: The description with every given label replaced.
        """
        return replace(
            scene,
            robot_name=self.robot_name or scene.robot_name,
            environment_name=self.environment_name or scene.environment_name,
            task=self.task or scene.task,
        )


@dataclass(frozen=True)
class BundleUpgrade:
    """
    Copies a bundle and rewrites its scene, trajectory and statecharts in the current
    protocol version; every other file is copied unchanged.
    """

    source: Path
    """
    The bundle to upgrade.
    """

    destination: Path
    """
    The directory to write the upgraded bundle to; it must not exist, and its name
    becomes the bundle's name.
    """

    labels: BundleLabels = BundleLabels()
    """
    The picker labels to write.
    """

    def run(self) -> SceneDescription:
        """
        :return: The upgraded scene description.
        :raises FileExistsError: When the destination exists.
        :raises InvalidSceneName: When the destination's name is no bundle name.
        """
        SceneName(self.destination.name)
        shutil.copytree(self.source, self.destination)
        scene = replace(
            self.labels.applied_to(self.read(BundleFile.SCENE, SceneDescription)),
            name=self.destination.name,
            format_version=CURRENT_VERSION,
        )
        self.write(BundleFile.SCENE, scene, indent=1)
        for file, document_class in self.documents_of(scene).items():
            self.write(file, self.read(file, document_class), indent=None)
        return scene

    def documents_of(self, scene: SceneDescription) -> Dict[str, Type[JsonDocument]]:
        """
        :param scene: The scene description.
        :return: The further documents the scene names, with their classes.
        """
        documents: Dict[str, Type[JsonDocument]] = {}
        if scene.trajectory is not None:
            documents[scene.trajectory] = Trajectory
        if scene.statecharts is not None:
            documents[scene.statecharts] = Statecharts
        return documents

    def read(self, file: str, document_class: Type[JsonDocument]) -> Any:
        """
        :param file: A document of the copied bundle.
        :param document_class: The document's class.
        :return: The document.
        """
        text = (self.destination / file).read_text(encoding="utf-8")
        return document_class.from_json(json.loads(text))

    def write(self, file: str, document: JsonDocument, indent: Optional[int]) -> None:
        """
        :param file: A document of the copied bundle.
        :param document: Its new content.
        :param indent: The JSON indentation, None for compact output.
        """
        separators = None if indent is not None else (",", ":")
        text = json.dumps(document.to_json(), indent=indent, separators=separators)
        (self.destination / file).write_text(text + "\n", encoding="utf-8")


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """
    Upgrade one bundle.

    :param arguments: The command-line arguments; the process arguments when None.
    :return: The process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="cramera-upgrade-bundle", description=__doc__.strip().splitlines()[0]
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(UpgradeOption.ROBOT_NAME, default=None)
    parser.add_argument(UpgradeOption.ENVIRONMENT_NAME, default=None)
    parser.add_argument(UpgradeOption.TASK, default=None)
    parsed = parser.parse_args(arguments)
    labels = BundleLabels(
        robot_name=parsed.robot_name,
        environment_name=parsed.environment_name,
        task=parsed.task,
    )
    scene = BundleUpgrade(parsed.source, parsed.destination, labels).run()
    print(
        f"upgraded {parsed.source} to {parsed.destination} ({scene.format_version.to_json()})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
