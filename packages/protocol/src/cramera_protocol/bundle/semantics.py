"""
The semantics of a converted stage, ``semantics.json``: the semantic attributes of every
prim that carries any, with the link that holds the prim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% units


class LengthUnit(StrEnum):
    """
    The length unit a converted bundle is written in.
    """

    METRES = "metres"
    """
    Lengths are in metres.
    """


class UpAxis(StrEnum):
    """
    The axis that points up in a converted bundle.
    """

    Z = "Z"
    """
    Z points up.
    """


# %% prims


class SemanticNamespace(StrEnum):
    """
    The attribute namespaces a converted stage carries over; a prim's attributes are
    grouped under them.
    """

    ONTOLOGY = "ont"
    """
    Ontology types and IRIs.
    """

    SEMANTIC_DIGITAL_TWIN = "sdt"
    """
    The twin's own semantic attributes.
    """


class PrimSemanticsKey(StrEnum):
    """
    The keys of one prim in ``semantics.json`` besides its attribute namespaces.
    """

    MODEL = "model"
    """
    The model or object holding the prim's link.
    """

    LINK = "link"
    """
    The link the prim belongs to.
    """


@dataclass(kw_only=True)
class PrimSemantics(JsonDocument):
    """
    The semantic attributes of one prim, grouped by namespace, and where the prim ended
    up in the bundle.
    """

    model: Optional[str] = document_field(PrimSemanticsKey.MODEL, default=None)
    """
    The model or object holding the prim's link, when the bundle has several models.
    """

    link: str = document_field(PrimSemanticsKey.LINK)
    """
    The name of the link the prim belongs to.
    """

    ontology: Optional[Dict[str, Any]] = document_field(
        SemanticNamespace.ONTOLOGY, default=None
    )
    """
    The prim's ontology attributes by name without their namespace, if it has any.
    """

    semantic_digital_twin: Optional[Dict[str, Any]] = document_field(
        SemanticNamespace.SEMANTIC_DIGITAL_TWIN, default=None
    )
    """
    The prim's twin attributes by name without their namespace, if it has any.
    """


# %% document


class SemanticsKey(StrEnum):
    """
    The keys of ``semantics.json``.
    """

    UNITS = "units"
    """
    The length unit.
    """

    UP_AXIS = "upAxis"
    """
    The axis that points up.
    """

    SOURCE = "source"
    """
    The converted stage.
    """

    PRIMS = "prims"
    """
    The prims carrying semantic attributes.
    """


@dataclass(kw_only=True)
class Semantics(JsonDocument):
    """
    The content of ``semantics.json``.
    """

    units: LengthUnit = document_field(SemanticsKey.UNITS, default=LengthUnit.METRES)
    """
    The length unit of the bundle.
    """

    up_axis: UpAxis = document_field(SemanticsKey.UP_AXIS, default=UpAxis.Z)
    """
    The axis that points up in the bundle.
    """

    source: str = document_field(SemanticsKey.SOURCE)
    """
    The path of the converted stage.
    """

    prims: Dict[str, PrimSemantics] = document_field(
        SemanticsKey.PRIMS, default_factory=dict
    )
    """
    The prims carrying semantic attributes, by USD path.
    """
