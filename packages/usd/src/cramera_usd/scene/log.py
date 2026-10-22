"""
What a conversion read, skipped and left out, collected while it runs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from typing_extensions import Dict, List

from cramera_protocol.bundle.conversion_report import (
    DetachedBody,
    EnvironmentArticulation,
    ExcludedPrim,
    SkipReason,
)

# %% log


@dataclass
class ConversionLog:
    """
    What the conversion read, skipped and left out.
    """

    counts: Counter = field(default_factory=Counter)
    """
    Named counts of what was read and written, by :class:`ReportCount` key.
    """

    skipped: Counter = field(default_factory=Counter)
    """
    The number of prims left out, by :class:`SkipReason`.
    """

    skipped_examples: Dict[str, List[str]] = field(default_factory=dict)
    """
    A few prim paths per skip reason.
    """

    excluded: List[ExcludedPrim] = field(default_factory=list)
    """
    The prims left out with their subtrees, in traversal order.
    """

    detached: List[DetachedBody] = field(default_factory=list)
    """
    The converted bodies whose joint to a left-out parent body was dropped, in joint
    path order.
    """

    articulations: List[EnvironmentArticulation] = field(default_factory=list)
    """
    The articulations with movable joints converted outside every marked robot, in
    traversal order.
    """

    missing_textures: List[str] = field(default_factory=list)
    """
    Texture asset paths that did not resolve to a file, in the order they were read.
    """

    warnings: List[str] = field(default_factory=list)
    """
    Everything else worth a look.
    """

    example_limit: int = 5
    """
    How many example paths are kept per skip reason.
    """

    def skip(self, reason: SkipReason, path: str) -> None:
        """
        Record that a prim was left out.

        :param reason: Why it was left out.
        :param path: The prim's USD path.
        """
        self.skipped[reason.value] += 1
        examples = self.skipped_examples.setdefault(reason.value, [])
        if len(examples) < self.example_limit:
            examples.append(path)

    def miss_texture(self, asset_path: str) -> None:
        """
        Record a texture whose asset path does not resolve to a file, once.

        :param asset_path: The authored asset path.
        """
        if asset_path not in self.missing_textures:
            self.missing_textures.append(asset_path)
