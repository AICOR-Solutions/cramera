"""
The names of the plugins whose routes and documents the protocol declares.
"""

from __future__ import annotations

from enum import StrEnum

# %% names


class PluginName(StrEnum):
    """
    The names of plugins with protocol documents; a plugin's name is also its route
    segment below :attr:`~cramera_protocol.viewer.ViewerRoute.PLUGIN_API`.
    """

    OFFLINE = "offline"
    """
    Presents recorded scenes as a storyboard and checks that bundles are complete.
    """
