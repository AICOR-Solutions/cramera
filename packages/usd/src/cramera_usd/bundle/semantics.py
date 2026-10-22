"""
The semantics of a converted stage, as ``semantics.json`` holds them.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Optional

from cramera_protocol.bundle.semantics import (
    PrimSemantics,
    SemanticNamespace,
    Semantics,
)
from cramera_usd.animation.animation import SceneAnimation
from cramera_usd.scene.semantics import PrimAttributes
from cramera_usd.scene.stage import ConvertedStage

# %% semantics


@dataclass(frozen=True)
class SemanticsSummary:
    """
    Every prim's semantic attributes with the link, and for a playback the model,
    holding it.
    """

    stage: ConvertedStage
    """
    The converted stage.
    """

    animation: Optional[SceneAnimation]
    """
    The playback that may have moved links into other models, or None.
    """

    def to_protocol(self) -> Semantics:
        """
        :return: The content of ``semantics.json``.
        """
        return Semantics(
            source=str(self.stage.source),
            prims={item.path: self.prim(item) for item in self.stage.semantics},
        )

    def prim(self, item: PrimAttributes) -> PrimSemantics:
        """
        :param item: A prim's attributes.
        :return: Its entry, placed in the model holding its link.
        """
        model = None
        link = item.link
        if self.animation is not None:
            placement = self.animation.placement_of(item.link)
            model, link = placement.model, placement.link
        return PrimSemantics(
            model=model,
            link=link,
            ontology=item.attributes.get(SemanticNamespace.ONTOLOGY),
            semantic_digital_twin=item.attributes.get(
                SemanticNamespace.SEMANTIC_DIGITAL_TWIN
            ),
        )
