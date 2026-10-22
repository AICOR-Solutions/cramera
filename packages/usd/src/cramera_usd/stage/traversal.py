"""
The prims a conversion visits, and which of them are visible render geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pxr import Sdf, Usd, UsdGeom
from typing_extensions import List

from cramera_protocol.bundle.conversion_report import ExcludedPrim, SkipReason
from cramera_usd.scene.log import ConversionLog
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.robots import PrimExclusion

# %% stage vocabulary


class Purpose(StrEnum):
    """
    The imageable purposes that are not rendered.
    """

    GUIDE = "guide"
    """
    Guide geometry such as collision proxies.
    """

    PROXY = "proxy"
    """
    Lightweight stand-ins for render geometry.
    """

    @property
    def skip_reason(self) -> SkipReason:
        """
        Why geometry of this purpose is left out.
        """
        return {
            Purpose.GUIDE: SkipReason.GUIDE_PURPOSE,
            Purpose.PROXY: SkipReason.PROXY_PURPOSE,
        }[self]


# %% traversal


@dataclass
class StageTraversal:
    """
    Visits the active prims under the selected roots, instance proxies included, and
    leaves out the subtrees the exclusion names.
    """

    frame: StageFrame
    """
    The stage frame.
    """

    roots: List[Usd.Prim]
    """
    The prims whose subtrees are converted.
    """

    exclusion: PrimExclusion
    """
    The prims left out with their subtrees.
    """

    log: ConversionLog
    """
    The log collecting the prims left out and the geometry skipped.
    """

    def prims(self) -> List[Usd.Prim]:
        """
        :return: Every converted prim, parents before children, root after root; each
            prim the exclusion leaves out is logged and its subtree not entered.
        """
        prims = []
        for root in self.roots:
            prims += self.subtree(root)
        return prims

    def subtree(self, root: Usd.Prim) -> List[Usd.Prim]:
        """
        :param root: A selected prim.
        :return: The converted prims of its subtree, parents before children.
        """
        prims = []
        iterator = iter(
            Usd.PrimRange(root, Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate))
        )
        for prim in iterator:
            if prim.IsPseudoRoot():
                continue
            reason = self.exclusion.reason_to_leave_out(prim, self.frame.time)
            if reason is not None:
                self.log.excluded.append(
                    ExcludedPrim(path=prim.GetPath().pathString, reason=reason)
                )
                iterator.PruneChildren()
                continue
            prims.append(prim)
        return prims

    def converts(self, path: Sdf.Path) -> bool:
        """
        :param path: The USD path of a prim.
        :return: Whether the prim lies in one of the selected subtrees.
        """
        return any(path.HasPrefix(root.GetPath()) for root in self.roots)

    def renderable(self, prim: Usd.Prim) -> bool:
        """
        :param prim: A prim.
        :return: Whether the prim is visible render geometry; guide, proxy and
            invisible geometry is logged as skipped.
        """
        if not prim.IsA(UsdGeom.Gprim):
            return False
        path = prim.GetPath().pathString
        imageable = UsdGeom.Imageable(prim)
        purposes = {member.value: member for member in Purpose}
        purpose = purposes.get(imageable.ComputePurpose())
        if purpose is not None:
            self.log.skip(purpose.skip_reason, path)
            return False
        if imageable.ComputeVisibility(self.frame.time) == UsdGeom.Tokens.invisible:
            self.log.skip(SkipReason.INVISIBLE, path)
            return False
        return True
