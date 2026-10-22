"""
The installed distributions the converter names: its own, and the viewer it can use.
"""

from __future__ import annotations

from enum import StrEnum
from importlib import metadata, util

# %% distributions


class Distribution(StrEnum):
    """
    The distributions the converter names, with the package each installs.
    """

    CONVERTER = "cramera-usd"
    """
    This converter.
    """

    VIEWER = "cramera"
    """
    The viewer, which takes screenshots of bundles.
    """

    def version(self) -> str:
        """
        :return: The installed version of the distribution.
        """
        return metadata.version(self.value)

    def importable(self, module: str) -> bool:
        """
        :param module: A module the distribution installs.
        :return: Whether the module can be imported.
        """
        return util.find_spec(module) is not None
