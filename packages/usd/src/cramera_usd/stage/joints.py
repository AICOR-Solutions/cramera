"""
Reading UsdPhysics joints: their kind, frames, axis, limits and the joint value the
authored body poses imply.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from pxr import Gf, Sdf, Usd, UsdPhysics
from typing_extensions import Optional

from cramera_protocol.bundle.conversion_report import (
    DetachedBody,
    ExcludedPrim,
    SkipReason,
)
from cramera_usd.geometry.axes import Axis
from cramera_usd.geometry.transforms import (
    HOMOGENEOUS_SIZE,
    SPACE_DIMENSIONS,
    RigidTransform,
)
from cramera_usd.scene.joint_graph import JointGraph
from cramera_usd.scene.kinematics import AllowedMotion, Joint, JointKind
from cramera_usd.scene.log import ConversionLog
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.robots import PrimExclusion

# %% constants

RADIANS_PER_DEGREE = float(numpy.radians(1.0))
"""
The angle of one degree in radians.
"""

# %% joint ends


@dataclass(frozen=True)
class JointEnd:
    """
    One body a joint connects, with the joint frame in the body's local coordinates.
    """

    body: Optional[Usd.Prim]
    """
    The body, or None for the world.
    """

    local_frame: numpy.ndarray
    """
    The joint frame in the body's (scaled) local coordinates, as a 4x4 matrix.
    """


# %% reader


@dataclass
class JointReader:
    """
    Reads UsdPhysics joints.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    log: ConversionLog
    """
    The log collecting skipped joints and unsupported joint types.
    """

    exclusion: PrimExclusion
    """
    The prims the conversion leaves out together with their subtrees.
    """

    def read(self, prim: Usd.Prim, name: str) -> Optional[Joint]:
        """
        :param prim: A joint prim.
        :param name: The joint's unique name.
        :return: The joint, not yet placed between links, or None (logged) when it
            names no body or a body the conversion leaves out.
        """
        joint = UsdPhysics.Joint(prim)
        path = prim.GetPath().pathString
        if self.joins_excluded_prim(joint):
            self.log.skip(SkipReason.JOINT_TO_EXCLUDED_PRIM, path)
            return None
        first = JointEnd(
            self.body_of(joint.GetBody0Rel()),
            self.local_frame(joint.GetLocalPos0Attr(), joint.GetLocalRot0Attr()),
        )
        second = JointEnd(
            self.body_of(joint.GetBody1Rel()),
            self.local_frame(joint.GetLocalPos1Attr(), joint.GetLocalRot1Attr()),
        )
        only_first = second.body is None and first.body is not None
        if only_first:
            first, second = second, first
        if second.body is None:
            self.log.skip(SkipReason.JOINT_WITHOUT_CHILD, path)
            return None
        motion = self.motion_of(prim)
        if only_first:
            motion = motion.reversed()
        return self.joint_between(name, path, motion, first, second, joint)

    def joint_between(
        self,
        name: str,
        path: str,
        motion: AllowedMotion,
        parent: JointEnd,
        child: JointEnd,
        joint: UsdPhysics.Joint,
    ) -> Joint:
        """
        :param name: The joint's unique name.
        :param path: The joint prim's path.
        :param motion: The motion the joint allows.
        :param parent: The body the child moves relative to, or the world.
        :param child: The body the joint moves.
        :param joint: The joint prim.
        :return: The joint, with its initial value recovered from the body poses.
        """
        parent_matrix = (
            self.frame.correction
            if parent.body is None
            else self.frame.world_matrix(parent.body)
        )
        parent_body_to_joint = self.body_to_joint(parent_matrix, parent.local_frame)
        if parent.body is None:
            parent_body_to_joint = (
                RigidTransform.rigid_part(parent_matrix) @ parent_body_to_joint
            )
        imported = Joint(
            name=name,
            path=path,
            motion=motion,
            parent_body=(
                None if parent.body is None else parent.body.GetPath().pathString
            ),
            child_body=child.body.GetPath().pathString,
            parent_body_to_joint=parent_body_to_joint,
            child_body_to_joint=self.body_to_joint(
                self.frame.world_matrix(child.body), child.local_frame
            ),
            enabled=joint.GetJointEnabledAttr().Get(self.frame.time) is not False,
        )
        imported.initial_value = imported.value_between(
            (
                RigidTransform()
                if parent.body is None
                else RigidTransform.rigid_part(parent_matrix)
            ),
            self.frame.world_pose(child.body),
        )
        return imported

    def joins_excluded_prim(self, joint: UsdPhysics.Joint) -> bool:
        """
        :param joint: A joint.
        :return: Whether a body of the joint lies in a subtree the conversion leaves
            out, inside the converted prims or beside them.
        """
        targets = [*joint.GetBody0Rel().GetTargets(), *joint.GetBody1Rel().GetTargets()]
        return any(self.left_out(target) is not None for target in targets)

    def left_out(self, path: Sdf.Path) -> Optional[ExcludedPrim]:
        """
        :param path: The USD path of a body.
        :return: The outermost prim holding the body that the conversion leaves out, or
            None.
        """
        return self.exclusion.left_out_holding(self.frame.stage, path, self.frame.time)

    def detached_body(
        self, prim: Usd.Prim, graph: JointGraph
    ) -> Optional[DetachedBody]:
        """
        :param prim: A joint prim.
        :param graph: The converted joints, to find the movable joints below the body.
        :return: The converted body the joint hangs from a left-out parent body, or
            None when the joint holds no such body.
        """
        joint = UsdPhysics.Joint(prim)
        parent = self.body_of(joint.GetBody0Rel())
        child = self.body_of(joint.GetBody1Rel())
        if parent is None or child is None:
            return None
        if self.left_out(child.GetPath()) is not None:
            return None
        if self.left_out(parent.GetPath()) is None:
            return None
        body = child.GetPath().pathString
        return DetachedBody(
            body=body,
            parent_body=parent.GetPath().pathString,
            joint=prim.GetPath().pathString,
            movable_joints=graph.movable_joints_below({body}),
        )

    def body_of(self, relationship: Usd.Relationship) -> Optional[Usd.Prim]:
        """
        :param relationship: ``physics:body0`` or ``physics:body1``.
        :return: The active prim the relationship targets, or None.
        """
        targets = relationship.GetTargets()
        if not targets:
            return None
        prim = self.frame.stage.GetPrimAtPath(targets[0])
        return prim if prim and prim.IsActive() else None

    def local_frame(
        self, position: Usd.Attribute, rotation: Usd.Attribute
    ) -> numpy.ndarray:
        """
        :param position: ``physics:localPos0`` or ``physics:localPos1``.
        :param rotation: ``physics:localRot0`` or ``physics:localRot1``.
        :return: The joint frame in its body's (scaled) local coordinates, as a 4x4
            matrix.
        """
        matrix = numpy.eye(HOMOGENEOUS_SIZE)
        quaternion = rotation.Get(self.frame.time)
        if quaternion is not None:
            matrix[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = numpy.array(
                Gf.Matrix3d(Gf.Rotation(Gf.Quatd(quaternion)))
            ).T
        translation = position.Get(self.frame.time)
        if translation is not None:
            matrix[:SPACE_DIMENSIONS, SPACE_DIMENSIONS] = numpy.asarray(
                translation, dtype=float
            )
        return matrix

    @staticmethod
    def body_to_joint(
        body_matrix: numpy.ndarray, local: numpy.ndarray
    ) -> RigidTransform:
        """
        :param body_matrix: The body's world matrix (or the stage correction for the
            world).
        :param local: The joint frame in the body's local coordinates.
        :return: The joint frame relative to the rigid frame of its body: the position
            goes through the body's full (possibly scaled) transform, the rotation
            through its rigid part.
        """
        body = RigidTransform.rigid_part(body_matrix)
        world = RigidTransform.from_parts(
            body.rotation @ local[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS],
            (body_matrix @ local[:, SPACE_DIMENSIONS])[:SPACE_DIMENSIONS],
        )
        return body.inverse() @ world

    def motion_of(self, prim: Usd.Prim) -> AllowedMotion:
        """
        :param prim: A joint prim.
        :return: The motion the joint allows, with its limits in radians or metres; a
            joint type without a URDF counterpart is logged and written as fixed.
        """
        if prim.IsA(UsdPhysics.RevoluteJoint):
            joint = UsdPhysics.RevoluteJoint(prim)
            lower = self.limit(joint.GetLowerLimitAttr(), RADIANS_PER_DEGREE)
            upper = self.limit(joint.GetUpperLimitAttr(), RADIANS_PER_DEGREE)
            kind = (
                JointKind.CONTINUOUS
                if lower is None and upper is None
                else JointKind.REVOLUTE
            )
            return AllowedMotion(
                kind, Axis(joint.GetAxisAttr().Get()).direction, lower, upper
            )
        if prim.IsA(UsdPhysics.PrismaticJoint):
            joint = UsdPhysics.PrismaticJoint(prim)
            scale = self.frame.meters_per_unit
            return AllowedMotion(
                JointKind.PRISMATIC,
                Axis(joint.GetAxisAttr().Get()).direction,
                self.limit(joint.GetLowerLimitAttr(), scale),
                self.limit(joint.GetUpperLimitAttr(), scale),
            )
        if not prim.IsA(UsdPhysics.FixedJoint):
            self.log.warnings.append(
                f"{prim.GetPath()}: {prim.GetTypeName()} is written as a fixed joint"
            )
        return AllowedMotion(JointKind.FIXED, Axis.X.direction)

    def limit(self, attribute: Usd.Attribute, scale: float) -> Optional[float]:
        """
        :param attribute: A limit attribute.
        :param scale: Degrees to radians, or stage units to metres.
        :return: The finite limit in radians or metres, or None when it is unset or
            infinite.
        """
        value = attribute.Get(self.frame.time)
        if value is None or not numpy.isfinite(value):
            return None
        return float(value) * scale
