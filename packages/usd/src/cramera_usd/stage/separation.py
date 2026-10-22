"""
What a conversion learns about the separation of robots and environment: the bodies that
hung from a left-out body, and the articulations kept in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxr import Sdf, Usd, UsdPhysics
from typing_extensions import List

from cramera_protocol.bundle.conversion_report import (
    DetachedBody,
    EnvironmentArticulation,
)
from cramera_usd.scene.joint_graph import JointGraph
from cramera_usd.stage.joints import JointReader
from cramera_usd.stage.robots import PrimExclusion
from cramera_usd.stage.traversal import StageTraversal

# %% separation


@dataclass
class RobotSeparation:
    """
    Finds the robot parts and robots a conversion's exclusion may have missed.
    """

    traversal: StageTraversal
    """
    The traversal of the conversion, holding the left-out prims.
    """

    joint_reader: JointReader
    """
    The joint reader of the conversion.
    """

    graph: JointGraph
    """
    The converted joints.
    """

    def detached_bodies(self, prims: List[Usd.Prim]) -> List[DetachedBody]:
        """
        :param prims: The traversed prims.
        :return: The converted bodies that hung from a left-out body, by a joint among
            the converted prims or inside a left-out prim, in joint path order.
        """
        stage = self.traversal.frame.stage
        left_out_joints = [
            prim
            for excluded in self.traversal.log.excluded
            for prim in Usd.PrimRange(
                stage.GetPrimAtPath(excluded.path),
                Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate),
            )
            if prim.IsA(UsdPhysics.Joint)
        ]
        joints = [prim for prim in prims if prim.IsA(UsdPhysics.Joint)]
        detached = [
            body
            for prim in joints + left_out_joints
            if (body := self.joint_reader.detached_body(prim, self.graph)) is not None
            and self.traversal.converts(Sdf.Path(body.body))
        ]
        return sorted(detached, key=lambda body: body.joint)

    def environment_articulations(
        self, prims: List[Usd.Prim], exclusion: PrimExclusion
    ) -> List[EnvironmentArticulation]:
        """
        :param prims: The traversed prims.
        :param exclusion: The prims the conversion leaves out.
        :return: The converted articulation roots outside every robot, each with its
            movable joints; an articulation without any is left out.
        """
        frame = self.traversal.frame
        articulations = []
        for prim in prims:
            if not prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                continue
            path = prim.GetPath()
            if exclusion.belongs_to_robot(frame.stage, path, frame.time):
                continue
            movable = self.graph.movable_joints_below(
                self.graph.bodies_in(path.pathString)
            )
            if movable:
                articulations.append(
                    EnvironmentArticulation(
                        path=path.pathString, movable_joints=movable
                    )
                )
        return articulations
