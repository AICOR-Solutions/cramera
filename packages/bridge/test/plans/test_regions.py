"""
The table a robot mounted on none looks at and puts objects down on: the table of its
environment that stands nearest to it.
"""

from __future__ import annotations

import pytest

from cramera_bridge.exceptions import RobotHasNoTable
from cramera_bridge.plans.regions import RegionBoxes
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.semantic_annotations.semantic_annotations import Table
from semantic_digital_twin.specifications.robots import RobotSpecification
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import FixedConnection
from semantic_digital_twin.world_description.geometry import Box, Scale
from semantic_digital_twin.world_description.shape_collection import ShapeCollection
from semantic_digital_twin.world_description.world_entity import Body

TABLE_HEIGHT = 0.9
"""
The height of the near table's top, in metres.
"""


def robot_on_the_floor() -> PR2:
    """
    :return: A PR2 standing at the origin of a world of its own.
    """
    world = World.create_with_root_body("map")
    return RobotSpecification(semantic_annotation_type=PR2).spawn(world)


def add_table(
    world: World, name: str, x: float, height: float, annotated: bool = True
) -> Body:
    """
    :param world: The world receiving the table.
    :param name: The table's name.
    :param x: Where the middle of its 0.6 m deep top lies in front of the origin.
    :param height: How high its top stands above the floor.
    :param annotated: Whether the table is annotated as one.
    :return: The table's body, a solid box standing on the floor.
    """
    shape = Box(scale=Scale(0.6, 1.2, height))
    body = Body(
        name=PrefixedName(name),
        visual=ShapeCollection([shape]),
        collision=ShapeCollection([Box(scale=Scale(0.6, 1.2, height))]),
    )
    with world.modify_world():
        world.add_connection(
            FixedConnection(
                parent=world.root,
                child=body,
                parent_T_connection_expression=HomogeneousTransformationMatrix.from_xyz_rpy(
                    x=x, z=height / 2, reference_frame=world.root
                ),
            )
        )
        if annotated:
            world.add_semantic_annotation(Table(root=body))
    return body


@pytest.fixture(scope="module")
def robot_at_two_tables() -> PR2:
    """
    :return: A PR2 on the floor with a table in front of it and a lower one further
        away.
    """
    robot = robot_on_the_floor()
    add_table(robot._world, "near_table", 0.7, TABLE_HEIGHT)
    add_table(robot._world, "far_table", 3.0, 0.7)
    return robot


def test_a_robot_on_the_floor_uses_the_table_nearest_to_it(robot_at_two_tables):
    boxes = RegionBoxes(robot_at_two_tables)

    assert boxes.table_body().name.name == "near_table"
    table = boxes.table()
    assert [table.min_x, table.max_x, table.min_y, table.max_y] == pytest.approx(
        [0.4, 1.0, -0.6, 0.6]
    )
    assert table.min_z == pytest.approx(TABLE_HEIGHT)


def test_a_robot_on_the_floor_at_no_table_has_none_to_look_at():
    robot = robot_on_the_floor()
    add_table(robot._world, "unannotated_box", 0.7, TABLE_HEIGHT, annotated=False)

    with pytest.raises(RobotHasNoTable):
        RegionBoxes(robot).table()
