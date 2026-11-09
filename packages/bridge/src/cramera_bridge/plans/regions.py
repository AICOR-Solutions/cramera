"""
The regions of a scene a step looks for objects in, as the native boxes CRAM's
perception queries take.
"""

from __future__ import annotations

from dataclasses import dataclass

from cramera_bridge.exceptions import RobotHasNoTable
from cramera_protocol.detection import DetectionRegion, RegionKind
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.robots.robot_part_mixins import HasMountingTable
from semantic_digital_twin.robots.robot_parts import AbstractRobot
from semantic_digital_twin.world_description.geometry import VolumetricBoundingBox
from semantic_digital_twin.world_description.shape_collection import ShapeCollection

# %% regions


@dataclass(frozen=True)
class RegionBoxes:
    """
    Turns the regions a plan names into boxes in the world of the robot that looks.
    """

    robot: AbstractRobot
    """
    The robot looking, whose table the regions lie on.
    """

    height_above_table: float = 0.3
    """
    How far above the table top, in metres, a region on the table reaches.
    """

    def box(self, region: DetectionRegion) -> VolumetricBoundingBox:
        """
        :param region: A region of the plan.
        :return: The box it spans in the world's root frame.
        """
        match region.kind:
            case RegionKind.TABLE:
                return self.table()

    def table(self) -> VolumetricBoundingBox:
        """
        :return: The box above the whole top of the robot's table, up to
            :attr:`height_above_table`.
        :raises RobotHasNoTable: When the robot is mounted on no table.
        """
        if not isinstance(self.robot, HasMountingTable):
            raise RobotHasNoTable(type(self.robot).__name__)
        table = self.robot.table.root
        world = table._world
        tabletop = max(table.collision, key=lambda shape: shape.scale.x * shape.scale.y)
        top = (
            ShapeCollection([tabletop], reference_frame=table)
            .as_bounding_box_collection_in_frame(world.root)
            .bounding_box()
        )
        return VolumetricBoundingBox(
            min_x=top.min_x,
            min_y=top.min_y,
            min_z=top.max_z,
            max_x=top.max_x,
            max_y=top.max_y,
            max_z=top.max_z + self.height_above_table,
            origin=HomogeneousTransformationMatrix(reference_frame=world.root),
        )
