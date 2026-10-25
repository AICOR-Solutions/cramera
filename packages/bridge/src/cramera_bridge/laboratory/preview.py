"""
An initial-state laboratory scene with the real PR2, built locally from CRAM's assets.

The authored bench remains intact so its controls and object identifiers are the same
before and after the robot is added. No plan runs while this scene is prepared.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from cramera_bridge.documents import DocumentFile
from cramera_bridge.exceptions import SceneNameTaken
from cramera_bridge.export.scene_index import SceneIndexFile
from cramera_bridge.export.world_models import WorldModels
from cramera_bridge.geometry import NumericPose
from cramera_bridge.laboratory.transfer import TRANSFER_CAMERA, VesselTransferDemo
from cramera_bridge.live.bundles import BundleDirectory
from cramera_bridge.live.world_model import WorldModelView
from cramera_bridge.live.world_state import WorldStatePublisher
from cramera_bridge.robots import RobotRoster
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndexEntry
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.live_messages import SavedScene
from semantic_digital_twin.world_description.geometry import Mesh
from semantic_digital_twin.robots.robot_parts import AbstractRobot

PREVIEW_NAME = "aicor_medical_lab_pr2"
"""
The locally prepared compact laboratory with its robot at the task's starting pose.
"""

PREVIEW_REVISION = "2"
"""
Change this when the preview's construction changes, to refresh a cached scene.
"""

PREVIEW_SIGNATURE = ".preview-source.sha256"
"""
The digest of the source assets and preview revision that produced a cached scene.
"""

PREVIEW_CAMERA = TRANSFER_CAMERA
"""
The whole PR2 and the small bench are visible when the laboratory page first opens.
"""


@dataclass(frozen=True)
class LaboratoryPreview:
    """
    Prepare and cache the robot's initial state beside the viewer's other local scenes.
    """

    bundle: Path
    """
    The compact authored laboratory supplied by the plugin.
    """

    scenes: Path
    """
    The viewer's local scenes directory.
    """

    def signature(self) -> str:
        """
        :return: A digest that changes when the authored assets or preparation change.
        """
        digest = hashlib.sha256(PREVIEW_REVISION.encode("utf-8"))
        for path in sorted(self.bundle.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(self.bundle).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def prepare(self) -> SavedScene:
        """
        Build the same world and initial arm and torso pose as the transfer, then export
        only the robot into a copy of the authored laboratory. Reuse a complete cached
        scene when its source assets have not changed.

        :return: The prepared scene's protocol reference.
        :raises SceneNameTaken: When a user scene already occupies the preview's name.
        """
        directory = BundleDirectory(self.scenes / PREVIEW_NAME)
        signature = self.signature()
        marker = directory.path / PREVIEW_SIGNATURE
        if directory.path.exists() and not marker.is_file():
            raise SceneNameTaken(PREVIEW_NAME)
        if (
            marker.is_file()
            and marker.read_text(encoding="utf-8") == signature
            and (directory.path / BundleFile.SCENE).is_file()
            and (directory.path / BundleFile.TRAJECTORY).is_file()
        ):
            return SavedScene(scene=PREVIEW_NAME)
        demo = VesselTransferDemo.at_the_bench(self.bundle)
        world = demo.build_world()
        context = demo.build_context(world)
        robot = context.robot
        staging = directory.staging()
        try:
            shutil.copytree(self.bundle, staging, dirs_exist_ok=True)
            exporter = WorldModels(world, staging, "pr2")
            members = {body.id for body in robot.bodies}
            report = exporter.document().write(
                [
                    body
                    for body in world.bodies_topologically_sorted
                    if body.id in members
                ],
                RobotRoster(world).model_name(robot),
                identity_root=robot.root,
            )
            description = exporter.description(report, robot=True)
            self.copy_asset_notices(robot, staging)
            description.identifier = RobotRoster.identifier(robot)
            description.pose = NumericPose.of_entity(world, robot.root).published()
            scene = DocumentFile(staging / BundleFile.SCENE).read(SceneDescription)
            scene.name = PREVIEW_NAME
            scene.models.append(description)
            scene.robot = exporter.robot_description(robot)
            scene.robot_name = RobotRoster.label(robot)
            scene.camera = PREVIEW_CAMERA
            scene.trajectory = BundleFile.TRAJECTORY
            scene.missing_assets = report.missing
            state = WorldStatePublisher().refresh(
                WorldModelView.of_world(world), robot, markers_version=0
            )
            trajectory = Trajectory(
                frames=[state.frames],
                base=[state.base],
                model_bases=[state.model_bases],
            )
            DocumentFile(staging / BundleFile.TRAJECTORY).write(trajectory)
            DocumentFile(staging / BundleFile.SCENE).write(scene)
            (staging / PREVIEW_SIGNATURE).write_text(signature, encoding="utf-8")
            directory.publish(staging)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        SceneIndexFile(self.scenes).register(
            SceneIndexEntry(
                name=PREVIEW_NAME,
                robot=scene.robot_name,
                environment=scene.environment_name,
                task="PR2 at the small medical laboratory",
            )
        )
        return SavedScene(scene=PREVIEW_NAME)

    @staticmethod
    def copy_asset_notices(robot: AbstractRobot, destination: Path) -> None:
        """
        Keep each source ROS package's manifest and available notices beside its copied
        robot meshes. Their author and license declarations remain with the preview.

        :param robot: The robot whose meshes were copied.
        :param destination: The prepared scene bundle.
        """
        packages = set()
        for body in robot.bodies:
            for shape in (*body.visual.shapes, *body.collision.shapes):
                if isinstance(shape, Mesh):
                    for parent in Path(shape.filename).parents:
                        if (parent / "package.xml").is_file():
                            packages.add(parent)
                            break
        for package in packages:
            notices = {package / "package.xml"}
            for pattern in ("LICENSE*", "COPYING*", "NOTICE*"):
                notices.update(path for path in package.glob(pattern) if path.is_file())
            target = destination / "asset-sources" / package.name
            target.mkdir(parents=True, exist_ok=True)
            for notice in notices:
                shutil.copy2(notice, target / notice.name)
