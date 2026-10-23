"""
Imports the questions plugin with krrood removed from the module search path, as in a
viewer installation without the CRAM workspace, and prints the plugin's name.
"""

from __future__ import annotations

import sys
from pathlib import Path

HIDDEN_PACKAGE = "krrood"
"""
The package this script pretends is not installed.
"""

sys.path[:] = [
    entry for entry in sys.path if not (Path(entry) / HIDDEN_PACKAGE).exists()
]

from cramera_questions.plugin import QuestionsPlugin  # noqa: E402

print(QuestionsPlugin().name())
