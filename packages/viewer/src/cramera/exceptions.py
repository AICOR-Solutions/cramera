"""
Errors the viewer raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

from cramera_protocol.exceptions import ProtocolError

# %% files


@dataclass
class ViewerError(ProtocolError):
    """
    A request or configuration the viewer cannot serve.
    """

    def status(self) -> HTTPStatus:
        """
        :return: The HTTP status a request that raised this error is answered with.
        """
        return HTTPStatus.BAD_REQUEST


@dataclass
class PathOutsideDirectory(ViewerError):
    """
    A requested path that leads out of the directory it must stay in.
    """

    directory: Path
    """
    The directory the path must stay in.
    """

    requested: str
    """
    The path that was requested, relative to the directory.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.FORBIDDEN

    def message(self) -> str:
        return f"{self.requested!r} leads out of the directory it is looked up in."


@dataclass
class FileNotInDirectory(ViewerError):
    """
    A requested file that does not exist in the directory it was looked for in.
    """

    directory: Path
    """
    The directory the file was looked for in.
    """

    requested: str
    """
    The path that was requested, relative to the directory.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"{self.requested!r} is not a file."


@dataclass
class UnknownScene(ViewerError):
    """
    A bundle name no scenes directory holds.
    """

    name: str
    """
    The bundle name that was requested.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return f"No scenes directory holds a bundle named {self.name!r}."


# %% plugins


@dataclass
class DuplicatePlugin(ViewerError):
    """
    Two installed plugins with the same name.
    """

    name: str
    """
    The name both plugins use.
    """

    def message(self) -> str:
        return f"Two installed plugins are named {self.name!r}."


@dataclass
class InvalidPluginName(ViewerError):
    """
    A plugin name that cannot be used as a route segment.
    """

    name: str
    """
    The name the plugin gave.
    """

    def message(self) -> str:
        return (
            f"{self.name!r} is not a plugin name: use lowercase letters, digits "
            f"and '-'."
        )
