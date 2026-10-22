"""
Decoding JSON text whose damage must become an error the viewer answers with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing_extensions import Any

from cramera_models.exceptions import InvalidJson

# %% text


@dataclass(frozen=True)
class JsonText:
    """
    Text that should hold one JSON value.
    """

    text: str
    """
    The text.
    """

    source: str
    """
    Where the text came from, for the error.
    """

    def decode(self) -> Any:
        """
        The JSON reader raises its own error for damaged text; this is the one place
        where it becomes :class:`InvalidJson`. ``Infinity`` and ``NaN`` are accepted, as
        circuit files hold them.

        :return: The decoded value.
        :raises InvalidJson: When the text is not JSON.
        """
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as error:
            raise InvalidJson(self.source, str(error)) from error
