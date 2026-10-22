"""
Starting a draft from a recorded scene.
"""

from __future__ import annotations

import math

import pytest

from cramera.exceptions import PathOutsideDirectory, UnknownScene
from cramera.scenes import SceneSource
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.geometry import Pose, Vector3
from cramera_scene_builder.exceptions import UnusableOrientation
from cramera_scene_builder.templates import (
    RollPitchYaw,
    SceneTemplate,
    TemplateInstance,
)

# %% orientations


def test_a_turn_about_z_is_a_yaw():
    half = math.sqrt(0.5)
    turn = RollPitchYaw.of_pose(Pose(0.0, 0.0, 0.0, 0.0, 0.0, half, half))
    assert (turn.roll, turn.pitch, turn.yaw) == pytest.approx((0.0, 0.0, math.pi / 2))


def test_roll_pitch_and_yaw_apply_about_the_fixed_axes():
    roll, pitch, yaw = 0.3, -0.4, 1.1
    quaternion = [
        math.sin(roll / 2) * math.cos(pitch / 2) * math.cos(yaw / 2)
        - math.cos(roll / 2) * math.sin(pitch / 2) * math.sin(yaw / 2),
        math.cos(roll / 2) * math.sin(pitch / 2) * math.cos(yaw / 2)
        + math.sin(roll / 2) * math.cos(pitch / 2) * math.sin(yaw / 2),
        math.cos(roll / 2) * math.cos(pitch / 2) * math.sin(yaw / 2)
        - math.sin(roll / 2) * math.sin(pitch / 2) * math.cos(yaw / 2),
        math.cos(roll / 2) * math.cos(pitch / 2) * math.cos(yaw / 2)
        + math.sin(roll / 2) * math.sin(pitch / 2) * math.sin(yaw / 2),
    ]
    turn = RollPitchYaw.of_pose(Pose(0.0, 0.0, 0.0, *quaternion))
    assert (turn.roll, turn.pitch, turn.yaw) == pytest.approx((roll, pitch, yaw))


def test_a_pitch_of_ninety_degrees_gives_the_whole_turn_as_yaw():
    half = math.sqrt(0.5)
    turn = RollPitchYaw.of_pose(Pose(0.0, 0.0, 0.0, 0.0, half, 0.0, half))
    assert (turn.roll, turn.pitch) == pytest.approx((0.0, math.pi / 2))


def test_a_quaternion_without_length_is_refused():
    with pytest.raises(UnusableOrientation):
        RollPitchYaw.of_pose(Pose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))


# %% templates


@pytest.fixture
def cell(read_json):
    description = SceneDescription.from_json(read_json("scenes/cell/scene.json"))
    trajectory = Trajectory.from_json(read_json("scenes/cell/trajectory.json"))
    return description, trajectory


def test_a_template_places_the_models_and_objects_of_the_first_frame(
    catalog, library, cell
):
    description, trajectory = cell
    draft = SceneTemplate(catalog, library).draft("cell")
    arm, table, box = draft.instances
    robot_pose = trajectory.base[0]
    assert draft.name == description.environment_name
    assert draft.source_scene == "cell"
    assert [instance.identifier for instance in draft.instances] == [
        f"{TemplateInstance.MODEL}-1",
        f"{TemplateInstance.MODEL}-2",
        f"{TemplateInstance.OBJECT}-1",
    ]
    assert arm.asset == f"{SceneSource.DEMO}/cell/{description.models[0].urdf}"
    assert arm.position == Vector3(robot_pose.x, robot_pose.y, robot_pose.z)
    assert arm.rotation.z == pytest.approx(RollPitchYaw.of_pose(robot_pose).yaw)
    assert table.position.x == description.models[1].pose.x
    assert box.asset == f"{SceneSource.DEMO}/cell/{description.objects[0].mesh}"
    assert box.position.x == trajectory.objects[0][description.objects[0].key].x


def test_a_template_takes_the_joint_values_of_the_first_frame(catalog, library, cell):
    description, trajectory = cell
    arm = SceneTemplate(catalog, library).draft("cell").instances[0]
    prefix = description.models[0].prefix
    assert arm.joint_positions == {
        joint: trajectory.frames[0][f"{prefix}/{joint}"]
        for joint in description.models[0].movable_joints
    }


def test_a_template_of_an_unknown_scene_is_refused(catalog, library):
    with pytest.raises(UnknownScene):
        SceneTemplate(catalog, library).draft("missing")


def test_a_model_outside_its_bundle_is_refused(catalog, library):
    with pytest.raises(PathOutsideDirectory):
        SceneTemplate(catalog, library).draft("escaping")
