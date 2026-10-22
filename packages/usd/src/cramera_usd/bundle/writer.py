"""
Writing a converted stage as a scene bundle and registering it in the scenes index.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneName
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.animator import ENVIRONMENT_MODEL
from cramera_usd.animation.models import AnimatedObject, KinematicModel
from cramera_usd.bundle.index import ScenesIndex
from cramera_usd.bundle.json_file import JsonFile, JsonLayout
from cramera_usd.bundle.layout import BundleLayout
from cramera_usd.bundle.lighting import LightingSummary
from cramera_usd.bundle.meshes import MeshFiles
from cramera_usd.bundle.report import ConversionDurations, ReportSummary
from cramera_usd.bundle.scene import ScenePresentation, SceneSummary
from cramera_usd.bundle.semantics import SemanticsSummary
from cramera_usd.bundle.trajectory import AnimatedTrajectory, StaticTrajectory
from cramera_usd.distribution import Distribution
from cramera_usd.encoding import TEXT_ENCODING
from cramera_usd.materials.mapper import MaterialMapper
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.urdf import UrdfDocument

# %% bundle


@dataclass
class SceneBundle:
    """
    Writes one converted stage as a scene bundle and registers it in the scenes index.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    name: str
    """
    The bundle's directory name and the scene the viewer's page opens by.
    """

    scenes_directory: Path
    """
    The directory holding the bundles and ``index.json``.
    """

    presentation: ScenePresentation = field(default_factory=ScenePresentation)
    """
    How the scene is labelled and first shown.
    """

    animation: Optional[SceneAnimation] = None
    """
    The recorded playback with its robot and objects, or None for a static scene of one
    environment model.
    """

    read_seconds: float = 0.0
    """
    How long reading the stage took, for the report.
    """

    mapper: MaterialMapper = field(default_factory=MaterialMapper)
    """
    The mapping of authored materials onto glTF materials.
    """

    @property
    def layout(self) -> BundleLayout:
        """
        The files of the bundle.
        """
        return BundleLayout(self.scenes_directory / self.name)

    @property
    def index(self) -> ScenesIndex:
        """
        The scenes index the bundle is registered in.
        """
        return ScenesIndex(self.scenes_directory)

    def write(self) -> Path:
        """
        Write every file of the bundle and rebuild the scenes index.

        :return: The bundle directory.
        :raises InvalidSceneName: When the bundle's name is not a scene name.
        """
        SceneName(self.name)
        started = time.perf_counter()
        layout = self.layout
        layout.file(BundleFile.MESHES).mkdir(parents=True, exist_ok=True)
        materials = self.mapped_materials()
        self.write_meshes(materials)
        for model in self.models():
            layout.file(BundleLayout.urdf_file(model)).write_bytes(
                self.urdf(model).to_bytes()
            )
        trajectory = self.trajectory()
        JsonFile(layout.file(BundleFile.TRAJECTORY)).write(
            trajectory, JsonLayout.COMPACT
        )
        if self.animation is not None:
            layout.file(BundleFile.RESIDUALS).write_bytes(
                self.animation.residuals_table().to_text().encode(TEXT_ENCODING)
            )
        JsonFile(layout.file(BundleFile.SEMANTICS)).write(
            SemanticsSummary(self.stage, self.animation).to_protocol(),
            JsonLayout.INDENTED,
        )
        JsonFile(layout.file(BundleFile.LIGHTING)).write(
            LightingSummary(self.stage.lights).to_protocol(), JsonLayout.INDENTED
        )
        JsonFile(layout.file(BundleFile.SCENE)).write(
            self.scene().to_protocol(trajectory), JsonLayout.INDENTED
        )
        report = ReportSummary(
            self.stage,
            Distribution.CONVERTER.version(),
            self.unmapped_inputs(materials),
            self.animation,
        ).to_protocol(
            ConversionDurations(self.read_seconds, time.perf_counter() - started),
            layout.size(),
        )
        JsonFile(layout.file(BundleFile.CONVERSION_REPORT)).write(
            report, JsonLayout.INDENTED
        )
        self.index.rebuild(self.name)
        return layout.directory

    def mapped_materials(self) -> Dict[str, PhysicallyBasedMaterial]:
        """
        :return: The glTF material of every authored material, by name.
        """
        return {
            name: self.mapper.map(material)
            for name, material in self.stage.materials.items()
        }

    @staticmethod
    def unmapped_inputs(
        materials: Dict[str, PhysicallyBasedMaterial],
    ) -> Dict[str, List[str]]:
        """
        :param materials: The glTF material of every authored material, by name.
        :return: The authored inputs no mapping carried over, by material name, for the
            materials that have any.
        """
        return {
            name: list(material.unmapped_inputs)
            for name, material in sorted(materials.items())
            if material.unmapped_inputs
        }

    def write_meshes(self, materials: Dict[str, PhysicallyBasedMaterial]) -> None:
        """
        Write one GLB per link with geometry of every model and per object, and remove
        the GLBs a previous conversion left for links that no longer exist.

        :param materials: The glTF material of every authored material.
        """
        files = MeshFiles(
            self.layout,
            materials,
            {item.path: item.attributes for item in self.stage.semantics},
        )
        files.write_models(self.models())
        files.write_objects(self.objects())
        files.remove_stale()

    def models(self) -> List[KinematicModel]:
        """
        :return: The URDF models of the bundle: the playback's, else one environment
            model of every link.
        """
        if self.animation is not None:
            return self.animation.models
        return [KinematicModel(ENVIRONMENT_MODEL, self.stage.links, self.stage.joints)]

    def objects(self) -> List[AnimatedObject]:
        """
        :return: The objects played back by their poses.
        """
        return [] if self.animation is None else self.animation.objects

    def urdf(self, model: KinematicModel) -> UrdfDocument:
        """
        :param model: A model of the bundle.
        :return: The model's URDF; a robot is named after itself, the environment after
            the bundle.
        """
        return UrdfDocument(
            model.name if model.robot else self.name,
            model.links,
            model.joints,
            {
                link.name: self.layout.mesh_file(model, link.name)
                for link in model.links
            },
        )

    def trajectory(self) -> Trajectory:
        """
        :return: The playback's frames, else one frame of the initial joint values.
        """
        if self.animation is not None:
            return AnimatedTrajectory(self.animation).to_protocol()
        return StaticTrajectory(
            {joint.name: joint.initial_value for joint in self.stage.movable_joints}
        ).to_protocol()

    def scene(self) -> SceneSummary:
        """
        :return: The collector of the bundle's scene description.
        """
        return SceneSummary(
            self.stage,
            self.name,
            self.presentation,
            self.models(),
            self.animation,
            Distribution.CONVERTER.version(),
        )
