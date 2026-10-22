"""
The semantic attributes authored on prims.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Any, Dict

from cramera_protocol.bundle.semantics import SemanticNamespace

# %% prims


@dataclass
class PrimAttributes:
    """
    The semantic attributes of one prim, grouped by attribute namespace.
    """

    path: str
    """
    The USD path of the prim.
    """

    attributes: Dict[SemanticNamespace, Dict[str, Any]]
    """
    The attribute values as JSON by name without its namespace, per namespace, in the
    order the stage lists the attributes.
    """

    link: str = ""
    """
    The name of the link the prim belongs to.
    """
