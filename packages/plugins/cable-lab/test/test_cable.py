"""
The composite cable in MuJoCo: its capsules, joints and mass, its placement in the
anchor frame, and the semantic points that follow it.
"""

from __future__ import annotations

import math

import mujoco
import numpy as np
import pytest

from cramera_cable_lab.cable import Cable, CableCompilation, is_point
from cramera_cable_lab.exceptions import CableNotBuilt, CablePrefixTaken
from cramera_protocol.cable_lab import CableConfiguration
from cramera_protocol.geometry import Vector3
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

LAB_ROOT = "lab_root"
"""
The name of the test worlds' root, which MuJoCo's own world body does not take.
"""

STEPS_UNDER_GRAVITY = 400
"""
How many steps the cable hangs before its links are measured.
"""


def world_with_parent() -> tuple[World, Body]:
    """
    :return: A world whose root is the cable's parent.
    """
    world = World()
    root = Body(name=PrefixedName(LAB_ROOT))
    with world.modify_world():
        world.add_kinematic_structure_entity(root)
    return world, root


def built(cable: Cable) -> CableCompilation:
    """
    :return: The cable built into a scene holding only its parent.
    """
    specification = mujoco.MjSpec()
    specification.worldbody.add_body(name=cable.parent.name.name)
    model = specification.compile()
    return cable.install(specification, model, mujoco.MjData(model))


def test_a_loose_cable_has_its_mass_and_ball_joints():
    world, parent = world_with_parent()
    cable = Cable(world, CableConfiguration(anchored=False), parent)
    compiled = built(cable)
    count = cable.configuration.segment_count
    assert compiled.model.nbody == count + 2
    assert compiled.model.neq == 0
    assert compiled.model.jnt_type.tolist() == [mujoco.mjtJoint.mjJNT_FREE] + [
        mujoco.mjtJoint.mjJNT_BALL
    ] * (count - 1)
    assert compiled.model.body_mass.sum() == pytest.approx(cable.configuration.mass)
    assert [compiled.model.body(index + 2).name for index in range(count)] == (
        cable.body_names()
    )


def test_the_links_keep_their_length_under_gravity():
    world, parent = world_with_parent()
    configuration = CableConfiguration(anchor_offset=Vector3(0.0, 0.0, 1.0))
    cable = Cable(world, configuration, parent)
    compiled = built(cable)
    for _ in range(STEPS_UNDER_GRAVITY):
        mujoco.mj_step(compiled.model, compiled.data)
    positions = np.array([compiled.data.body(name).xpos for name in cable.body_names()])
    np.testing.assert_allclose(
        np.linalg.norm(np.diff(positions, axis=0), axis=1),
        configuration.segment_length,
        atol=1e-7,
    )
    np.testing.assert_allclose(
        positions[0], configuration.anchor_offset.to_json(), atol=1e-10
    )
    assert positions[-1, 2] < configuration.anchor_offset.z


def test_the_anchor_rotation_turns_the_cable():
    world, parent = world_with_parent()
    configuration = CableConfiguration(
        anchor_offset=Vector3(0.1, 0.0, 0.6),
        anchor_rotation=Vector3(0.0, 0.0, math.pi / 2),
    )
    cable = Cable(world, configuration, parent)
    compiled = built(cable)
    first, second = (compiled.data.body(name).xpos for name in cable.body_names()[:2])
    np.testing.assert_allclose(first, configuration.anchor_offset.to_json(), atol=1e-7)
    np.testing.assert_allclose(
        second - first, [0, configuration.segment_length, 0], atol=1e-7
    )


def test_the_points_start_along_the_cable_and_follow_it():
    world, parent = world_with_parent()
    cable = Cable(world, CableConfiguration(anchored=False), parent)
    positions = [
        world.compute_forward_kinematics_np(world.root, point)[:3, 3]
        for point in cable.points
    ]
    np.testing.assert_allclose(
        np.diff(np.array(positions)[:, 0]), cable.configuration.segment_length
    )
    compiled = built(cable)
    for _ in range(STEPS_UNDER_GRAVITY):
        mujoco.mj_step(compiled.model, compiled.data)
    cable.follow(compiled.model, compiled.data)
    for point, name in zip(cable.points, cable.body_names()):
        np.testing.assert_allclose(
            world.compute_forward_kinematics_np(world.root, point)[:3, 3],
            compiled.data.body(name).xpos,
        )


def test_the_points_are_marked_as_semantic_only():
    world, parent = world_with_parent()
    cable = Cable(world, CableConfiguration(), parent)
    assert all(is_point(point) for point in cable.points)
    assert not is_point(parent)


def test_a_second_cable_with_the_same_names_is_refused():
    world, parent = world_with_parent()
    Cable(world, CableConfiguration(), parent)
    with pytest.raises(CablePrefixTaken):
        Cable(world, CableConfiguration(), parent)


def test_a_cable_mujoco_cannot_compile_is_refused():
    world, parent = world_with_parent()
    cable = Cable(world, CableConfiguration(anchored=False), parent)
    compiled = built(cable)
    with pytest.raises(CableNotBuilt) as refused:
        cable.install(compiled.specification, compiled.model, compiled.data)
    assert refused.value.message()
