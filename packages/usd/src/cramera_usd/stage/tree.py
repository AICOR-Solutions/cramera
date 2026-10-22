"""
The links of a conversion and the joints connecting them into one tree rooted in the
world.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pxr import Sdf
from typing_extensions import Dict, List, Optional

from cramera_protocol.bundle.conversion_report import SkipReason
from cramera_usd.geometry.transforms import RigidTransform
from cramera_usd.names import GeneratedName, PrimNames, PrimPath
from cramera_usd.scene.kinematics import (
    AllowedMotion,
    Joint,
    JointKind,
    Link,
    LinkMesh,
)
from cramera_usd.scene.log import ConversionLog
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.partition import LinkPartition

# %% links under construction


@dataclass
class LinkRecord:
    """
    A link while the kinematic tree is being built.
    """

    path: str
    """
    The prim the link stands for.
    """

    name: str
    """
    The unique link name.
    """

    prim_pose: RigidTransform
    """
    The rigid world pose of the prim.
    """

    pose: RigidTransform
    """
    The link frame in the world.
    """

    parent: Optional[str] = None
    """
    The path of the parent link, None for the root and before attachment.
    """

    joint: Optional[Joint] = None
    """
    The joint connecting the link to its parent.
    """

    joint_frame: Optional[RigidTransform] = None
    """
    The world pose of a movable joint's frame at joint value zero.
    """

    is_body: bool = False
    """
    Whether the prim is a rigid or joint body.
    """

    meshes: List[LinkMesh] = field(default_factory=list)
    """
    The visual geometry in the link frame.
    """


# %% tree


@dataclass
class KinematicTree:
    """
    The links of a conversion and the joints connecting them into one tree rooted in the
    world.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    partition: LinkPartition
    """
    The partition of prims into links.
    """

    link_names: PrimNames
    """
    The names of links.
    """

    joint_names: PrimNames
    """
    The names of joints.
    """

    log: ConversionLog
    """
    The log collecting skipped joints.
    """

    links: Dict[str, LinkRecord] = field(default_factory=dict)
    """
    The links by prim path.
    """

    @property
    def root_path(self) -> str:
        """
        The path of the root link's prim.
        """
        return self.partition.root_path

    def build(self, joints: List[Joint], geometry_links: List[str]) -> None:
        """
        Create the links (bodies, assets, and groups holding geometry), connect joint
        children to their parents, attach every other link to the nearest link above it,
        and place each joint.

        :param joints: The joints read from the stage.
        :param geometry_links: The link path of every renderable geometry prim.
        """
        self.add_link(self.root_path, False)
        for path in sorted(self.partition.bodies):
            self.add_link(path, True)
        for path in sorted(self.partition.assets | set(geometry_links)):
            self.add_link(path, False)
        for joint in sorted(joints, key=lambda joint: (not joint.enabled, joint.path)):
            self.connect(joint)
        for path in sorted(self.links):
            if path != self.root_path and self.links[path].parent is None:
                self.attach(path)
        for record in self.links.values():
            if record.joint is not None:
                self.place(record)

    def add_link(self, path: str, is_body: bool) -> None:
        """
        Create a link for a prim once, framed at the prim's rigid world pose.

        :param path: The prim path.
        :param is_body: Whether the prim is a rigid or joint body.
        """
        if path in self.links:
            return
        prim = self.frame.stage.GetPrimAtPath(path)
        pose = (
            self.frame.world_pose(prim)
            if prim and not prim.IsPseudoRoot() and path != self.root_path
            else RigidTransform()
        )
        self.links[path] = LinkRecord(
            path, self.link_names.name_of(path), pose, pose, is_body=is_body
        )

    def ancestors(self, path: str) -> List[str]:
        """
        :param path: A link path.
        :return: The chain of parent links above the link, as far as it is connected
            yet.
        """
        chain = []
        parent = self.links[path].parent
        while parent is not None and parent not in chain:
            chain.append(parent)
            parent = self.links[parent].parent
        return chain

    def connect(self, joint: Joint) -> None:
        """
        Make a joint's child body a child link of the link holding its parent body (for
        a joint to the world, of the static asset enclosing the child), unless that
        would give the child a second parent or close a loop, which is logged.

        :param joint: The joint.
        """
        child = joint.child_body
        parent = (
            self.static_asset_above(child)
            if joint.parent_body is None
            else self.partition.link_path_of(joint.parent_body)
        )
        if (
            child not in self.links
            or child == self.root_path
            or self.links[child].parent is not None
            or parent == child
            or child in self.ancestors(parent)
        ):
            self.log.skip(SkipReason.LOOP_CLOSING_JOINT, joint.path)
            return
        record = self.links[child]
        parent_body_pose = (
            RigidTransform()
            if joint.parent_body is None
            else self.frame.world_pose(
                self.frame.stage.GetPrimAtPath(joint.parent_body)
            )
        )
        if joint.movable:
            record.joint_frame = parent_body_pose @ joint.parent_body_to_joint
            record.pose = record.joint_frame @ joint.motion.transform(
                joint.initial_value
            )
        else:
            record.pose = record.prim_pose @ joint.child_body_to_joint
        joint.parent = self.links[parent].name
        joint.child = record.name
        record.parent = parent
        record.joint = joint

    def static_asset_above(self, path: str) -> str:
        """
        :param path: A prim path.
        :return: The asset link enclosing the prim when no rigid body lies between it
            and the world, else the root: the link a joint to the world can hang from
            without changing what it is fixed to.
        """
        if self.partition.body_above(path):
            return self.root_path
        return self.partition.nearest_asset_above(path, self.root_path)

    def attach(self, path: str) -> None:
        """
        Attach a link without a joint to the nearest link above its prim with a fixed
        joint at its authored pose (to the root if that would close a loop).

        :param path: The link path.
        """
        record = self.links[path]
        parent = self.nearest_link_above(path)
        if path in self.ancestors(parent) or parent == path:
            parent = self.root_path
        record.parent = parent
        record.joint = Joint(
            name=self.joint_names.name_of(
                PrimPath(path).child(GeneratedName.ATTACHMENT)
            ),
            path=path,
            motion=AllowedMotion(JointKind.FIXED),
            parent=self.links[parent].name,
            child=record.name,
        )

    def place(self, record: LinkRecord) -> None:
        """
        Set a joint's origin from the final link frames: the joint frame (movable
        joints) or the child link frame (fixed joints) in the parent link frame.

        :param record: The child link of the joint.
        """
        parent_pose = self.links[record.parent].pose
        placed = record.joint_frame if record.joint_frame is not None else record.pose
        record.joint.origin = parent_pose.inverse() @ placed

    def nearest_link_above(self, path: str) -> str:
        """
        :param path: A link path.
        :return: The link of the closest ancestor prim that has one, else the root.
        """
        current = Sdf.Path(path).GetParentPath()
        while not current.IsAbsoluteRootPath() and not current.isEmpty:
            if current.pathString in self.links:
                return current.pathString
            current = current.GetParentPath()
        return self.root_path

    def link_name_of(self, path: str) -> str:
        """
        :param path: A prim path.
        :return: The name of the link the prim belongs to: the nearest link at or above
            it.
        """
        current = Sdf.Path(path)
        while not current.IsAbsoluteRootPath() and not current.isEmpty:
            if current.pathString in self.links:
                return self.links[current.pathString].name
            current = current.GetParentPath()
        return self.links[self.root_path].name

    def order(self) -> List[str]:
        """
        :return: The link paths with every parent before its children.
        """
        children: Dict[str, List[str]] = {}
        for path, record in self.links.items():
            if record.parent is not None:
                children.setdefault(record.parent, []).append(path)
        ordered = [self.root_path]
        for path in ordered:
            ordered += sorted(children.get(path, []))
        return ordered

    def converted_links(self) -> List[Link]:
        """
        :return: The links, parents before children.
        """
        return [
            Link(
                name=self.links[path].name,
                path=path,
                pose=self.links[path].pose,
                prim_to_link=self.links[path].prim_pose.inverse()
                @ self.links[path].pose,
                meshes=self.links[path].meshes,
                free=self.free(path),
            )
            for path in self.order()
        ]

    def free(self, path: str) -> bool:
        """
        :param path: A link path.
        :return: Whether the link moves with a rigid body that no authored joint
            connects to the world: the link itself, or a link above it, is a body
            attached by a generated fixed joint.
        """
        for current in [path, *self.ancestors(path)]:
            record = self.links[current]
            if record.is_body and record.joint is not None and record.joint.generated:
                return True
        return False

    def converted_joints(self) -> List[Joint]:
        """
        :return: The joints, in the order of their child links.
        """
        return [
            self.links[path].joint
            for path in self.order()
            if self.links[path].joint is not None
        ]
