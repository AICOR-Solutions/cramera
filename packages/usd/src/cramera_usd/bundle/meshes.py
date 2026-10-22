"""
The GLB files of a bundle: one per link with geometry of every model, and one per
object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Any, Dict, List, Set

from cramera_protocol.bundle.files import BundleFile, MeshFormat
from cramera_protocol.bundle.semantics import SemanticNamespace
from cramera_usd.animation.models import AnimatedObject, KinematicModel
from cramera_usd.bundle.layout import ANY_NAME, BundleLayout
from cramera_usd.gltf.link import LinkGltf
from cramera_usd.materials.physically_based import PhysicallyBasedMaterial
from cramera_usd.scene.kinematics import Link

# %% meshes


@dataclass
class MeshFiles:
    """
    Writes the GLB files of a bundle and removes those a previous conversion left for
    links that no longer exist.
    """

    layout: BundleLayout
    """
    The files of the bundle.
    """

    materials: Dict[str, PhysicallyBasedMaterial]
    """
    The glTF material of every authored material.
    """

    semantics: Dict[str, Dict[SemanticNamespace, Dict[str, Any]]]
    """
    The semantic attributes by prim path, stored on the GLB nodes.
    """

    written: Set[Path] = field(default_factory=set)
    """
    The GLB files written so far.
    """

    def write_models(self, models: List[KinematicModel]) -> None:
        """
        Write one GLB per link with geometry of every model.

        :param models: The bundle's models.
        """
        for model in models:
            for link in model.links:
                if link.meshes:
                    self.write(link, self.layout.mesh_file(model, link.name))

    def write_objects(self, objects: List[AnimatedObject]) -> None:
        """
        Write one GLB per object.

        :param objects: The objects of the playback.
        """
        for moving in objects:
            self.write(moving.link, self.layout.object_mesh(moving.key))

    def write(self, link: Link, relative: str) -> None:
        """
        Write one link's GLB.

        :param link: The link.
        :param relative: The GLB file, relative to the bundle.
        """
        path = self.layout.file(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(LinkGltf(link, self.materials, self.semantics).encode())
        self.written.add(path)

    def remove_stale(self) -> None:
        """
        Remove the GLBs below the mesh directory that were not written.
        """
        meshes = self.layout.file(BundleFile.MESHES)
        for stale in set(meshes.rglob(f"{ANY_NAME}{MeshFormat.GLB}")) - self.written:
            stale.unlink()
