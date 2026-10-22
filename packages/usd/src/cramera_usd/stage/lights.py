"""
Reading UsdLux lights and cameras.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy
from pxr import Usd, UsdGeom, UsdLux
from typing_extensions import List, Optional

from cramera_usd.scene.lights import WHITE, LightKind, StageCamera, StageLight
from cramera_usd.geometry.transforms import SPACE_DIMENSIONS
from cramera_usd.stage.frame import StageFrame

# %% constants

EXPOSURE_BASE = 2.0
"""
The factor one stop of exposure multiplies a light's intensity by.
"""

# %% lights


@dataclass
class LightReader:
    """
    Reads the visible UsdLux lights of the kinds the lighting description uses.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    def lights(self, prims: List[Usd.Prim]) -> List[StageLight]:
        """
        :param prims: The traversed prims.
        :return: Their visible lights, in traversal order.
        """
        lights = []
        for prim in prims:
            if not prim.HasAPI(UsdLux.LightAPI):
                continue
            visibility = UsdGeom.Imageable(prim).ComputeVisibility(self.frame.time)
            if visibility == UsdGeom.Tokens.invisible:
                continue
            light = self.read(prim)
            if light is not None:
                lights.append(light)
        return lights

    def read(self, prim: Usd.Prim) -> Optional[StageLight]:
        """
        :param prim: A light prim.
        :return: The light, or None for a light type the reader does not know.
        """
        known = {member.value: member for member in LightKind}
        kind = known.get(prim.GetTypeName())
        if kind is None:
            return None
        time = self.frame.time
        light = UsdLux.LightAPI(prim)
        matrix = self.frame.world_matrix(prim)
        scales = numpy.linalg.norm(matrix[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS], axis=0)
        intensity = float(light.GetIntensityAttr().Get(time) or 0.0)
        exposure = float(light.GetExposureAttr().Get(time) or 0.0)
        color = light.GetColorAttr().Get(time)
        read = StageLight(
            path=prim.GetPath().pathString,
            kind=kind,
            pose=self.frame.world_pose(prim),
            intensity=intensity * EXPOSURE_BASE**exposure,
            color=(
                tuple(float(component) for component in color)
                if color is not None
                else WHITE
            ),
            color_temperature=(
                float(light.GetColorTemperatureAttr().Get(time))
                if light.GetEnableColorTemperatureAttr().Get(time)
                else None
            ),
        )
        if kind is LightKind.RECTANGLE:
            rectangle = UsdLux.RectLight(prim)
            read.width = float(rectangle.GetWidthAttr().Get(time)) * scales[0]
            read.height = float(rectangle.GetHeightAttr().Get(time)) * scales[1]
        if kind.round:
            radius = self.radius_attribute(prim, kind).Get(time)
            read.radius = float(radius or 0.0) * float(scales.mean())
        if kind is LightKind.DISTANT:
            read.angle = float(UsdLux.DistantLight(prim).GetAngleAttr().Get(time))
        return read

    @staticmethod
    def radius_attribute(prim: Usd.Prim, kind: LightKind) -> Usd.Attribute:
        """
        :param prim: A light prim.
        :param kind: Its kind, a round one.
        :return: The attribute holding the light's radius.
        """
        if kind is LightKind.DISK:
            return UsdLux.DiskLight(prim).GetRadiusAttr()
        if kind is LightKind.SPHERE:
            return UsdLux.SphereLight(prim).GetRadiusAttr()
        return UsdLux.CylinderLight(prim).GetRadiusAttr()


# %% cameras


@dataclass
class CameraReader:
    """
    Reads the cameras authored on the stage.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    def cameras(self, prims: List[Usd.Prim]) -> List[StageCamera]:
        """
        :param prims: The traversed prims.
        :return: Their cameras with their vertical field of view, in traversal order.
        """
        return [self.read(prim) for prim in prims if prim.IsA(UsdGeom.Camera)]

    def read(self, prim: Usd.Prim) -> StageCamera:
        """
        :param prim: A camera prim.
        :return: The camera.
        """
        camera = UsdGeom.Camera(prim)
        focal_length = camera.GetFocalLengthAttr().Get(self.frame.time)
        aperture = camera.GetVerticalApertureAttr().Get(self.frame.time)
        return StageCamera(
            prim.GetPath().pathString,
            self.frame.world_pose(prim),
            float(numpy.degrees(2.0 * numpy.arctan(aperture / 2.0 / focal_length))),
        )
