"""
The workshop's MuJoCo model: free joints for the loose bodies, sliding drawers, and the
collision shapes it can build.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree

import mujoco
import pytest

from cramera_workshop.collision_model import (
    FREE_JOINT_SUFFIX,
    CollisionModel,
    ContactSettings,
    MujocoTag,
    UrdfDescription,
)
from cramera_workshop.exceptions import UnsupportedCollisionShape


@pytest.fixture(scope="module")
def model(bundle) -> mujoco.MjModel:
    """
    :return: The compiled workshop model.
    """
    return CollisionModel(bundle).compile()


def test_every_loose_body_moves_on_a_free_joint(model, bundle):
    for item in bundle.movable_objects():
        joint = model.joint(f"{item.key}{FREE_JOINT_SUFFIX}")
        assert model.jnt_type[joint.id] == mujoco.mjtJoint.mjJNT_FREE


def test_the_drawers_slide_within_their_travel(model, bundle):
    for drawer in bundle.workshop.drawers:
        joint = model.joint(drawer.joint)
        assert model.jnt_type[joint.id] == mujoco.mjtJoint.mjJNT_SLIDE
        assert model.jnt_range[joint.id][1] >= drawer.open


def test_the_model_takes_the_contact_settings(model):
    settings = ContactSettings()
    assert model.opt.timestep == settings.timestep
    assert model.opt.iterations == settings.solver_iterations


def test_a_loose_body_starts_at_its_spawn_pose(bundle):
    root = ElementTree.fromstring(CollisionModel(bundle).xml())
    item = bundle.movable_objects()[0]
    body = root.find(f"{MujocoTag.WORLD_BODY}/{MujocoTag.BODY}[@name='{item.key}']")
    position = [float(value) for value in body.get("pos").split()]
    assert position == pytest.approx([item.spawn.x, item.spawn.y, item.spawn.z])


def test_a_mesh_collision_is_refused(dataset):
    description = UrdfDescription(dataset / "mesh_collision.urdf", ContactSettings())
    with pytest.raises(UnsupportedCollisionShape) as refused:
        description.add_to(ElementTree.Element(MujocoTag.WORLD_BODY), None)
    assert refused.value.shape == "mesh"
    assert refused.value.message()
