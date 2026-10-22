"""
The workshop as a CRAM world: its loose bodies, drawers and handles, and the frames the
demos aim at.
"""

from __future__ import annotations

import numpy as np
import pytest

from cramera_workshop.robot.world import RobotStart, WorkshopBody
from semantic_digital_twin.semantic_annotations.semantic_annotations import Handle
from semantic_digital_twin.world_description.connections import (
    Connection6DoF,
    PrismaticConnection,
)


def test_every_loose_body_moves_freely_from_its_spawn_pose(workshop_world, bundle):
    for item in bundle.movable_objects():
        body = workshop_world.get_body_by_name(item.key)
        assert isinstance(body.parent_connection, Connection6DoF)
        np.testing.assert_allclose(
            body.global_pose.to_np()[:3, 3],
            [item.spawn.x, item.spawn.y, item.spawn.z],
            atol=1e-9,
        )


def test_the_drawers_slide(workshop_world, bundle):
    for drawer in bundle.workshop.drawers:
        connection = workshop_world.get_connection_by_name(drawer.joint)
        assert isinstance(connection, PrismaticConnection)


def test_every_handle_is_annotated(workshop_world, bundle):
    handles = workshop_world.get_semantic_annotations_by_type(Handle)
    assert sorted(handle.root.name.name for handle in handles) == sorted(
        bundle.semantics().handles
    )


def test_the_pilot_mouth_is_on_the_workpiece(workshop_world, environment, bundle):
    mouth = environment.pilot_mouth(workshop_world).to_np()
    workpiece = workshop_world.get_body_by_name(WorkshopBody.ASSEMBLY)
    local = np.linalg.inv(workpiece.global_pose.to_np()) @ mouth
    np.testing.assert_allclose(
        local[:3, 3], bundle.workshop.assembly.local_mouth.to_json(), atol=1e-9
    )


def test_the_screws_are_the_described_ones(workshop_world, environment, bundle):
    names = [screw.name.name for screw in environment.screws(workshop_world)]
    assert names == bundle.workshop.screws()


def test_a_robot_start_faces_the_workbench(workshop_world):
    start = RobotStart()
    pose = start.world_pose(workshop_world).to_np()
    np.testing.assert_allclose(pose[:3, 3], [start.x, start.y, 0.0])
    assert pose[1, 0] == pytest.approx(np.sin(start.yaw))
    assert start.pr2().odom_T_robot_start.to_np()[0, 3] == start.x
