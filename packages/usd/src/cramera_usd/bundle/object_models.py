"""
The URDF files of a bundle's free objects: one per object with collision boxes, holding
the object's GLB and its boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from typing_extensions import List, Set

from cramera_protocol.bundle.files import BundleFile
from cramera_usd.animation.models import AnimatedObject
from cramera_usd.bundle.layout import ANY_NAME, BundleLayout, FileSuffix
from cramera_usd.urdf import UrdfDocument

# %% object models


@dataclass
class ObjectModelFiles:
    """
    Writes the URDF of every free object with collision boxes and removes those a
    previous conversion left for objects that no longer exist.
    """

    layout: BundleLayout
    """
    The files of the bundle.
    """

    written: Set[Path] = field(default_factory=set)
    """
    The URDF files written so far.
    """

    def write(self, objects: List[AnimatedObject]) -> None:
        """
        Write one URDF per object with collision boxes.

        :param objects: The bundle's objects.
        """
        for moving in objects:
            if not moving.link.collisions:
                continue
            path = self.layout.file(BundleLayout.object_model(moving.key))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.document(moving).to_bytes())
            self.written.add(path)

    @staticmethod
    def document(moving: AnimatedObject) -> UrdfDocument:
        """
        :param moving: An object.
        :return: Its URDF: one link named after the object's key, its GLB as visual.
        """
        return UrdfDocument(
            moving.key,
            [replace(moving.link, name=moving.key)],
            [],
            {moving.key: BundleLayout.object_model_mesh(moving.key)},
        )

    def remove_stale(self) -> None:
        """
        Remove the object URDFs that were not written.
        """
        directory = self.layout.file(BundleFile.OBJECT_MODELS)
        for stale in set(directory.glob(f"{ANY_NAME}{FileSuffix.URDF}")) - self.written:
            stale.unlink()
