"""
The free objects of a world: bodies that move on their own rather than as part of the
robot or the environment model.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import TYPE_CHECKING, Iterable, List, Set
from uuid import UUID

from cramera_cram.robots import RobotRoster
from semantic_digital_twin.world_description.connections import Connection6DoF
from semantic_digital_twin.world_description.world_entity import Body

if TYPE_CHECKING:
    from semantic_digital_twin.world import World

# %% discovery


@dataclass(frozen=True)
class WorldObjects:
    """
    Selects a world's free objects from its connections, identifying bodies by UUID.

    A free object is a body held by a connection with six degrees of freedom that is
    neither part of a robot nor carries one, together with the shaped bodies fixed below
    it. An object stays tracked while it is attached to a gripper or a support, until it
    leaves the world.
    """

    world: World
    """
    The world whose current bodies are read.
    """

    def robot_bodies(self) -> Set[UUID]:
        """
        :return: The identities of every body of every robot.
        """
        return {
            body.id
            for robot in RobotRoster(self.world).robots()
            for body in robot.bodies
        }

    def robot_carriers(self) -> Set[UUID]:
        """
        :return: The identities of the bodies above a robot's root, such as the odometry
            frame a robot drives in.
        """
        carriers: Set[UUID] = set()
        for robot in RobotRoster(self.world).robots():
            connection = robot.root.parent_connection
            while connection is not None:
                carriers.add(connection.parent.id)
                connection = connection.parent.parent_connection
        return carriers

    def free_roots(self) -> List[Body]:
        """
        :return: The bodies held by six degrees of freedom outside every robot.
        """
        excluded = self.robot_bodies() | self.robot_carriers()
        return [
            body
            for body in self.world.bodies
            if isinstance(body.parent_connection, Connection6DoF)
            and body.id not in excluded
        ]

    def objects(self, tracked: Iterable[UUID] = ()) -> List[Body]:
        """
        :param tracked: Identities of objects published before, which stay objects
            after a grasp or a placement attached them to another body.
        :return: The free objects, in the order the world holds them.
        """
        robot_bodies = self.robot_bodies()
        roots = {body.id for body in self.free_roots()} | set(tracked)
        present = [body for body in self.world.bodies if body.id in roots]
        published = {body.id for body in present}
        for root in present:
            for entity in self.world.get_kinematic_structure_entities_of_branch(root):
                if (
                    isinstance(entity, Body)
                    and entity.id not in robot_bodies
                    and (entity.visual.shapes or entity.collision.shapes)
                ):
                    published.add(entity.id)
        return [body for body in self.world.bodies if body.id in published]
