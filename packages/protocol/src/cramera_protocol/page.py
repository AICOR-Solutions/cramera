"""
The query parameters of the viewer's page.
"""

from __future__ import annotations

from enum import StrEnum

# %% parameters


class PageParameter(StrEnum):
    """
    The query parameters the viewer's page reads from its address.
    """

    SCENE = "scene"
    """
    The bundle the page opens.
    """
