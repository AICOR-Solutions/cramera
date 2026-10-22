"""
The GLB file of one link: its meshes merged per material, one node per material.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from typing_extensions import Any, Dict, List

from cramera_protocol.bundle.semantics import SemanticNamespace
from cramera_usd.gltf.document import GltfDocument
from cramera_usd.gltf.format import NodeExtra
from cramera_usd.gltf.merged import MergedMesh
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.scene.kinematics import Link, LinkMesh

# %% link


@dataclass
class LinkGltf:
    """
    The GLB file of one link: its meshes merged per material, one node per material.
    """

    link: Link
    """
    The link whose meshes are written, in the link frame.
    """

    materials: Dict[str, PhysicallyBasedMaterial]
    """
    The mapped material for every material name the meshes use.
    """

    semantics: Dict[str, Dict[SemanticNamespace, Dict[str, Any]]] = field(
        default_factory=dict
    )
    """
    Semantic attributes by prim path, stored on the nodes as ``extras``.
    """

    def groups(self) -> Dict[PhysicallyBasedMaterial, List[LinkMesh]]:
        """
        :return: The link's meshes grouped by the material they are drawn with, in the
            order the materials first appear.
        """
        groups: Dict[PhysicallyBasedMaterial, List[LinkMesh]] = {}
        for mesh in self.link.meshes:
            material = self.materials[mesh.material]
            if mesh.double_sided:
                material = material.with_double_sides()
            groups.setdefault(material, []).append(mesh)
        return groups

    def encode(self) -> bytes:
        """
        :return: The link's GLB file.
        """
        document = GltfDocument()
        for material, meshes in self.groups().items():
            paths = [mesh.path for mesh in meshes]
            name = self.common_prim_path(paths)
            extras: Dict[str, Any] = {
                NodeExtra.USD_PATH: name,
                NodeExtra.USD_PATHS: sorted(set(paths)),
            }
            extras.update(self.semantics.get(name, {}))
            document.add_mesh_node(
                name, extras, MergedMesh.of_meshes(meshes, material.textured), material
            )
        return document.encode()

    @staticmethod
    def common_prim_path(paths: List[str]) -> str:
        """
        :param paths: Absolute prim paths.
        :return: The deepest prim path that is an ancestor of (or equal to) every given
            path, which names a node merged from several prims.
        """
        common = os.path.commonpath(paths)
        return common if common != os.sep else paths[0]
