"""
The key other devices of the network carry to watch the viewer.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Self

from cramera.locations import DataLocations

KEY_FILE = "network_key"
"""
The file in cramera's data directory that keeps the key.
"""

KEY_BYTES = 12
"""
The random bytes of a new key.
"""

OWNER_ONLY = 0o600
"""
The permissions of the key's file: readable and writable by its owner only.
"""

# %% key


@dataclass(frozen=True)
class NetworkKey:
    """
    The key in its file, kept from one viewer to the next, so an address a phone keeps
    still opens the viewer after a restart.
    """

    path: Path
    """
    The file that keeps the key.
    """

    @classmethod
    def of(cls, locations: DataLocations) -> Self:
        """
        :param locations: Where cramera keeps its data.
        :return: The key of that data directory.
        """
        return cls(locations.data / KEY_FILE)

    def value(self) -> str:
        """
        :return: The key; a new one when the file holds none, written readable by its
            owner only.
        """
        key = self.path.read_text().strip() if self.path.is_file() else ""
        if key:
            return key
        key = secrets.token_urlsafe(KEY_BYTES)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=OWNER_ONLY)
        self.path.chmod(OWNER_ONLY)
        self.path.write_text(key)
        return key
