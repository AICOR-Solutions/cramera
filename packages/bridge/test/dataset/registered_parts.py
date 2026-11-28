"""
A package's own action outside coraplex's actions package, which the action discovery
offers only because the identifier registry declares it.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import List

from coraplex.robot_plans.actions.base import SequentialAction
from cramph.node import StatechartNode


@dataclass(eq=False, repr=False, kw_only=True)
class BowAction(SequentialAction):
    """
    Bow, as a package outside CRAM declares it.
    """

    depth: float = 0.3
    """
    How deep to bow, in metres.
    """

    def create_steps(self) -> List[StatechartNode]:
        return []
