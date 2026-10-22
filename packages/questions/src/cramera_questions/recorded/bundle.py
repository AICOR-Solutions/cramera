"""
A recorded scene bundle read through the protocol documents of its files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing_extensions import Optional

from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import ModelDescription, SceneDescription
from cramera_protocol.bundle.statecharts import Statecharts
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_questions.recorded.urdf import UrdfStructure

# %% bundle


@dataclass(frozen=True)
class RecordedBundle:
    """
    The files of one bundle that questions are answered from.
    """

    name: str
    """
    The bundle's name.
    """

    scene: SceneDescription
    """
    The scene description.
    """

    trajectory: Optional[Trajectory] = None
    """
    The trajectory, when the bundle has one.
    """

    statecharts: Optional[Statecharts] = None
    """
    The recorded statecharts, when the bundle has them.
    """

    robot_structure: Optional[UrdfStructure] = None
    """
    The kinematic tree of the robot model, when the bundle has one.
    """

    @classmethod
    def of_catalog(cls, catalog: SceneCatalog, name: str) -> RecordedBundle:
        """
        :param catalog: The scenes the viewer shows.
        :param name: A bundle name.
        :return: The bundle's documents.
        :raises UnknownScene: When no scenes directory holds the bundle.
        :raises FileNotInDirectory: When a file the scene declares is missing.
        :raises ProtocolError: When a file does not hold its document.
        """
        reader = BundleReader(catalog, name)
        scene = SceneDescription.from_json(reader.json(BundleFile.SCENE))
        robot_model = cls.robot_model(scene)
        return cls(
            name=name,
            scene=scene,
            trajectory=(
                None
                if scene.trajectory is None
                else Trajectory.from_json(reader.json(scene.trajectory))
            ),
            statecharts=(
                None
                if scene.statecharts is None
                else Statecharts.from_json(reader.json(scene.statecharts))
            ),
            robot_structure=(
                None
                if robot_model is None
                else UrdfStructure.of_file(catalog.bundle_file(name, robot_model.urdf))
            ),
        )

    @staticmethod
    def robot_model(scene: SceneDescription) -> Optional[ModelDescription]:
        """
        :param scene: A scene description.
        :return: The model of the scene's robot: the first robot model.
        """
        return next((model for model in scene.models if model.robot), None)


@dataclass(frozen=True)
class BundleReader:
    """
    Reads the JSON files of one bundle, confined to the bundle.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    name: str
    """
    The bundle's name.
    """

    def json(self, relative: str) -> object:
        """
        :param relative: A file of the bundle.
        :return: The file's decoded content.
        """
        path = self.catalog.bundle_file(self.name, relative)
        return json.loads(path.read_text(encoding="utf-8"))

    def stamp(self) -> int:
        """
        :return: When the bundle's scene description last changed, in nanoseconds.
        """
        return self.catalog.bundle_file(self.name, BundleFile.SCENE).stat().st_mtime_ns
