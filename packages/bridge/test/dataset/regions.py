"""
A region added to a test world, which the scene draws no geometry for.
"""

from __future__ import annotations

from dataclasses import dataclass

from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import FixedConnection
from semantic_digital_twin.world_description.geometry import Box, Scale
from semantic_digital_twin.world_description.shape_collection import ShapeCollection
from semantic_digital_twin.world_description.world_entity import Body, Region

# %% regions


@dataclass
class RegionOverBody:
    """
    A box-shaped region fixed above a body, its box offset from the region's origin.
    """

    region: Region
    """
    The region.
    """

    @classmethod
    def build(
        cls,
        world: World,
        body: Body,
        height: float,
        box_offset: float,
        size: Scale,
    ) -> RegionOverBody:
        """
        :param world: The world the body is in.
        :param body: The body the region is fixed to.
        :param height: How far above the body's origin the region's origin lies.
        :param box_offset: How far along its own x axis the box lies from the region's
            origin.
        :param size: The box's size.
        :return: The region, added to the world.
        """
        region = Region(
            name=PrefixedName("drop_zone", "kitchen"),
            area=ShapeCollection(
                shapes=[
                    Box(
                        origin=HomogeneousTransformationMatrix.from_xyz_rpy(
                            x=box_offset
                        ),
                        scale=size,
                    )
                ]
            ),
        )
        with world.modify_world():
            world.add_kinematic_structure_entity(region)
            world.add_connection(
                FixedConnection(
                    parent=body,
                    child=region,
                    parent_T_connection_expression=HomogeneousTransformationMatrix.from_xyz_rpy(
                        z=height
                    ),
                )
            )
        return cls(region=region)
