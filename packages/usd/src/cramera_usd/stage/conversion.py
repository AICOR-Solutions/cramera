"""
One conversion of a composed stage: traversal, joints, link partition, kinematic tree,
geometry, lights, cameras and semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy
from pxr import Usd, UsdGeom, UsdPhysics
from typing_extensions import List, Optional, Set

from cramera_protocol.bundle.conversion_report import ReportCount, SkipReason
from cramera_usd.geometry.bounds import PointBounds
from cramera_usd.geometry.transforms import SPACE_DIMENSIONS
from cramera_usd.names import PrimNames
from cramera_usd.scene.joint_graph import JointGraph
from cramera_usd.scene.kinematics import Joint, LinkMesh
from cramera_usd.scene.log import ConversionLog
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.geometry import GeometryReader
from cramera_usd.stage.joints import JointReader
from cramera_usd.stage.lights import CameraReader, LightReader
from cramera_usd.stage.materials import MaterialReader
from cramera_usd.stage.partition import LinkPartition
from cramera_usd.stage.robots import PrimExclusion
from cramera_usd.stage.semantics import SemanticsReader
from cramera_usd.stage.separation import RobotSeparation
from cramera_usd.stage.traversal import StageTraversal
from cramera_usd.stage.tree import KinematicTree

# %% constants

CENTRAL_FRACTION = 0.98
"""
The share of geometry points per axis the dense core of a scene holds.
"""

ABSOLUTE_ROOT = "/"
"""
The path of a stage's pseudo-root, which stands for the world without a default prim.
"""

# %% geometry


@dataclass
class GeometryCollection:
    """
    Reads geometry prims into the links of a kinematic tree, and keeps their world
    points for the scene's bounds.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    reader: GeometryReader
    """
    The geometry reader.
    """

    tree: KinematicTree
    """
    The kinematic tree holding the links.
    """

    log: ConversionLog
    """
    The log collecting skipped geometry.
    """

    world_points: List[numpy.ndarray] = field(
        default_factory=lambda: [numpy.zeros((0, SPACE_DIMENSIONS))]
    )
    """
    The world positions of every mesh read so far.
    """

    def add(self, prim: Usd.Prim) -> None:
        """
        Read one geometry prim into its link.

        :param prim: A renderable geometry prim.
        """
        path = prim.GetPath().pathString
        pieces = self.reader.pieces(prim)
        if pieces is None:
            self.log.skip(SkipReason.UNSUPPORTED_GEOMETRY, path)
            return
        link = self.tree.links[self.tree.partition.link_path_of(path)]
        to_link = link.pose.inverse().matrix @ self.frame.world_matrix(prim)
        double_sided = bool(UsdGeom.Gprim(prim).GetDoubleSidedAttr().Get())
        for piece in pieces:
            if len(piece.mesh.triangles) == 0:
                self.log.skip(SkipReason.EMPTY_GEOMETRY, path)
                continue
            local = piece.mesh.transformed(to_link)
            link.meshes.append(
                LinkMesh(path, local.single_precision(), piece.material, double_sided)
            )
            self.world_points.append(
                local.points @ link.pose.rotation.T + link.pose.translation
            )

    def bounds(self) -> Optional[PointBounds]:
        """
        :return: The box around all points, or None without points.
        """
        points = numpy.concatenate(self.world_points)
        if not len(points):
            return None
        return PointBounds.of_points(points)

    def central_bounds(self) -> Optional[PointBounds]:
        """
        :return: The box around the dense core of the points, or None without points.
        """
        points = numpy.concatenate(self.world_points)
        if not len(points):
            return None
        return PointBounds.central(points, CENTRAL_FRACTION)


# %% conversion


@dataclass
class StageConversion:
    """
    One conversion of a composed stage.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    roots: List[Usd.Prim]
    """
    The prims whose subtrees are converted.
    """

    source: Path
    """
    The stage file.
    """

    exclusion: PrimExclusion = field(default_factory=PrimExclusion)
    """
    The prims left out with their subtrees.
    """

    log: ConversionLog = field(default_factory=ConversionLog)
    """
    What the conversion read, skipped and left out.
    """

    def run(self) -> ConvertedStage:
        """
        :return: The neutral description of the selected prims.
        """
        default_prim = self.frame.stage.GetDefaultPrim()
        root_path = default_prim.GetPath().pathString if default_prim else ABSOLUTE_ROOT
        named_prefix = root_path if default_prim else ""
        traversal = StageTraversal(self.frame, self.roots, self.exclusion, self.log)
        prims = traversal.prims()
        materials = MaterialReader(self.frame, self.log)
        joint_reader = JointReader(self.frame, self.log, self.exclusion)
        joint_names = PrimNames(named_prefix)
        joints = self.joints(prims, joint_reader, joint_names)
        graph = JointGraph(joints)
        separation = RobotSeparation(traversal, joint_reader, graph)
        self.log.detached = separation.detached_bodies(prims)
        self.log.articulations = separation.environment_articulations(
            prims, self.exclusion
        )
        partition = LinkPartition(
            root_path,
            self.bodies(prims, joints),
            LinkPartition.asset_roots(prims, root_path),
        )
        geometry = [prim for prim in prims if traversal.renderable(prim)]
        tree = KinematicTree(
            self.frame,
            partition,
            PrimNames(named_prefix),
            joint_names,
            self.log,
        )
        tree.build(
            joints,
            [partition.link_path_of(prim.GetPath().pathString) for prim in geometry],
        )
        collection = GeometryCollection(
            self.frame, GeometryReader(self.frame, materials), tree, self.log
        )
        for prim in geometry:
            collection.add(prim)
        converted = ConvertedStage(
            source=self.source,
            root_link=tree.links[tree.root_path].name,
            links=tree.converted_links(),
            joints=tree.converted_joints(),
            materials=materials.materials,
            lights=LightReader(self.frame).lights(prims),
            semantics=SemanticsReader(self.frame).semantics(prims, tree.link_name_of),
            cameras=CameraReader(self.frame).cameras(prims),
            bounds=collection.bounds(),
            central_bounds=collection.central_bounds(),
            used_files=self.used_files(materials),
            log=self.log,
        )
        ConversionCounts(converted, prims).fill()
        return converted

    def joints(
        self, prims: List[Usd.Prim], reader: JointReader, names: PrimNames
    ) -> List[Joint]:
        """
        :param prims: The traversed prims.
        :param reader: The joint reader.
        :param names: The names of joints.
        :return: The joints among the prims that connect converted bodies, in
            traversal order.
        """
        return [
            joint
            for prim in prims
            if prim.IsA(UsdPhysics.Joint)
            and (joint := reader.read(prim, names.name_of(prim.GetPath().pathString)))
            is not None
        ]

    @staticmethod
    def bodies(prims: List[Usd.Prim], joints: List[Joint]) -> Set[str]:
        """
        :param prims: The traversed prims.
        :param joints: The converted joints.
        :return: The USD paths of the rigid bodies and of the joints' bodies.
        """
        bodies = {
            prim.GetPath().pathString
            for prim in prims
            if prim.HasAPI(UsdPhysics.RigidBodyAPI)
        }
        bodies |= {joint.child_body for joint in joints}
        bodies |= {
            joint.parent_body for joint in joints if joint.parent_body is not None
        }
        return bodies

    def used_files(self, materials: MaterialReader) -> List[Path]:
        """
        :param materials: The material reader of the conversion.
        :return: The layer files the stage composed and the textures the materials
            read, sorted.
        """
        files = {
            Path(layer.realPath)
            for layer in self.frame.stage.GetUsedLayers()
            if layer.realPath and Path(layer.realPath).is_file()
        }
        for material in materials.materials.values():
            files |= set(material.texture_files())
        return sorted(files)


# %% counts


@dataclass
class ConversionCounts:
    """
    Fills a converted stage's log with the named counts of what was read and written.
    """

    converted: ConvertedStage
    """
    The finished conversion.
    """

    prims: List[Usd.Prim]
    """
    The traversed prims.
    """

    def fill(self) -> None:
        """
        Set every count.
        """
        converted = self.converted
        counts = converted.log.counts
        counts[ReportCount.PRIMS] = len(self.prims)
        counts[ReportCount.INSTANCE_PROXIES] = sum(
            1 for prim in self.prims if prim.IsInstanceProxy()
        )
        counts[ReportCount.LINKS] = len(converted.links)
        counts[ReportCount.MESHES] = sum(len(link.meshes) for link in converted.links)
        counts[ReportCount.TRIANGLES] = sum(
            link.triangle_count for link in converted.links
        )
        counts[ReportCount.MATERIALS] = len(converted.materials)
        counts[ReportCount.LIGHTS] = len(converted.lights)
        counts[ReportCount.SEMANTIC_PRIMS] = len(converted.semantics)
        for joint in converted.joints:
            counts[ReportCount.JOINTS.of_type(joint.motion.kind)] += 1
            counts[ReportCount.DISABLED_JOINTS] += not joint.enabled
