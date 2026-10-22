"""
Reading a staged world's object catalog from its live routes.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from typing_extensions import Optional

from cramera_protocol.live_messages import ObjectCatalog


@dataclass(frozen=True)
class ObjectCatalogReader:
    """
    Reads a staged world's object catalog, or nothing while the world is not served.
    """

    url: str
    """
    The live route of the object catalog.
    """

    def read(self) -> Optional[ObjectCatalog]:
        """
        A world that is still being built does not answer yet, so this is where a
        refused connection becomes "not yet".

        :return: The catalog, or None while the world is not served.
        """
        try:
            with urllib.request.urlopen(self.url) as answer:
                return ObjectCatalog.from_json(json.loads(answer.read()))
        except OSError:
            return None
