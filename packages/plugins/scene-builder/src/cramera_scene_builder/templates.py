"""
Starting a draft from a recorded scene: its models, robots and objects, placed as the
recording's first frame shows them.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import Dict, List, Optional, Self

from cramera.confinement import ConfinedDirectory
from cramera.scenes import SceneCatalog
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import (
    ModelDescription,
    ObjectDescription,
    SceneDescription,
)
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.geometry import Pose, Vector3
from cramera_protocol.scene_builder import DraftInstance, SceneDraft
from cramera_scene_builder.exceptions import UnusableOrientation
from cramera_scene_builder.resources import ResourceLibrary

IDENTITY_POSE = Pose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
"""
The pose of a model a scene does not place.
"""

GIMBAL_LOCK_TOLERANCE = 1e-12
"""
How close to ±1 the sine of the pitch is taken as a pitch of ±90°.
"""

JOINT_PREFIX_SEPARATOR = "/"
"""
Separates a model's prefix from a joint name in trajectory keys.
"""

# %% orientations


@dataclass(frozen=True)
class RollPitchYaw:
    """
    An orientation as URDF writes it: rotations about the fixed x, y and z axes, applied
    in that order (``Rz · Ry · Rx``), in radians.
    """

    roll: float
    """
    The rotation about the x axis.
    """

    pitch: float
    """
    The rotation about the y axis.
    """

    yaw: float
    """
    The rotation about the z axis.
    """

    @classmethod
    def of_pose(cls, pose: Pose) -> Self:
        """
        At a pitch of ±90° roll and yaw turn about the same axis; the whole turn is then
        given as yaw.

        :param pose: A pose with a quaternion.
        :return: The pose's orientation.
        :raises UnusableOrientation: When the quaternion has no length.
        """
        quaternion = (pose.qx, pose.qy, pose.qz, pose.qw)
        length = math.sqrt(sum(component * component for component in quaternion))
        if length == 0 or not math.isfinite(length):
            raise UnusableOrientation(list(quaternion))
        x, y, z, w = (component / length for component in quaternion)
        sine_pitch = max(-1.0, min(1.0, 2 * (y * w - x * z)))
        pitch = math.asin(sine_pitch)
        if abs(sine_pitch) >= 1.0 - GIMBAL_LOCK_TOLERANCE:
            yaw = math.atan2(2 * (z * w - x * y), 1 - 2 * (x * x + z * z))
            return cls(roll=0.0, pitch=pitch, yaw=yaw)
        return cls(
            roll=math.atan2(2 * (x * w + y * z), 1 - 2 * (x * x + y * y)),
            pitch=pitch,
            yaw=math.atan2(2 * (z * w + x * y), 1 - 2 * (y * y + z * z)),
        )

    def to_vector(self) -> Vector3:
        """
        :return: The roll, pitch and yaw as a vector.
        """
        return Vector3(self.roll, self.pitch, self.yaw)


# %% templates


class TemplateInstance(StrEnum):
    """
    What an instance of a draft started from a scene was in the scene; its identity
    starts with it.
    """

    MODEL = "model"
    """
    One of the scene's kinematic models.
    """

    OBJECT = "object"
    """
    One of the scene's free objects.
    """


@dataclass(frozen=True)
class FirstFrame:
    """
    The recording's first frame: joint values, robot root poses and object poses.
    """

    joint_values: Dict[str, float]
    """
    The value of every joint, by its trajectory key.
    """

    robot_pose: Optional[Pose]
    """
    The robot's root pose, if recorded.
    """

    model_poses: Dict[str, Pose]
    """
    The root pose of every robot instance, by its identifier.
    """

    object_poses: Dict[str, Pose]
    """
    The pose of every free object, by its key.
    """

    @classmethod
    def of(cls, trajectory: Optional[Trajectory]) -> Self:
        """
        :param trajectory: The recording, or None for a scene without one.
        :return: Its first frame; empty for a scene without recording.
        """
        if trajectory is None:
            return cls(
                joint_values={}, robot_pose=None, model_poses={}, object_poses={}
            )
        return cls(
            joint_values=dict(trajectory.frames[0]) if trajectory.frames else {},
            robot_pose=trajectory.base[0] if trajectory.base else None,
            model_poses=(
                dict(trajectory.model_bases[0]) if trajectory.model_bases else {}
            ),
            object_poses=dict(trajectory.objects[0]) if trajectory.objects else {},
        )

    def model_pose(self, model: ModelDescription) -> Pose:
        """
        :param model: A model of the scene.
        :return: Where the first frame places it.
        """
        pose = model.pose or IDENTITY_POSE
        if model.robot and self.robot_pose is not None:
            pose = self.robot_pose
        return self.model_poses.get(model.identifier or model.name, pose)

    def joints_of(self, model: ModelDescription) -> Dict[str, float]:
        """
        :param model: A model of the scene.
        :return: The first frame's value of each of its movable joints, by joint name.
        """
        values = {}
        for joint in model.movable_joints:
            key = (
                f"{model.prefix}{JOINT_PREFIX_SEPARATOR}{joint}"
                if model.prefix
                else joint
            )
            if key in self.joint_values:
                values[joint] = self.joint_values[key]
        return values

    def object_pose(self, scene_object: ObjectDescription) -> Pose:
        """
        :param scene_object: A free object of the scene.
        :return: Where the first frame places it.
        """
        return self.object_poses.get(scene_object.key, scene_object.spawn)


@dataclass(frozen=True)
class SceneTemplate:
    """
    Turns a scene bundle of the viewer's catalog into a draft.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    library: ResourceLibrary
    """
    The resource library, whose roots include the catalog's directories.
    """

    def draft(self, name: str) -> SceneDraft:
        """
        :param name: The bundle's name.
        :return: A draft placing the bundle's models and objects as its first frame
            shows them.
        :raises UnknownScene: When no scenes directory holds the bundle.
        :raises PathOutsideDirectory: When a model's file lies outside the bundle.
        :raises FileNotInDirectory: When the bundle lacks a model's file.
        :raises OutsideLibrary: When a model's file lies outside the library.
        """
        bundle = self.catalog.directory_of(name).bundle(name)
        description = SceneDescription.from_json(
            self.read_json(bundle.file(BundleFile.SCENE))
        )
        frame = FirstFrame.of(self.trajectory(bundle, description))
        instances: List[DraftInstance] = []
        for index, model in enumerate(description.models, start=1):
            instances.append(
                self.instance(
                    f"{TemplateInstance.MODEL}-{index}",
                    model.name,
                    bundle.file(model.urdf),
                    frame.model_pose(model),
                    frame.joints_of(model),
                )
            )
        placed = [item for item in description.objects if item.mesh or item.urdf]
        for index, scene_object in enumerate(placed, start=1):
            instances.append(
                self.instance(
                    f"{TemplateInstance.OBJECT}-{index}",
                    scene_object.identifier,
                    bundle.file(scene_object.urdf or scene_object.mesh),
                    frame.object_pose(scene_object),
                    {},
                )
            )
        return SceneDraft(
            name=description.environment_name or description.name,
            instances=instances,
            source_scene=name,
        )

    @staticmethod
    def read_json(path: Path) -> object:
        """
        :param path: A JSON file of a bundle.
        :return: Its decoded content.
        """
        return json.loads(path.read_text(encoding="utf-8"))

    def trajectory(
        self, bundle: ConfinedDirectory, description: SceneDescription
    ) -> Optional[Trajectory]:
        """
        :param bundle: The bundle directory.
        :param description: The bundle's scene description.
        :return: The bundle's recording, or None for a scene without one.
        """
        if description.trajectory is None:
            return None
        return Trajectory.from_json(self.read_json(bundle.file(description.trajectory)))

    def instance(
        self,
        identifier: str,
        name: str,
        path: Path,
        pose: Pose,
        joints: Dict[str, float],
    ) -> DraftInstance:
        """
        :param identifier: The instance's identity in the draft.
        :param name: The instance's name.
        :param path: The model's file, confined to the bundle.
        :param pose: Where the scene places the model.
        :param joints: The model's joint values.
        :return: The instance placing the model.
        :raises OutsideLibrary: When the model's file lies outside the library.
        """
        return DraftInstance(
            identifier=identifier,
            asset=self.library.identifier_of(path).text(),
            name=name,
            position=Vector3(pose.x, pose.y, pose.z),
            rotation=RollPitchYaw.of_pose(pose).to_vector(),
            joint_positions=joints,
        )
