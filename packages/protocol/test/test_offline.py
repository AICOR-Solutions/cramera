"""
The offline presentation's storyboard and the bundle check report.
"""

from __future__ import annotations

import pytest

from cramera_protocol.bundle.index import InvalidSceneName
from cramera_protocol.exceptions import UnsupportedProtocolVersion
from cramera_protocol.offline import (
    AssetProblemKind,
    BundleCheckReport,
    Chapter,
    ChapterKey,
    EmptyStoryboard,
    InvalidChapterTiming,
    Storyboard,
    StoryboardKey,
)
from cramera_protocol.version import CURRENT_VERSION

# %% storyboard


def test_a_storyboard_reads_its_chapters(read_json):
    data = read_json("offline/storyboard.json")
    storyboard = Storyboard.from_json(data)
    assert storyboard.format_version == CURRENT_VERSION
    assert [chapter.title for chapter in storyboard.chapters] == [
        chapter[ChapterKey.TITLE] for chapter in data[StoryboardKey.CHAPTERS]
    ]
    second = data[StoryboardKey.CHAPTERS][1]
    assert storyboard.chapters[1].playback is second[ChapterKey.PLAYBACK]
    assert storyboard.chapters[1].frame == second[ChapterKey.FRAME]
    assert storyboard.chapters[1].duration_seconds == second[ChapterKey.DURATION]


def test_a_chapter_without_optional_keys_takes_the_defaults(read_json):
    chapter = Storyboard.from_json(read_json("offline/storyboard.json")).chapters[2]
    assert chapter == Chapter(
        title=chapter.title, scene=chapter.scene, duration_seconds=4
    )
    assert chapter.panel is None
    assert chapter.frame == 0
    assert chapter.playback is False


def test_a_storyboard_round_trips(read_json):
    storyboard = Storyboard.from_json(read_json("offline/storyboard.json"))
    assert Storyboard.from_json(storyboard.to_json()) == storyboard


def test_the_scene_names_are_listed_once_in_the_order_they_are_shown(read_json):
    data = read_json("offline/storyboard.json")
    chapters = data[StoryboardKey.CHAPTERS]
    assert Storyboard.from_json(data).scene_names() == [
        chapters[0][ChapterKey.SCENE],
        chapters[1][ChapterKey.SCENE],
    ]


@pytest.mark.parametrize(
    "document, error",
    [
        ("offline/storyboard_without_chapters.json", EmptyStoryboard),
        ("offline/storyboard_with_zero_duration.json", InvalidChapterTiming),
        ("offline/storyboard_with_negative_frame.json", InvalidChapterTiming),
        ("offline/storyboard_with_invalid_scene.json", InvalidSceneName),
        ("offline/storyboard_from_next_major_version.json", UnsupportedProtocolVersion),
    ],
)
def test_an_unusable_storyboard_is_refused(read_json, document, error):
    with pytest.raises(error):
        Storyboard.from_json(read_json(document))


# %% bundle check


def test_a_bundle_check_report_round_trips(read_json):
    data = read_json("offline/bundle_check_report.json")
    report = BundleCheckReport.from_json(data)
    assert [problem.kind for problem in report.problems] == [
        AssetProblemKind.MISSING,
        AssetProblemKind.UNREADABLE,
    ]
    assert report.to_json() == data


def test_a_report_without_problems_is_complete(read_json):
    report = BundleCheckReport.from_json(read_json("offline/bundle_check_report.json"))
    assert not report.is_complete()
    assert BundleCheckReport(bundle=report.bundle).is_complete()
