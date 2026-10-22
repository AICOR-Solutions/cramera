"""
The partition of a stage's prims into links.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pxr import Kind, Sdf, Usd
from typing_extensions import List, Set

# %% constants

TOP_LEVEL_DEPTH = 2
"""
The number of path elements below which a prim can be an asset of its own: prims
directly under the root are scopes, not assets.
"""

# %% partition


@dataclass
class LinkPartition:
    """
    Decides which prim each piece of geometry belongs to: the nearest rigid body, joint
    body or referenced asset above it, else the outermost prim whose subtree holds no
    other link.
    """

    root_path: str
    """
    The prim standing for the world (the default prim).
    """

    bodies: Set[str]
    """
    Rigid bodies and joint bodies; each is a link.
    """

    assets: Set[str]
    """
    Outermost referenced or component-kind prims; each holding geometry is a link.
    """

    occupied: Set[str] = field(default_factory=set)
    """
    The strict ancestors of every body and asset.
    """

    def __post_init__(self) -> None:
        """
        Collect the strict ancestors of every body and asset.
        """
        for path in self.bodies | self.assets:
            parent = Sdf.Path(path).GetParentPath()
            while not parent.IsAbsoluteRootPath() and not parent.isEmpty:
                self.occupied.add(parent.pathString)
                parent = parent.GetParentPath()

    @staticmethod
    def asset_roots(prims: List[Usd.Prim], root_path: str) -> Set[str]:
        """
        :param prims: The traversed prims, parents before children.
        :param root_path: The default prim's path.
        :return: The outermost prims below the default prim that reference or load
            another layer, or are component models.
        """
        assets: Set[str] = set()
        for prim in prims:
            path = prim.GetPath()
            if path.pathElementCount < TOP_LEVEL_DEPTH or path.pathString == root_path:
                continue
            if not (
                prim.HasAuthoredReferences()
                or prim.HasAuthoredPayloads()
                or Usd.ModelAPI(prim).IsKind(
                    Kind.Tokens.component, Usd.ModelAPI.KindValidationNone
                )
            ):
                continue
            if any(prefix.pathString in assets for prefix in path.GetPrefixes()[:-1]):
                continue
            assets.add(path.pathString)
        return assets

    def link_path_of(self, path: str) -> str:
        """
        :param path: A prim path.
        :return: The path of the prim whose link holds the prim.
        """
        current = Sdf.Path(path)
        while not current.IsAbsoluteRootPath():
            if current.pathString in self.bodies or current.pathString in self.assets:
                return current.pathString
            current = current.GetParentPath()
        root = Sdf.Path(self.root_path)
        for prefix in Sdf.Path(path).GetPrefixes():
            if not root.HasPrefix(prefix) and prefix.pathString not in self.occupied:
                return prefix.pathString
        return self.root_path

    def body_above(self, path: str) -> bool:
        """
        :param path: A prim path.
        :return: Whether a body lies between the prim and the world.
        """
        return any(
            prefix.pathString in self.bodies
            for prefix in Sdf.Path(path).GetPrefixes()[:-1]
        )

    def nearest_asset_above(self, path: str, fallback: str) -> str:
        """
        :param path: A prim path.
        :param fallback: The path to answer when no asset lies above the prim.
        :return: The nearest asset strictly above the prim, else the fallback.
        """
        prefixes = [prefix.pathString for prefix in Sdf.Path(path).GetPrefixes()[:-1]]
        return next(
            (prefix for prefix in reversed(prefixes) if prefix in self.assets),
            fallback,
        )
