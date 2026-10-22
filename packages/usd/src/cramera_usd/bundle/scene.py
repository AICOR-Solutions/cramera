"""
The scene description of a converted stage, ``scene.json``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from typing_extensions import List, Optional

from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    ModelDescription,
    ObjectDescription,
    Rendering,
    RobotDescription,
    SceneDescription,
    SceneSource,
    Segment,
)
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.version import CURRENT_VERSION
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.animation.models import AnimatedObject, KinematicModel
from cramera_usd.bundle.camera import SceneCamera
from cramera_usd.bundle.layout import BundleLayout, Decimals
from cramera_usd.encoding import TEXT_ENCODING
from cramera_usd.geometry.bounds import PointBounds
from cramera_usd.scene.stage import ConvertedStage

# %% constants

OBJECT_LABEL_COLOR = "#ffffff"
"""
The colour of the objects' labels in the viewer.
"""

DEFAULT_EXPOSURE = 0.72
"""
The tone mapping exposure of a converted scene.

The viewer scales every light of ``lighting.json`` so that the lit ceiling shows at one,
which leaves the exposure alone to set the brightness; this value matches Isaac Sim's
renders of the lab twin.
"""

EMPTY_FOCUS_HALF_SIZE = 0.5
"""
Half the edge of the box framed in a scene without geometry, in metres.
"""

# %% presentation


@dataclass(frozen=True)
class ScenePresentation:
    """
    How a converted scene is labelled and first shown.
    """

    environment_name: str = ""
    """
    The environment's name in the viewer's picker; the stage file's name when empty.
    """

    task: str = ""
    """
    The scene's description in the viewer's picker; the stage file's name when empty.
    """

    camera: Optional[SceneCamera] = None
    """
    The initial camera, or None for the stage's first authored camera, else a view
    framing the dense core of the geometry.
    """

    exposure: float = DEFAULT_EXPOSURE
    """
    The tone mapping exposure.
    """


# %% scene


@dataclass(frozen=True)
class SceneSummary:
    """
    Collects the scene description of one bundle.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    name: str
    """
    The bundle's name.
    """

    presentation: ScenePresentation
    """
    How the scene is labelled and first shown.
    """

    models: List[KinematicModel]
    """
    The bundle's URDF models.
    """

    animation: Optional[SceneAnimation]
    """
    The playback with its robot, objects and segments, or None.
    """

    converter: str
    """
    The version of the converter.
    """

    def to_protocol(self, trajectory: Trajectory) -> SceneDescription:
        """
        :param trajectory: The bundle's trajectory, which spawns the objects.
        :return: The content of ``scene.json``.
        """
        stage_name = self.stage.source.name
        objects = [] if self.animation is None else self.animation.objects
        return SceneDescription(
            name=self.name,
            format_version=CURRENT_VERSION,
            environment_name=self.presentation.environment_name or stage_name,
            task=self.presentation.task or stage_name,
            frames_per_second=trajectory.frames_per_second,
            trajectory=BundleFile.TRAJECTORY.value,
            rendering=Rendering(
                exposure=self.presentation.exposure,
                ambient_occlusion=False,
                ground_plane=False,
                shadow_bounds=self.focus_bounds().to_protocol(Decimals.POSITION),
                environment=BundleFile.LIGHTING.value,
            ),
            camera=self.camera().to_protocol(),
            models=[self.model(model) for model in self.models],
            robot=self.robot(),
            objects=[self.object(moving, trajectory) for moving in objects],
            segments=self.segments(),
            missing_assets=list(self.stage.log.missing_textures),
            source=SceneSource(
                usd=str(self.stage.source),
                converter=self.converter,
                layers=self.source_digest(),
            ),
        )

    def focus_bounds(self) -> PointBounds:
        """
        :return: The dense core of the geometry, or a unit box at the origin without
            any.
        """
        if self.stage.central_bounds is not None:
            return self.stage.central_bounds
        return PointBounds.around_origin(EMPTY_FOCUS_HALF_SIZE)

    def camera(self) -> SceneCamera:
        """
        :return: The given camera, else the stage's first authored camera, else one
            framing the dense core of the geometry; the far plane reaches beyond the
            whole scene unless given.
        """
        framing = SceneCamera.framing(
            self.focus_bounds(), self.stage.bounds or self.focus_bounds()
        )
        camera = self.presentation.camera
        if camera is None and self.stage.cameras:
            camera = SceneCamera.of_camera(self.stage.cameras[0], self.focus_bounds())
        if camera is None:
            return framing
        return camera.with_far(framing.far)

    @staticmethod
    def model(model: KinematicModel) -> ModelDescription:
        """
        :param model: A URDF model of the bundle.
        :return: Its ``models`` entry.
        """
        return ModelDescription(
            name=model.name,
            urdf=BundleLayout.urdf_file(model),
            prefix=model.prefix,
            robot=model.robot,
            links=len(model.links),
            movable_joints=[joint.name for joint in model.movable_joints],
            preserve_materials=True,
        )

    def robot(self) -> Optional[RobotDescription]:
        """
        :return: The robot model's name, prefix, base link and parts, or None without a
            robot.
        """
        robot = None if self.animation is None else self.animation.robot
        if robot is None:
            return None
        return RobotDescription(
            name=robot.name,
            prefix=robot.prefix,
            base_body=robot.base_link,
            parts=robot.parts,
        )

    @staticmethod
    def object(moving: AnimatedObject, trajectory: Trajectory) -> ObjectDescription:
        """
        :param moving: An object of the playback.
        :param trajectory: The trajectory holding the object's poses.
        :return: Its ``objects`` entry, spawned at its pose in the first frame.
        """
        return ObjectDescription(
            identifier=moving.key,
            key=moving.key,
            mesh=BundleLayout.object_mesh(moving.key),
            spawn=trajectory.objects[0][moving.key],
            color=OBJECT_LABEL_COLOR,
            height=round(moving.height, Decimals.POSITION),
            preserve_materials=True,
        )

    def segments(self) -> List[Segment]:
        """
        :return: The labelled stretches of the playback.
        """
        if self.animation is None:
            return []
        return [
            Segment(step=segment.step, start=segment.start, end=segment.end)
            for segment in self.animation.segments
        ]

    def source_digest(self) -> str:
        """
        :return: The SHA-256 over the names and contents of every layer and texture
            read.
        """
        digest = hashlib.sha256()
        for path in sorted(self.stage.used_files):
            digest.update(path.name.encode(TEXT_ENCODING))
            digest.update(path.read_bytes())
        return digest.hexdigest()
