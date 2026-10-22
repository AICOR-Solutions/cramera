"""
Everything the bundle writers need from a converted stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from typing_extensions import Dict, List, Optional

from cramera_usd.geometry.bounds import PointBounds
from cramera_usd.scene.kinematics import Joint, Link
from cramera_usd.scene.lights import StageCamera, StageLight
from cramera_usd.scene.log import ConversionLog
from cramera_usd.scene.materials import AuthoredMaterial
from cramera_usd.scene.semantics import PrimAttributes

# %% stage


@dataclass(eq=False)
class ConvertedStage:
    """
    The neutral description of the converted part of a stage.
    """

    source: Path
    """
    The stage file that was converted.
    """

    root_link: str
    """
    The name of the link every other link hangs from, standing for the world.
    """

    links: List[Link] = field(default_factory=list)
    """
    Every link, parents before children.
    """

    joints: List[Joint] = field(default_factory=list)
    """
    One joint per link except the root, in the order of their child links.
    """

    materials: Dict[str, AuthoredMaterial] = field(default_factory=dict)
    """
    The materials meshes refer to, by name.
    """

    lights: List[StageLight] = field(default_factory=list)
    """
    The visible lights of the selected prims.
    """

    semantics: List[PrimAttributes] = field(default_factory=list)
    """
    The prims carrying semantic attributes.
    """

    cameras: List[StageCamera] = field(default_factory=list)
    """
    The cameras of the selected prims, in traversal order.
    """

    bounds: Optional[PointBounds] = None
    """
    The box holding all visual geometry, or None for a scene without any.
    """

    central_bounds: Optional[PointBounds] = None
    """
    The box holding the dense core of the visual geometry, or None without any.
    """

    used_files: List[Path] = field(default_factory=list)
    """
    The layers and textures the conversion read, for change detection.
    """

    log: ConversionLog = field(default_factory=ConversionLog)
    """
    What the conversion read, skipped and left out.
    """

    @property
    def movable_joints(self) -> List[Joint]:
        """
        The joints whose value can change, in tree order.
        """
        return [joint for joint in self.joints if joint.movable]
