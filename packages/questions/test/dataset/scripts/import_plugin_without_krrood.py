"""
Imports the questions plugin with krrood hidden from the import system, as in a viewer
installation without the CRAM workspace, and prints the plugin's name.
"""

from __future__ import annotations

import importlib.abc
import sys
from types import ModuleType

from typing_extensions import Optional, Sequence

HIDDEN_PACKAGE = "krrood"
"""
The package this script pretends is not installed.
"""


class HiddenPackageFinder(importlib.abc.MetaPathFinder):
    """
    Refuses to find :data:`HIDDEN_PACKAGE` and its modules.
    """

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]],
        target: Optional[ModuleType] = None,
    ) -> None:
        """
        :param fullname: The module asked for.
        :param path: Where its parent package is.
        :param target: The module being reloaded, if any.
        :raises ModuleNotFoundError: For the hidden package and its modules.
        """
        if fullname.partition(".")[0] == HIDDEN_PACKAGE:
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


sys.meta_path.insert(0, HiddenPackageFinder())

from cramera_questions.plugin import QuestionsPlugin  # noqa: E402

print(QuestionsPlugin().name())
