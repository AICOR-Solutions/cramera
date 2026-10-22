"""
Reading the semantic attributes of prims.
"""

from __future__ import annotations

from dataclasses import dataclass

from pxr import Sdf, Usd
from typing_extensions import Any, Callable, Dict, List

from cramera_protocol.bundle.semantics import SemanticNamespace
from cramera_usd.scene.semantics import PrimAttributes
from cramera_usd.stage.frame import StageFrame
from cramera_usd.stage.values import StageValue

# %% reader


@dataclass
class SemanticsReader:
    """
    Reads the attributes of the namespaces a conversion carries over.
    """

    frame: StageFrame
    """
    The stage frame, for the read time.
    """

    def semantics(
        self, prims: List[Usd.Prim], link_name_of: Callable[[str], str]
    ) -> List[PrimAttributes]:
        """
        :param prims: The traversed prims.
        :param link_name_of: Names the link a prim path belongs to.
        :return: The attributes of every prim carrying any, in traversal order.
        """
        result = []
        for prim in prims:
            attributes = self.attributes_of(prim)
            if attributes:
                path = prim.GetPath().pathString
                result.append(PrimAttributes(path, attributes, link_name_of(path)))
        return result

    def attributes_of(self, prim: Usd.Prim) -> Dict[SemanticNamespace, Dict[str, Any]]:
        """
        :param prim: A prim.
        :return: The prim's attribute values as JSON by name without namespace, per
            namespace, in the order the stage lists them.
        """
        namespaces = {member.value: member for member in SemanticNamespace}
        attributes: Dict[SemanticNamespace, Dict[str, Any]] = {}
        for attribute in prim.GetAuthoredAttributes():
            namespace, *base_name = attribute.SplitName()
            if namespace not in namespaces or not base_name:
                continue
            value = StageValue(attribute.Get(self.frame.time)).json_value()
            attributes.setdefault(namespaces[namespace], {})[
                Sdf.Path.JoinIdentifier(base_name)
            ] = value
        return attributes
