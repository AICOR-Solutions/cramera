"""
The meshes of one link that share a material, concatenated into one glTF primitive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from typing_extensions import List, Optional, Self

from cramera_usd.geometry.meshes import TEXTURE_DIMENSIONS
from cramera_usd.scene.kinematics import LinkMesh

# %% constants

V_COLUMN = 1
"""
The column of the V texture coordinate.
"""

# %% merged meshes


@dataclass(eq=False)
class MergedMesh:
    """
    The meshes of one link that share a material, concatenated into one primitive.
    """

    points: numpy.ndarray
    """
    ``(N, 3)`` float32 positions.
    """

    triangles: numpy.ndarray
    """
    ``(M, 3)`` uint32 indices.
    """

    normals: Optional[numpy.ndarray]
    """
    ``(N, 3)`` float32 normals, or None when no source mesh has any.
    """

    texture_coordinates: Optional[numpy.ndarray]
    """
    ``(N, 2)`` float32 glTF texture coordinates (V flipped), or None.
    """

    @classmethod
    def of_meshes(cls, meshes: List[LinkMesh], textured: bool) -> Self:
        """
        A mesh without normals gets area-weighted vertex normals when others have
        normals; a mesh without texture coordinates gets zeros when the material is
        textured.

        :param meshes: The meshes sharing one material.
        :param textured: Whether the material reads texture coordinates.
        :return: The meshes concatenated, USD's texture V axis flipped into glTF's.
        """
        geometries = [mesh.geometry for mesh in meshes]
        offsets = numpy.cumsum([0] + [len(geometry.points) for geometry in geometries])
        with_normals = any(geometry.normals is not None for geometry in geometries)
        return cls(
            points=numpy.concatenate(
                [geometry.points for geometry in geometries]
            ).astype(numpy.float32),
            triangles=numpy.concatenate(
                [
                    geometry.triangles + offset
                    for geometry, offset in zip(geometries, offsets)
                ]
            ).astype(numpy.uint32),
            normals=(
                numpy.concatenate(
                    [geometry.vertex_normals() for geometry in geometries]
                ).astype(numpy.float32)
                if with_normals
                else None
            ),
            texture_coordinates=(
                numpy.concatenate(
                    [cls.flipped_coordinates(mesh) for mesh in meshes]
                ).astype(numpy.float32)
                if textured
                else None
            ),
        )

    @staticmethod
    def flipped_coordinates(mesh: LinkMesh) -> numpy.ndarray:
        """
        :param mesh: A mesh.
        :return: Its texture coordinates with V flipped (USD's origin is bottom left,
            glTF's top left), or zeros when the mesh has none.
        """
        geometry = mesh.geometry
        if geometry.texture_coordinates is None:
            return numpy.zeros(
                (len(geometry.points), TEXTURE_DIMENSIONS), dtype=numpy.float32
            )
        flipped = geometry.texture_coordinates.astype(numpy.float32).copy()
        flipped[:, V_COLUMN] = 1.0 - flipped[:, V_COLUMN]
        return flipped
