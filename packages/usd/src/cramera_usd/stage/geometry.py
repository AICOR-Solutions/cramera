"""
Reading renderable geometry prims as triangle meshes in their local frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy
from pxr import Sdf, Usd, UsdGeom, UsdShade
from typing_extensions import List, Optional

from cramera_usd.geometry.meshes import (
    Interpolation,
    PolygonMesh,
    PrimvarData,
    TriangleMesh,
)
from cramera_usd.geometry.axes import Axis
from cramera_usd.geometry.shapes import ShapeTessellation
from cramera_usd.geometry.transforms import SPACE_DIMENSIONS
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.materials import MaterialReader

# %% stage vocabulary


class GeometryPrimvar(StrEnum):
    """
    The geometry primvars the reader looks up by name.
    """

    TEXTURE_COORDINATES = "st"
    """
    The conventional texture coordinate set.
    """

    NORMALS = "normals"
    """
    Normals authored as a primvar, which take precedence over the normals attribute.
    """


# %% pieces


@dataclass(eq=False)
class MaterialPiece:
    """
    The triangles of a geometry prim that one material shades.
    """

    mesh: TriangleMesh
    """
    The triangles in the prim's local frame.
    """

    material: str
    """
    The name of the material.
    """


# %% reader


@dataclass
class GeometryReader:
    """
    Reads a renderable geometry prim as triangle meshes in its local frame, one per
    bound material (material subsets split a mesh).
    """

    frame: StageFrame
    """
    The stage frame, for the read time.
    """

    materials: MaterialReader
    """
    The material reader.
    """

    tessellation: ShapeTessellation = field(default_factory=ShapeTessellation)
    """
    The resolution of implicit shapes.
    """

    def pieces(self, prim: Usd.Prim) -> Optional[List[MaterialPiece]]:
        """
        :param prim: A geometry prim.
        :return: Its triangles per bound material, or None for a geometry type the
            reader cannot tessellate.
        """
        mesh = self.triangle_mesh(prim)
        if mesh is None:
            return None
        material = self.materials.material_of(prim)
        if not prim.IsA(UsdGeom.Mesh) or mesh.faces is None:
            return [MaterialPiece(mesh, material)]
        pieces = []
        remaining = numpy.ones(len(mesh.triangles), dtype=bool)
        for subset in UsdShade.MaterialBindingAPI(prim).GetMaterialBindSubsets():
            faces = numpy.asarray(subset.GetIndicesAttr().Get(self.frame.time) or [])
            selected = numpy.isin(mesh.faces, faces) & remaining
            if selected.any():
                pieces.append(
                    MaterialPiece(
                        mesh.subset(selected),
                        self.materials.material_of(subset.GetPrim()),
                    )
                )
            remaining &= ~selected
        if remaining.all():
            return [MaterialPiece(mesh, material)]
        if remaining.any():
            pieces.append(MaterialPiece(mesh.subset(remaining), material))
        return pieces

    def triangle_mesh(self, prim: Usd.Prim) -> Optional[TriangleMesh]:
        """
        :param prim: A geometry prim.
        :return: The prim's triangles, or None for an unsupported geometry type.
        """
        time = self.frame.time
        if prim.IsA(UsdGeom.Mesh):
            return self.polygon_mesh(UsdGeom.Mesh(prim)).triangulate()
        if prim.IsA(UsdGeom.Cube):
            return self.tessellation.box(UsdGeom.Cube(prim).GetSizeAttr().Get(time))
        if prim.IsA(UsdGeom.Sphere):
            return self.tessellation.sphere(
                UsdGeom.Sphere(prim).GetRadiusAttr().Get(time)
            )
        if prim.IsA(UsdGeom.Cylinder):
            shape = UsdGeom.Cylinder(prim)
            return self.tessellation.cylinder(
                shape.GetRadiusAttr().Get(time),
                shape.GetHeightAttr().Get(time),
                Axis(shape.GetAxisAttr().Get(time)),
            )
        if prim.IsA(UsdGeom.Cone):
            shape = UsdGeom.Cone(prim)
            return self.tessellation.cone(
                shape.GetRadiusAttr().Get(time),
                shape.GetHeightAttr().Get(time),
                Axis(shape.GetAxisAttr().Get(time)),
            )
        if prim.IsA(UsdGeom.Capsule):
            shape = UsdGeom.Capsule(prim)
            return self.tessellation.capsule(
                shape.GetRadiusAttr().Get(time),
                shape.GetHeightAttr().Get(time),
                Axis(shape.GetAxisAttr().Get(time)),
            )
        return None

    def polygon_mesh(self, mesh: UsdGeom.Mesh) -> PolygonMesh:
        """
        :param mesh: A mesh prim.
        :return: Its polygons and primvars.
        """
        time = self.frame.time
        return PolygonMesh(
            points=numpy.asarray(
                mesh.GetPointsAttr().Get(time) or [], dtype=numpy.float64
            ).reshape(-1, SPACE_DIMENSIONS),
            face_vertex_counts=numpy.asarray(
                mesh.GetFaceVertexCountsAttr().Get(time) or [], dtype=numpy.int64
            ),
            face_vertex_indices=numpy.asarray(
                mesh.GetFaceVertexIndicesAttr().Get(time) or [], dtype=numpy.int64
            ),
            normals=self.normals_of(mesh),
            texture_coordinates=self.texture_coordinates_of(mesh),
            left_handed=mesh.GetOrientationAttr().Get(time)
            == UsdGeom.Tokens.leftHanded,
        )

    def normals_of(self, mesh: UsdGeom.Mesh) -> Optional[PrimvarData]:
        """
        :param mesh: A mesh prim.
        :return: The normals primvar, else the normals attribute, else None.
        """
        primvar = UsdGeom.PrimvarsAPI(mesh.GetPrim()).GetPrimvar(
            GeometryPrimvar.NORMALS
        )
        if primvar and primvar.HasValue():
            return self.primvar_data(primvar)
        if mesh.GetNormalsAttr().HasValue():
            return PrimvarData(
                numpy.asarray(
                    mesh.GetNormalsAttr().Get(self.frame.time), dtype=numpy.float64
                ),
                Interpolation(mesh.GetNormalsInterpolation()),
            )
        return None

    def texture_coordinates_of(self, mesh: UsdGeom.Mesh) -> Optional[PrimvarData]:
        """
        :param mesh: A mesh prim.
        :return: The ``st`` primvar, else the first primvar with texture coordinates,
            else None.
        """
        primvars = UsdGeom.PrimvarsAPI(mesh.GetPrim())
        coordinates = primvars.GetPrimvar(GeometryPrimvar.TEXTURE_COORDINATES)
        if coordinates and coordinates.HasValue():
            return self.primvar_data(coordinates)
        found = next(
            (
                primvar
                for primvar in primvars.GetPrimvarsWithValues()
                if primvar.GetTypeName().role == Sdf.ValueRoleNames.TextureCoordinate
            ),
            None,
        )
        return None if found is None else self.primvar_data(found)

    def primvar_data(self, primvar: UsdGeom.Primvar) -> PrimvarData:
        """
        :param primvar: A primvar.
        :return: Its flattened values and interpolation.
        """
        return PrimvarData(
            numpy.asarray(
                primvar.ComputeFlattened(self.frame.time), dtype=numpy.float64
            ),
            Interpolation(primvar.GetInterpolation()),
        )
