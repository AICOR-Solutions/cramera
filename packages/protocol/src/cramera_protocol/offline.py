"""
The offline presentation: a storyboard of chapters over recorded scene bundles, and the
report of a check that a bundle holds every file it references.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.bundle.index import SceneName
from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.exceptions import ProtocolError
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion

# %% files and routes


class PresentationFile(StrEnum):
    """
    The files a presentation directory holds besides its bundles; a presentation
    directory is a scenes directory.
    """

    STORYBOARD = "storyboard.json"
    """
    The chapters of the presentation.
    """


class OfflineRoute(StrEnum):
    """
    The routes of the offline plugin, below ``/api/plugins/offline/``.
    """

    STORYBOARD = "storyboard"
    """
    The storyboard of the first scenes directory that holds one.
    """

    BUNDLE_CHECK = "bundle-check"
    """
    The completeness report of one bundle, named by :attr:`OfflineParameter.SCENE`.
    """


class OfflineParameter(StrEnum):
    """
    The query parameters of the offline plugin's routes.
    """

    SCENE = "scene"
    """
    The bundle a route is about.
    """


# %% errors


@dataclass
class EmptyStoryboard(ProtocolError):
    """
    A storyboard without chapters.
    """

    title: str
    """
    The storyboard's title.
    """

    def message(self) -> str:
        return f"The storyboard {self.title!r} has no chapters."


@dataclass
class InvalidChapterTiming(ProtocolError):
    """
    A chapter whose duration is not positive or whose first frame is negative.
    """

    title: str
    """
    The chapter's title.
    """

    duration_seconds: float
    """
    The chapter's duration.
    """

    frame: int
    """
    The chapter's first frame.
    """

    def message(self) -> str:
        return (
            f"The chapter {self.title!r} needs a positive duration and a frame of at "
            f"least 0, got {self.duration_seconds} seconds from frame {self.frame}."
        )


# %% storyboard


class ChapterKey(StrEnum):
    """
    The keys of one chapter of a storyboard.
    """

    TITLE = "title"
    """
    The chapter's heading.
    """

    NARRATION = "narration"
    """
    What the presenter says during the chapter.
    """

    SCENE = "scene"
    """
    The bundle the chapter shows.
    """

    PANEL = "panel"
    """
    The side panel the chapter opens.
    """

    FRAME = "frame"
    """
    The frame the chapter starts at.
    """

    PLAYBACK = "playback"
    """
    Whether the chapter plays the recording.
    """

    DURATION = "durationSeconds"
    """
    How long the chapter is shown at least, in seconds.
    """


@dataclass(kw_only=True)
class Chapter(JsonDocument):
    """
    One step of a presentation: a bundle, where to start in it, and what to say.
    """

    title: str = document_field(ChapterKey.TITLE)
    """
    The chapter's heading.
    """

    narration: str = document_field(ChapterKey.NARRATION, default="")
    """
    What the presenter says during the chapter.
    """

    scene: str = document_field(ChapterKey.SCENE)
    """
    The bundle the chapter shows.
    """

    panel: Optional[str] = document_field(ChapterKey.PANEL, default=None)
    """
    The identifier of the side panel the chapter opens, or None to keep the shown one.
    """

    frame: int = document_field(ChapterKey.FRAME, default=0)
    """
    The frame the chapter starts at.
    """

    playback: bool = document_field(ChapterKey.PLAYBACK, default=False)
    """
    Whether the chapter plays the recording from :attr:`frame`; an automatic tour waits
    for the recording's last frame before it moves on.
    """

    duration_seconds: float = document_field(ChapterKey.DURATION)
    """
    How long an automatic tour shows the chapter at least.
    """

    def __post_init__(self) -> None:
        SceneName(self.scene)
        if self.duration_seconds <= 0 or self.frame < 0:
            raise InvalidChapterTiming(self.title, self.duration_seconds, self.frame)


class StoryboardKey(StrEnum):
    """
    The keys of ``storyboard.json``.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The protocol version the storyboard was written with.
    """

    TITLE = "title"
    """
    The presentation's title.
    """

    DESCRIPTION = "description"
    """
    What the presentation shows.
    """

    CHAPTERS = "chapters"
    """
    The chapters, in the order they are presented.
    """


@dataclass(kw_only=True)
class Storyboard(JsonDocument):
    """
    The content of ``storyboard.json``: recorded scenes presented as chapters.
    """

    format_version: ProtocolVersion = document_field(
        StoryboardKey.FORMAT_VERSION, default=UNVERSIONED
    )
    """
    The protocol version the storyboard was written with.
    """

    title: str = document_field(StoryboardKey.TITLE)
    """
    The presentation's title.
    """

    description: str = document_field(StoryboardKey.DESCRIPTION, default="")
    """
    What the presentation shows.
    """

    chapters: List[Chapter] = document_field(StoryboardKey.CHAPTERS)
    """
    The chapters, in the order they are presented; at least one.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)
        if not self.chapters:
            raise EmptyStoryboard(self.title)

    def scene_names(self) -> List[str]:
        """
        :return: The bundles the chapters show, each once, in the order they are first
            shown.
        """
        return list(dict.fromkeys(chapter.scene for chapter in self.chapters))


# %% bundle check


class AssetProblemKind(StrEnum):
    """
    Why a file a bundle references cannot be shown from the bundle alone.
    """

    MISSING = "missing"
    """
    The referenced file does not exist in the bundle.
    """

    EXTERNAL = "external"
    """
    The reference names a web address, a package or an absolute path.
    """

    OUTSIDE_BUNDLE = "outsideBundle"
    """
    The reference, or a symbolic link on its way, leads out of the bundle.
    """

    DECLARED_MISSING = "declaredMissing"
    """
    The writer of the bundle listed the file as one it could not include.
    """

    UNREADABLE = "unreadable"
    """
    The file declaring references cannot be parsed.
    """

    INVALID_REFERENCE = "invalidReference"
    """
    A declaration that should name a file names none.
    """


class AssetProblemKey(StrEnum):
    """
    The keys of one problem of a bundle check.
    """

    KIND = "kind"
    """
    An :class:`AssetProblemKind` value.
    """

    SOURCE = "source"
    """
    The file declaring the reference, relative to the bundle.
    """

    REFERENCE = "reference"
    """
    The reference as the file declares it.
    """

    DETAIL = "detail"
    """
    Why a file could not be parsed.
    """


@dataclass(kw_only=True)
class AssetProblem(JsonDocument):
    """
    One reference of a bundle that cannot be followed inside the bundle.
    """

    kind: AssetProblemKind = document_field(AssetProblemKey.KIND)
    """
    Why the reference cannot be followed.
    """

    source: str = document_field(AssetProblemKey.SOURCE)
    """
    The file declaring the reference, relative to the bundle with ``/`` separators.
    """

    reference: str = document_field(AssetProblemKey.REFERENCE)
    """
    The reference as the file declares it.
    """

    detail: Optional[str] = document_field(AssetProblemKey.DETAIL, default=None)
    """
    Why the file could not be parsed, for :attr:`AssetProblemKind.UNREADABLE`.
    """


class BundleCheckKey(StrEnum):
    """
    The keys of a bundle check report.
    """

    BUNDLE = "bundle"
    """
    The checked bundle's name.
    """

    CHECKED_FILES = "checkedFiles"
    """
    Every file the check found and read.
    """

    PROBLEMS = "problems"
    """
    The references that cannot be followed.
    """


@dataclass(kw_only=True)
class BundleCheckReport(JsonDocument):
    """
    Whether a bundle holds every file its scene, models, meshes and materials reference.
    """

    bundle: str = document_field(BundleCheckKey.BUNDLE)
    """
    The checked bundle's name.
    """

    checked_files: List[str] = document_field(
        BundleCheckKey.CHECKED_FILES, default_factory=list
    )
    """
    Every file the check found, relative to the bundle, sorted.
    """

    problems: List[AssetProblem] = document_field(
        BundleCheckKey.PROBLEMS, default_factory=list
    )
    """
    The references that cannot be followed, in the order they were found.
    """

    def is_complete(self) -> bool:
        """
        :return: Whether every reference leads to a file inside the bundle.
        """
        return not self.problems
