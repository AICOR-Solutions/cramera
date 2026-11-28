"""
Where a converted stage is placed in its bundle: the stage point that becomes the
bundle's origin, and the part of the floor plan whose geometry is drawn.

A scan of a whole building lies wherever it was captured and holds far more than a robot
working at one table needs. Placing the table's work place at the bundle's origin lets a
robot stand at the origin as it does in every other bundle, and cropping the drawn
geometry to the room around it keeps the viewer and a simulator fast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy
from typing_extensions import List, Optional

from cramera_usd.geometry.meshes import TRIANGLE_CORNERS, TriangleMesh, UnitVectors
from cramera_usd.geometry.transforms import HOMOGENEOUS_SIZE, SPACE_DIMENSIONS

# %% origin


@dataclass(frozen=True)
class StageOrigin:
    """
    The point of a stage, in metres with Z up, and the heading about Z that become the
    bundle's origin and its x axis: a robot standing at the bundle's origin and facing
    its x axis stands at the point, facing the heading.
    """

    x: float
    """
    The point's x in the stage, in metres.
    """

    y: float
    """
    The point's y in the stage, in metres.
    """

    z: float
    """
    The point's height in the stage, in metres.
    """

    yaw: float
    """
    The heading about Z, in degrees, counter-clockwise from the stage's x axis.
    """

    def bundle_from_stage(self) -> numpy.ndarray:
        """
        :return: The 4x4 matrix taking stage coordinates in metres with Z up into the
            bundle's, acting on column vectors.
        """
        angle = math.radians(self.yaw)
        cosine, sine = math.cos(angle), math.sin(angle)
        rotation = numpy.array(
            [[cosine, sine, 0.0], [-sine, cosine, 0.0], [0.0, 0.0, 1.0]]
        )
        matrix = numpy.eye(HOMOGENEOUS_SIZE)
        matrix[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = rotation
        matrix[:SPACE_DIMENSIONS, SPACE_DIMENSIONS] = -rotation @ numpy.array(
            [self.x, self.y, self.z]
        )
        return matrix


# %% region


@dataclass(frozen=True)
class RegionEdge:
    """
    One edge of a floor region: the half of the floor plan on one side of a line of
    constant x or y.
    """

    axis: int
    """
    The axis the line is constant in: 0 for x, 1 for y.
    """

    limit: float
    """
    The line's coordinate.
    """

    keeps_below: bool
    """
    Whether the kept half lies below the limit rather than above it.
    """

    def distances(self, points: numpy.ndarray) -> numpy.ndarray:
        """
        :param points: ``(N, 3)`` positions in the bundle's frame.
        :return: How far each lies inside the kept half, negative outside.
        """
        offsets = points[:, self.axis] - self.limit
        return -offsets if self.keeps_below else offsets


@dataclass(frozen=True)
class ClippedCorner:
    """
    A corner of a triangle cut at a region's edges, as weights of the triangle's
    corners.
    """

    weights: numpy.ndarray
    """
    ``(3,)`` weights of the source triangle's corners, summing to one.
    """

    position: numpy.ndarray
    """
    ``(3,)`` the corner's position in the bundle's frame.
    """


@dataclass(frozen=True)
class FloorRegion:
    """
    A rectangle of the bundle's floor plan, in metres: only the geometry over it is
    drawn. A triangle wholly over it is kept, one crossing its edge is cut there, and
    collision geometry is kept whole.
    """

    minimum_x: float
    """
    The rectangle's smallest x.
    """

    minimum_y: float
    """
    The rectangle's smallest y.
    """

    maximum_x: float
    """
    The rectangle's largest x.
    """

    maximum_y: float
    """
    The rectangle's largest y.
    """

    def edges(self) -> List[RegionEdge]:
        """
        :return: The four edges of the rectangle.
        """
        return [
            RegionEdge(0, self.minimum_x, keeps_below=False),
            RegionEdge(0, self.maximum_x, keeps_below=True),
            RegionEdge(1, self.minimum_y, keeps_below=False),
            RegionEdge(1, self.maximum_y, keeps_below=True),
        ]

    def crop(
        self, mesh: TriangleMesh, to_bundle: numpy.ndarray
    ) -> Optional[TriangleMesh]:
        """
        :param mesh: A mesh in its own frame.
        :param to_bundle: The 4x4 matrix taking the mesh's frame into the bundle's.
        :return: The part of the mesh over the rectangle, in the mesh's own frame, its
            points, normals and texture coordinates interpolated where a triangle is
            cut; None when no part of it lies over the rectangle.
        """
        placed = mesh.transformed(to_bundle).points[mesh.triangles]
        inside = numpy.ones(len(mesh.triangles), dtype=bool)
        outside = numpy.zeros(len(mesh.triangles), dtype=bool)
        for edge in self.edges():
            distances = edge.distances(placed.reshape(-1, SPACE_DIMENSIONS)).reshape(
                -1, TRIANGLE_CORNERS
            )
            inside &= (distances >= 0.0).all(axis=1)
            outside |= (distances < 0.0).all(axis=1)
        kept = mesh.subset(inside) if inside.any() else None
        cut = self.cut(mesh, placed, numpy.flatnonzero(~inside & ~outside))
        if kept is None or cut is None:
            return kept if cut is None else cut
        return self.joined(kept, cut)

    def cut(
        self, mesh: TriangleMesh, placed: numpy.ndarray, crossing: numpy.ndarray
    ) -> Optional[TriangleMesh]:
        """
        :param mesh: A mesh in its own frame.
        :param placed: ``(M, 3, 3)`` its triangles' corners in the bundle's frame.
        :param crossing: The indices of the triangles crossing an edge.
        :return: The parts of those triangles over the rectangle, or None when no part
            lies over it.
        """
        corner_weights: List[numpy.ndarray] = []
        sources: List[int] = []
        for triangle in crossing:
            polygon = [
                ClippedCorner(
                    numpy.eye(TRIANGLE_CORNERS)[corner], placed[triangle][corner]
                )
                for corner in range(TRIANGLE_CORNERS)
            ]
            for edge in self.edges():
                polygon = self.clipped(polygon, edge)
            for fan in range(1, len(polygon) - 1):
                corner_weights.extend(
                    [polygon[0].weights, polygon[fan].weights, polygon[fan + 1].weights]
                )
                sources.append(int(triangle))
        if not sources:
            return None
        weights = numpy.array(corner_weights)
        corners = mesh.triangles[numpy.repeat(sources, TRIANGLE_CORNERS)]
        return TriangleMesh(
            points=self.interpolated(mesh.points, corners, weights),
            triangles=numpy.arange(len(weights), dtype=numpy.uint32).reshape(
                -1, TRIANGLE_CORNERS
            ),
            normals=(
                None
                if mesh.normals is None
                else UnitVectors(
                    self.interpolated(mesh.normals, corners, weights)
                ).normalized()
            ),
            texture_coordinates=(
                None
                if mesh.texture_coordinates is None
                else self.interpolated(mesh.texture_coordinates, corners, weights)
            ),
            faces=None if mesh.faces is None else mesh.faces[sources],
        )

    @staticmethod
    def clipped(polygon: List[ClippedCorner], edge: RegionEdge) -> List[ClippedCorner]:
        """
        :param polygon: A convex polygon's corners in order.
        :param edge: An edge of the region.
        :return: The part of the polygon on the kept side of the edge.
        """
        if not polygon:
            return polygon
        distances = edge.distances(numpy.array([corner.position for corner in polygon]))
        result: List[ClippedCorner] = []
        for index, corner in enumerate(polygon):
            following = (index + 1) % len(polygon)
            here, there = distances[index], distances[following]
            if here >= 0.0:
                result.append(corner)
            if (here >= 0.0) != (there >= 0.0):
                share = here / (here - there)
                other = polygon[following]
                result.append(
                    ClippedCorner(
                        corner.weights + share * (other.weights - corner.weights),
                        corner.position + share * (other.position - corner.position),
                    )
                )
        return result

    @staticmethod
    def interpolated(
        values: numpy.ndarray, corners: numpy.ndarray, weights: numpy.ndarray
    ) -> numpy.ndarray:
        """
        :param values: ``(N, K)`` a value per vertex.
        :param corners: ``(C, 3)`` the source triangle's vertices of each new corner.
        :param weights: ``(C, 3)`` the weights of those vertices.
        :return: ``(C, K)`` the value at each new corner.
        """
        return numpy.einsum("ci,cik->ck", weights, values[corners])

    @staticmethod
    def joined(first: TriangleMesh, second: TriangleMesh) -> TriangleMesh:
        """
        :param first: A mesh.
        :param second: A mesh with the same vertex attributes.
        :return: Both meshes as one.
        """
        return TriangleMesh(
            points=numpy.concatenate([first.points, second.points]),
            triangles=numpy.concatenate(
                [first.triangles, second.triangles + len(first.points)]
            ).astype(numpy.uint32),
            normals=FloorRegion.stacked(first.normals, second.normals),
            texture_coordinates=FloorRegion.stacked(
                first.texture_coordinates, second.texture_coordinates
            ),
            faces=FloorRegion.stacked(first.faces, second.faces),
        )

    @staticmethod
    def stacked(
        first: Optional[numpy.ndarray], second: Optional[numpy.ndarray]
    ) -> Optional[numpy.ndarray]:
        """
        :param first: An attribute of one mesh, or None.
        :param second: The same attribute of another, or None.
        :return: Both stacked, or None when either mesh lacks the attribute.
        """
        if first is None or second is None:
            return None
        return numpy.concatenate([first, second])
