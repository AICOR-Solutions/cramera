"""
Errors the offline plugin raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

from typing_extensions import List

from cramera.exceptions import ViewerError
from cramera_protocol.offline import BundleCheckReport

# %% files


@dataclass
class UnreadableFile(ViewerError):
    """
    A file that exists but cannot be parsed in its format.
    """

    path: Path
    """
    The file.
    """

    reason: str
    """
    What the parser reported.
    """

    def message(self) -> str:
        return f"{self.path} cannot be read: {self.reason}"


@dataclass
class InvalidReference(ViewerError):
    """
    A declaration in an asset file that should name a file but names none.
    """

    path: Path
    """
    The file holding the declaration.
    """

    declaration: str
    """
    The declaration as the file holds it.
    """

    def message(self) -> str:
        return f"{self.path} declares {self.declaration!r}, which names no file."


# %% presentation


@dataclass
class StoryboardNotFound(ViewerError):
    """
    No scenes directory holds a storyboard.
    """

    directories: List[Path]
    """
    The scenes directories that were searched.
    """

    def status(self) -> HTTPStatus:
        return HTTPStatus.NOT_FOUND

    def message(self) -> str:
        return (
            f"None of the scenes directories {[str(path) for path in self.directories]} "
            f"holds a storyboard."
        )


@dataclass
class MissingQueryParameter(ViewerError):
    """
    A request without a query parameter its route needs.
    """

    parameter: str
    """
    The missing parameter.
    """

    def message(self) -> str:
        return f"The request needs the query parameter {self.parameter!r}."


@dataclass
class PresentationExists(ViewerError):
    """
    A presentation directory that would overwrite files.
    """

    destination: Path
    """
    The directory that exists and is not empty.
    """

    def message(self) -> str:
        return (
            f"{self.destination} exists and is not empty; choose a new directory for "
            f"the presentation."
        )


@dataclass
class IncompleteBundles(ViewerError):
    """
    Bundles a presentation needs that do not hold every file they reference.
    """

    reports: List[BundleCheckReport] = field(default_factory=list)
    """
    The reports of the incomplete bundles.
    """

    def message(self) -> str:
        names = [report.bundle for report in self.reports]
        return f"The bundles {names} do not hold every file they reference."


# %% network


@dataclass
class NetworkIsolationUnavailable(ViewerError):
    """
    A system on which the current user cannot create a network namespace.
    """

    reason: str
    """
    What ``unshare`` reported.
    """

    def message(self) -> str:
        return (
            f"The viewer cannot be started without network routes: {self.reason.strip()} "
            f"Unprivileged user namespaces may be disabled, for example by "
            f"kernel.apparmor_restrict_unprivileged_userns; serve without --isolated."
        )
