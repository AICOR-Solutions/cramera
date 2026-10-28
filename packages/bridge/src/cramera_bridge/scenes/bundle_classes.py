"""
``cramera-record-classes``: names the class of every entity of bundles recorded before
scenes named them, as CRAM reads each bundle, and writes the classes into the bundle's
``scene.json``, so the viewer can link each entity to its class in the ontology.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Optional, Sequence

from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_bridge.documents import DocumentFile
from cramera_bridge.names import ROBOTS, class_path
from cramera_bridge.robots import RobotParts, RobotRoster
from cramera_bridge.scenes.environment import SceneEnvironment
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    ModelDescription,
    SceneClasses,
    SceneDescription,
)
from semantic_digital_twin.specifications.robots import RobotSpecification
from semantic_digital_twin.specifications.worlds import WorldSpecification
from semantic_digital_twin.world_description.world_entity import Body

# %% classes


@dataclass(frozen=True)
class BundleClasses:
    """
    The classes of a bundle's entities as CRAM reads the bundle: the bodies and
    connections of its models parsed from their URDFs, its free objects as bodies, and
    its robot with the parts the robot's own description gives it.
    """

    directory: Path
    """
    The bundle directory.
    """

    def scene_file(self) -> DocumentFile:
        """
        :return: The bundle's ``scene.json``.
        """
        return DocumentFile(self.directory / BundleFile.SCENE)

    def classes(self, scene: SceneDescription) -> SceneClasses:
        """
        :param scene: The bundle's scene description.
        :return: The classes of its entities; a robot model whose class is not pinned
            names no class.
        """
        classes = SceneClasses()
        for model in scene.models:
            self.add_model(classes, model)
        for description in scene.objects:
            classes.bodies[description.identifier] = class_path(Body)
        robot_classes = self.robot_classes()
        for model in scene.models:
            robot_class = robot_classes.get(model.name) if model.robot else None
            if robot_class is None:
                continue
            classes.models[model.name] = class_path(robot_class)
            if scene.robot is not None and scene.robot.name == model.name:
                classes.annotations = self.part_classes(robot_class)
        return classes

    def add_model(self, classes: SceneClasses, model: ModelDescription) -> None:
        """
        :param classes: The classes the model's world, bodies and connections are added
            to, each body by its link name and each connection by its joint name.
        :param model: A model of the bundle.
        """
        # the parser reads a relative path from the directory of the file it names
        description = (self.directory / model.urdf).resolve()
        world = SceneEnvironment.parse_model(description, model.prefix)
        classes.world = class_path(type(world))
        for body in world.bodies:
            classes.bodies[body.name.name] = class_path(type(body))
            connection = body.parent_connection
            if connection is not None:
                classes.connections[connection.name.name] = class_path(type(connection))

    @staticmethod
    def robot_classes() -> Dict[str, type]:
        """
        :return: The pinned robot classes by the model name the only robot of a world
            being of that class gets.
        """
        classes = [pinned.resolve() for pinned in ROBOTS]
        return {RobotRoster.class_model_name(cls): cls for cls in classes}

    @staticmethod
    def part_classes(robot_class: type) -> Dict[str, str]:
        """
        :param robot_class: A robot class.
        :return: The classes of the parts its description gives a robot of the class,
            by part name.
        """
        world = WorldSpecification(
            robots=[RobotSpecification(semantic_annotation_type=robot_class)]
        ).to_domain_object()
        [robot] = world.get_semantic_annotations_by_type(robot_class)
        return {
            str(part.name): class_path(type(part))
            for part in RobotParts(world, robot).annotations()
        }

    def write(self) -> Path:
        """
        Name the classes in the bundle's ``scene.json``.

        :return: The file written.
        """
        scene_file = self.scene_file()
        scene = scene_file.read(SceneDescription)
        scene.classes = self.classes(scene)
        scene_file.write(scene)
        return scene_file.path


# %% command


class ClassesOption(StrEnum):
    """
    The command's options.
    """

    SCENE = "--scene"
    """
    A bundle to name the classes of; every bundle of the directory when none is named.
    """


def scene_names(scenes: Path) -> List[str]:
    """
    :param scenes: A scenes directory.
    :return: The names of every readable bundle of the directory.
    """
    catalog = SceneCatalog([SceneDirectory(scenes, SceneSource.DEMO)])
    return [entry.name for entry in catalog.index().scenes]


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """
    Name the classes of a scenes directory's bundles.

    :param arguments: The command-line arguments; the process arguments when None.
    :return: The process exit code.
    """
    parser = argparse.ArgumentParser(
        prog="cramera-record-classes", description=__doc__.strip().splitlines()[0]
    )
    parser.add_argument("scenes", type=Path)
    parser.add_argument(ClassesOption.SCENE, action="append", default=None)
    parsed = parser.parse_args(arguments)
    for name in parsed.scene or scene_names(parsed.scenes):
        print(f"named the classes in {BundleClasses(parsed.scenes / name).write()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
