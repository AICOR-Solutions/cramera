"""
The closed cabinet below the bench's worktop: panels the authored environment shows but
gives no collision shapes, so robots and objects would pass through them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Tuple

CABINET_BODY = "laboratory_cabinet"
"""
The body holding the panels.
"""

SIDE_PANEL_POSITIONS = (-0.81, 0.81)
"""
Where the two outer side panels stand along x, in metres.
"""

PARTITION_POSITIONS = (-0.225, 0.24)
"""
Where the two inner partitions stand along x, in metres.
"""

# %% panels


class CabinetPart(StrEnum):
    """
    The authored Blender objects whose bounds the panels take.
    """

    SPLASHBACK = "Rear splashback"
    """
    The worktop's raised rear edge.
    """

    PLINTH = "Recessed plinth"
    """
    The recessed base.
    """

    SIDE = "Cabinet side"
    """
    An outer side panel.
    """

    REAR = "Cabinet rear"
    """
    The rear panel.
    """

    CROSS_MEMBER = "Upper cross member"
    """
    The reinforcement below the worktop.
    """

    PARTITION = "Cabinet partition"
    """
    A partition beside a bay.
    """

    SHELF = "Drawer lower shelf"
    """
    The shelf beneath the drawer.
    """

    LOWER_DOOR = "Lower left cabinet"
    """
    The closed door beneath the drawer bay.
    """

    DOOR = "Cabinet door"
    """
    The closed middle or right door.
    """


@dataclass(frozen=True)
class CabinetPanel:
    """
    One axis-aligned panel, with the extent the bench's Blender model gives it before
    its edges are rounded.
    """

    part: CabinetPart
    """
    The authored object.
    """

    center: Tuple[float, float, float]
    """
    The panel's centre in the laboratory's frame, in metres.
    """

    size: Tuple[float, float, float]
    """
    The panel's full extent along x, y and z, in metres.
    """


@dataclass(frozen=True)
class CabinetStructure:
    """
    The cabinet's closed panels; the drawer's bay stays open.

    Drawer guides, handles, feet and the room's decoration have no collision shapes.
    """

    name: str = CABINET_BODY
    """
    The body the panels belong to.
    """

    def panels(self) -> List[CabinetPanel]:
        """
        :return: Every panel.
        """
        panels = [
            CabinetPanel(
                CabinetPart.SPLASHBACK, (0, 0.352, 0.958), (1.78, 0.025, 0.116)
            ),
            CabinetPanel(CabinetPart.PLINTH, (0, 0.027, 0.083), (1.66, 0.59, 0.12)),
            CabinetPanel(CabinetPart.REAR, (0, 0.33, 0.47), (1.62, 0.023, 0.7)),
            CabinetPanel(
                CabinetPart.CROSS_MEMBER, (0, 0.02, 0.833), (1.62, 0.64, 0.05)
            ),
            CabinetPanel(
                CabinetPart.SHELF, (-0.52, 0.006, 0.597), (0.558, 0.616, 0.018)
            ),
            CabinetPanel(
                CabinetPart.LOWER_DOOR, (-0.52, -0.313, 0.352), (0.558, 0.023, 0.451)
            ),
            CabinetPanel(
                CabinetPart.DOOR, (0.005, -0.313, 0.469), (0.436, 0.024, 0.681)
            ),
            CabinetPanel(
                CabinetPart.DOOR, (0.523, -0.313, 0.469), (0.552, 0.024, 0.681)
            ),
        ]
        panels.extend(
            CabinetPanel(CabinetPart.SIDE, (x, 0.02, 0.468), (0.026, 0.654, 0.684))
            for x in SIDE_PANEL_POSITIONS
        )
        panels.extend(
            CabinetPanel(CabinetPart.PARTITION, (x, 0.015, 0.464), (0.021, 0.63, 0.675))
            for x in PARTITION_POSITIONS
        )
        return panels
