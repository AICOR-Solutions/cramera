"""
The events the parts of the browser application exchange.

Plugins subscribe to and emit the same events, so their names are part of the protocol.
"""

from __future__ import annotations

from enum import StrEnum

# %% events


class ViewerEvent(StrEnum):
    """
    The names of the browser application's events.
    """

    SCENE_LOADING = "scene:loading"
    """
    A bundle starts loading; the payload names it.
    """

    SCENE_LOADED = "scene:loaded"
    """
    A bundle finished loading; the payload is its scene description.
    """

    SCENE_FAILED = "scene:failed"
    """
    A bundle could not be loaded; the payload names the reason.
    """

    FRAME_CHANGED = "frame:changed"
    """
    The shown trajectory frame changed; the payload is the frame number.
    """

    PLAYBACK_CHANGED = "playback:changed"
    """
    Playback started, paused or changed speed.
    """

    ENTITY_SELECTED = "entity:selected"
    """
    A link, object or plan node was selected.
    """

    ENTITY_HIGHLIGHTED = "entity:highlighted"
    """
    Entities should be highlighted in the 3D view; the payload lists them.
    """

    QUESTION_ASKED = "question:asked"
    """
    A question or query was submitted.
    """

    QUESTION_ANSWERED = "question:answered"
    """
    An answer arrived.
    """

    LIVE_CONNECTED = "live:connected"
    """
    A live publisher answered; the payload is its information.
    """

    LIVE_DISCONNECTED = "live:disconnected"
    """
    The live publisher stopped answering.
    """

    LIVE_STATE = "live:state"
    """
    A new live state arrived.
    """

    LAYOUT_CHANGED = "layout:changed"
    """
    Panels were shown, hidden or resized.
    """
