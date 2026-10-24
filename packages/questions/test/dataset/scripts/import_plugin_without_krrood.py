"""
Imports the questions plugin while krrood and cramera-bridge cannot be imported, as in a
viewer installation without the CRAM workspace, and prints the plugin's name.
"""

from __future__ import annotations

import sys
from importlib.abc import MetaPathFinder

HIDDEN_PACKAGES = frozenset({"krrood", "cramera_bridge"})
"""
The packages this script pretends are not installed.
"""


class HidingFinder(MetaPathFinder):
    """
    Refuses every module of the hidden packages.
    """

    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in HIDDEN_PACKAGES:
            raise ModuleNotFoundError(name)
        return None


sys.meta_path.insert(0, HidingFinder())

from cramera_questions.plugin import QuestionsPlugin  # noqa: E402

print(QuestionsPlugin().name())
