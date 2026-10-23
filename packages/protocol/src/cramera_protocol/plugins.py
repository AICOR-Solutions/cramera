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

    MODELS = "models"
    """
    Answers probability, posterior and mode questions about a probabilistic circuit.
    """

    QUESTIONS = "questions"
    """
    The questions plugin: queries, plain-language questions and graph views.
    """

    WORKSHOP = "workshop"
    """
    Runs the woodworking workshop's contact simulation.
    """

