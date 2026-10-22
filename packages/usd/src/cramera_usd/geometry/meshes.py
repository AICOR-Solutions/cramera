"""
Triangle meshes, and USD polygon meshes with their primvar interpolations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy
from typing_extensions import Optional

from cramera_usd.geometry.transforms import SPACE_DIMENSIONS

# %% constants

TRIANGLE_CORNERS = 3
"""
The number of corners of a triangle, the fewest a face can have.
"""

TEXTURE_DIMENSIONS = 2
"""
The number of texture coordinates per vertex.
"""

NORMAL_COLUMNS = slice(SPACE_DIMENSIONS, 2 * SPACE_DIMENSIONS)
"""
The columns holding the normal in a row of position, normal and texture coordinates.
"""

# %% primvar data


class Interpolation(StrEnum):
    """
    How a primvar's values are spread over a mesh, named as USD names it.
    """

    CONSTANT = "constant"
    """
    One value for the whole mesh.
    """

    UNIFORM = "uniform"
    """
    One value per face.
    """

    VARYING = "varying"
    """
    One value per point, interpolated linearly.
    """

    VERTEX = "vertex"
    """
    One value per point.
    """

    FACE_VARYING = "faceVarying"
    """
    One value per face corner.
    """

    @property
    def follows_points(self) -> bool:
        """
        Whether values of this interpolation belong to the points.
        """
        return self in (Interpolation.VERTEX, Interpolation.VARYING)


@dataclass(eq=False)
class PrimvarData:
    """
    The flattened values of one primvar and how they are spread over the mesh.
    """

    values: numpy.ndarray
    """
    ``(V, D)`` values, already de-indexed.
    """

    interpolation: Interpolation
    """
    How the values map onto points, faces or corners.
    """

    def per_corner(
        self, face_vertex_indices: numpy.ndarray, face_of_corner: numpy.ndarray
    ) -> Optional[numpy.ndarray]:
        """
        :param face_vertex_indices: The point index of every corner.
        :param face_of_corner: The face index of every corner.
        :return: One value per face corner, or None when the number of values does not
            match the interpolation.
        """
        if self.interpolation is Interpolation.CONSTANT:
            return self.repeated(len(face_vertex_indices))
        if self.interpolation is Interpolation.UNIFORM:
            return self.indexed(face_of_corner)
        if self.interpolation is Interpolation.FACE_VARYING:
            return self.leading(len(face_vertex_indices))
        return self.indexed(face_vertex_indices)

    def repeated(self, count: int) -> Optional[numpy.ndarray]:
        """
        :param count: The number of corners.
        :return: The first value for every corner, or None without values.
        """
        if len(self.values) == 0:
            return None
        return numpy.repeat(self.values[:1], count, axis=0)

    def indexed(self, indices: numpy.ndarray) -> Optional[numpy.ndarray]:
        """
        :param indices: The value index of every corner.
        :return: The value of every corner, or None when an index has no value.
        """
        if len(self.values) <= int(indices.max(initial=-1)):
            return None
        return self.values[indices]

    def leading(self, count: int) -> Optional[numpy.ndarray]:
        """
        :param count: The number of corners.
        :return: The first values, one per corner, or None when there are fewer.
        """
        if len(self.values) < count:
            return None
        return self.values[:count]


# %% triangle meshes


@dataclass(eq=False)
class TriangleMesh:
    """
    Indexed triangles with optional normals and texture coordinates per vertex.
    """

    points: numpy.ndarray
    """
    ``(N, 3)`` positions.
    """

    triangles: numpy.ndarray
    """
    ``(M, 3)`` vertex indices, counter-clockwise seen from outside.
    """

    normals: Optional[numpy.ndarray] = None
    """
    ``(N, 3)`` unit normals.
    """

    texture_coordinates: Optional[numpy.ndarray] = None
    """
    ``(N, 2)`` texture coordinates.
    """

    faces: Optional[numpy.ndarray] = None
    """
    ``(M,)`` index of the source polygon of every triangle.
    """

    def subset(self, keep: numpy.ndarray) -> TriangleMesh:
        """
        :param keep: A boolean mask over the triangles.
        :return: The selected triangles, with unused vertices dropped.
        """
        triangles = self.triangles[keep]
        used, remapped = numpy.unique(triangles, return_inverse=True)
        return TriangleMesh(
            points=self.points[used],
            triangles=remapped.reshape(-1, TRIANGLE_CORNERS).astype(numpy.uint32),
            normals=None if self.normals is None else self.normals[used],
            texture_coordinates=(
                None
                if self.texture_coordinates is None
                else self.texture_coordinates[used]
            ),
            faces=None if self.faces is None else self.faces[keep],
        )

    def transformed(self, matrix: numpy.ndarray) -> TriangleMesh:
        """
        :param matrix: A homogeneous 4x4 affine matrix acting on column vectors.
        :return: The mesh under the transform; a mirroring transform reverses the
            winding so the triangles keep facing outwards.
        """
        linear = matrix[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS]
        normals = None
        if self.normals is not None:
            normals = UnitVectors(self.normals @ numpy.linalg.inv(linear)).normalized()
        triangles = self.triangles
        if numpy.linalg.det(linear) < 0.0:
            triangles = triangles[:, ::-1]
        return TriangleMesh(
            points=self.points @ linear.T + matrix[:SPACE_DIMENSIONS, SPACE_DIMENSIONS],
            triangles=triangles,
            normals=normals,
            texture_coordinates=self.texture_coordinates,
            faces=self.faces,
        )

    def single_precision(self) -> TriangleMesh:
        """
        :return: The mesh as a link keeps it: float32 positions, normals and texture
            coordinates, and uint32 indices.
        """
        return TriangleMesh(
            points=self.points.astype(numpy.float32),
            triangles=self.triangles.astype(numpy.uint32),
            normals=(
                None if self.normals is None else self.normals.astype(numpy.float32)
            ),
            texture_coordinates=(
                None
                if self.texture_coordinates is None
                else self.texture_coordinates.astype(numpy.float32)
            ),
        )

    def vertex_normals(self) -> numpy.ndarray:
        """
        :return: The mesh's normals, or area-weighted vertex normals computed from its
            triangles when it has none.
        """
        if self.normals is not None:
            return self.normals
        corners = self.points[self.triangles]
        face_normals = numpy.cross(
            corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]
        )
        normals = numpy.zeros_like(self.points, dtype=numpy.float64)
        for corner in range(TRIANGLE_CORNERS):
            numpy.add.at(normals, self.triangles[:, corner], face_normals)
        return UnitVectors(normals).normalized()


@dataclass(frozen=True, eq=False)
class UnitVectors:
    """
    Directions to scale to unit length.
    """

    vectors: numpy.ndarray
    """
    ``(N, 3)`` directions of any length.
    """

    def normalized(self) -> numpy.ndarray:
        """
        :return: The directions at unit length; zero vectors stay zero.
        """
        lengths = numpy.linalg.norm(self.vectors, axis=1, keepdims=True)
        return self.vectors / numpy.where(lengths > 0.0, lengths, 1.0)


# %% polygon meshes


@dataclass(eq=False)
class PolygonMesh:
    """
    A USD polygon mesh: points, faces as corner lists, and primvars.
    """

    points: numpy.ndarray
    """
    ``(N, 3)`` positions.
    """

    face_vertex_counts: numpy.ndarray
    """
    ``(F,)`` corners per face.
    """

    face_vertex_indices: numpy.ndarray
    """
    ``(K,)`` point index of every corner, face after face.
    """

    normals: Optional[PrimvarData] = None
    """
    The normals, if authored.
    """

    texture_coordinates: Optional[PrimvarData] = None
    """
    The texture coordinates, if authored.
    """

    left_handed: bool = False
    """
    Whether the faces wind clockwise seen from outside (``orientation`` leftHanded).
    """

    def triangulate(self) -> TriangleMesh:
        """
        :return: The faces as a fan of triangles each; per-point data stays shared,
            and points are split only where a primvar varies per face or corner.
        """
        counts = numpy.asarray(self.face_vertex_counts, dtype=numpy.int64)
        indices = numpy.asarray(self.face_vertex_indices, dtype=numpy.int64)
        face_of_corner = numpy.repeat(numpy.arange(len(counts)), counts)
        corners = self.fan_corners(counts)
        if self.left_handed:
            corners = corners[:, ::-1]
        normals = self.corner_values(self.normals, indices, face_of_corner)
        texture_coordinates = self.corner_values(
            self.texture_coordinates, indices, face_of_corner
        )
        faces = face_of_corner[corners[:, 0]]
        points = numpy.asarray(self.points, dtype=numpy.float64)
        if not self.splits_points(normals, texture_coordinates):
            return TriangleMesh(
                points=points,
                triangles=indices[corners].astype(numpy.uint32),
                normals=None if normals is None else self.normals.values[: len(points)],
                texture_coordinates=(
                    None
                    if texture_coordinates is None
                    else self.texture_coordinates.values[: len(points)]
                ),
                faces=faces,
            )
        return CornerVertices(points[indices], normals, texture_coordinates).welded(
            corners, faces
        )

    def splits_points(
        self,
        normals: Optional[numpy.ndarray],
        texture_coordinates: Optional[numpy.ndarray],
    ) -> bool:
        """
        :param normals: The normal of every corner, or None.
        :param texture_coordinates: The texture coordinates of every corner, or None.
        :return: Whether a present primvar varies per face or corner, so points need a
            vertex per corner.
        """
        return any(
            primvar is not None
            and values is not None
            and not primvar.interpolation.follows_points
            for primvar, values in (
                (self.normals, normals),
                (self.texture_coordinates, texture_coordinates),
            )
        )

    @staticmethod
    def fan_corners(counts: numpy.ndarray) -> numpy.ndarray:
        """
        :param counts: Corners per face; faces with fewer than three are dropped.
        :return: The corner indices of a fan triangulation, ``(first, k, k + 1)`` per
            face.
        """
        starts = numpy.concatenate([[0], numpy.cumsum(counts)[:-1]])
        per_face = numpy.where(
            counts >= TRIANGLE_CORNERS, counts - (TRIANGLE_CORNERS - 1), 0
        )
        face = numpy.repeat(numpy.arange(len(counts)), per_face)
        first_triangle = numpy.repeat(numpy.cumsum(per_face) - per_face, per_face)
        step = numpy.arange(int(per_face.sum())) - first_triangle + 1
        anchor = starts[face]
        return numpy.stack([anchor, anchor + step, anchor + step + 1], axis=1)

    @staticmethod
    def corner_values(
        primvar: Optional[PrimvarData],
        indices: numpy.ndarray,
        face_of_corner: numpy.ndarray,
    ) -> Optional[numpy.ndarray]:
        """
        :param primvar: The primvar, or None.
        :param indices: The point index of every corner.
        :param face_of_corner: The face index of every corner.
        :return: The primvar's value per corner, or None when it is absent or does not
            fit the mesh.
        """
        if primvar is None:
            return None
        return primvar.per_corner(indices, face_of_corner)


@dataclass(frozen=True, eq=False)
class CornerVertices:
    """
    One vertex per face corner: its position and the primvars that vary per corner.
    """

    positions: numpy.ndarray
    """
    The position of every corner.
    """

    normals: Optional[numpy.ndarray]
    """
    The normal of every corner, or None.
    """

    texture_coordinates: Optional[numpy.ndarray]
    """
    The texture coordinates of every corner, or None.
    """

    def welded(self, corners: numpy.ndarray, faces: numpy.ndarray) -> TriangleMesh:
        """
        :param corners: The corner indices of every triangle.
        :param faces: The source face of every triangle.
        :return: The triangles over the corners, with identical corners merged.
        """
        columns = [self.positions]
        columns += [] if self.normals is None else [self.normals]
        columns += (
            [] if self.texture_coordinates is None else [self.texture_coordinates]
        )
        rows = numpy.concatenate(columns, axis=1)
        unique, inverse = numpy.unique(rows, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        return TriangleMesh(
            points=unique[:, :SPACE_DIMENSIONS],
            triangles=inverse[corners].astype(numpy.uint32),
            normals=None if self.normals is None else unique[:, NORMAL_COLUMNS],
            texture_coordinates=(
                None
                if self.texture_coordinates is None
                else unique[:, -TEXTURE_DIMENSIONS:]
            ),
            faces=faces,
        )
