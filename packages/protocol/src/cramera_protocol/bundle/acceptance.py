"""
The measured outcome of a recorded task demo, ``acceptance_metrics.json``.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import Any, Dict

from cramera_protocol.document import JsonDocument, extension_field

# %% metrics


@dataclass(kw_only=True)
class AcceptanceMetrics(JsonDocument):
    """
    What a task demo measured in the world after its plan ran, by measurement name.

    The names are the demo's own, so the document declares no keys of its own.
    """

    measurements: Dict[str, Any] = extension_field()
    """
    Each measurement by its name, such as the distance between the robot's base and its
    target in metres.
    """
