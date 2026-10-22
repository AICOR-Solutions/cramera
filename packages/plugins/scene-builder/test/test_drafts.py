"""
Checking drafts against the limits and the library, and keeping them.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from cramera.exceptions import FileNotInDirectory
from cramera_protocol.scene_builder import (
    DraftKey,
    DraftRecord,
    InstanceKey,
    SceneDraft,
)
from cramera_scene_builder.drafts import (
    Axis,
    DraftCheck,
    DraftFile,
    DraftResources,
    DraftStore,
)
from cramera_scene_builder.exceptions import (
    DraftTooLarge,
    DuplicateInstance,
    InvalidDraftIdentifier,
    InvalidDraftText,
    InvalidResourceIdentifier,
    NonPositiveScale,
    NotAModel,
    NotAPointCloud,
    TooManyEntries,
    UnknownDraft,
    UnknownResourceRoot,
    UnreadableDraft,
    UnsafeStoragePath,
    ValueOutOfRange,
)
from cramera_scene_builder.resources import ResourceIdentifier


@pytest.fixture
def record(read_json) -> DraftRecord:
    return DraftRecord.from_json(read_json("drafts/new_draft.json"))


@pytest.fixture
def store(storage, limits) -> DraftStore:
    return DraftStore(storage.drafts, DraftCheck(limits))


def invalid(read_json, name: str) -> SceneDraft:
    return DraftRecord.from_json(read_json(f"drafts/invalid/{name}.json")).document


# %% limits


def test_a_draft_within_the_limits_passes(limits, record):
    DraftCheck(limits).check(record.document)


@pytest.mark.parametrize(
    "name, error",
    [
        ("control_character_in_name", InvalidDraftText),
        ("blank_instance_name", InvalidDraftText),
        ("identity_with_space", InvalidDraftIdentifier),
        ("duplicate_instances", DuplicateInstance),
        ("distant_position", ValueOutOfRange),
        ("position_not_a_number", ValueOutOfRange),
        ("distant_joint", ValueOutOfRange),
        ("distant_link_offset", ValueOutOfRange),
        ("zero_scale", NonPositiveScale),
        ("huge_scale", ValueOutOfRange),
        ("large_point_size", ValueOutOfRange),
    ],
)
def test_drafts_beyond_the_limits_are_refused(limits, read_json, name, error):
    with pytest.raises(error):
        DraftCheck(limits).check(invalid(read_json, name))


def test_a_refusal_names_where_the_value_sits(limits, read_json):
    with pytest.raises(ValueOutOfRange) as refused:
        DraftCheck(limits).check(invalid(read_json, "position_not_a_number"))
    instance = invalid(read_json, "position_not_a_number").instances[0]
    assert refused.value.location == DraftCheck.location(
        DraftKey.INSTANCES, instance.identifier, InstanceKey.POSITION, Axis.X
    )
    assert math.isnan(refused.value.value)


def test_more_instances_than_the_limit_are_refused(limits, record):
    bounded = replace(limits, maximum_instances=1)
    with pytest.raises(TooManyEntries) as refused:
        DraftCheck(bounded).check(record.document)
    assert (refused.value.count, refused.value.limit) == (
        len(record.document.instances),
        bounded.maximum_instances,
    )


def test_a_draft_larger_than_the_limit_is_refused(limits, record):
    bounded = replace(limits, maximum_document_bytes=64)
    with pytest.raises(DraftTooLarge) as refused:
        DraftCheck(bounded).check(record.document)
    assert refused.value.limit == bounded.maximum_document_bytes


# %% resources


def test_completing_a_draft_replaces_its_notices_with_the_librarys(library, record):
    completed = DraftResources(library).complete(record.document)
    expected = {}
    for instance in record.document.instances:
        for notice in library.notices(ResourceIdentifier.parse(instance.asset)):
            expected[notice.asset] = notice
    assert completed.notices == list(expected.values())
    assert completed.instances == record.document.instances


@pytest.mark.parametrize(
    "name, error",
    [
        ("unknown_asset", FileNotInDirectory),
        ("dependency_asset", NotAModel),
        ("climbing_asset", InvalidResourceIdentifier),
        ("unknown_root", UnknownResourceRoot),
        ("appearance_on_model", NotAPointCloud),
    ],
)
def test_drafts_placing_what_the_library_cannot_place_are_refused(
    library, read_json, name, error
):
    with pytest.raises(error):
        DraftResources(library).complete(invalid(read_json, name))


# %% storage


def test_a_new_draft_is_saved_under_a_new_identity(store, record):
    saved = store.save(record)
    assert saved.identifier is not None
    assert store.load(saved.identifier) == saved


def test_saving_with_an_identity_replaces_that_draft(store, record):
    saved = store.save(record)
    renamed = replace(saved.document, name="Renamed")
    store.save(DraftRecord(identifier=saved.identifier, document=renamed))
    assert store.load(saved.identifier).document == renamed
    assert [summary.identifier for summary in store.summaries()] == [saved.identifier]


def test_the_summaries_name_each_saved_draft(store, record):
    first = store.save(record)
    second = store.save(
        DraftRecord(document=replace(record.document, name="Second corner"))
    )
    summaries = {summary.identifier: summary.name for summary in store.summaries()}
    assert summaries == {
        first.identifier: first.document.name,
        second.identifier: second.document.name,
    }


def test_there_are_no_summaries_before_the_first_draft(store):
    assert store.summaries() == []


def test_a_damaged_draft_does_not_hide_the_others(store, record):
    saved = store.save(record)
    (store.directory / f"damaged{DraftFile.SUFFIX}").write_text("{", encoding="utf-8")
    assert [summary.identifier for summary in store.summaries()] == [saved.identifier]
    with pytest.raises(UnreadableDraft) as refused:
        store.load("damaged")
    assert refused.value.identifier == "damaged"


def test_an_unknown_draft_is_refused(store):
    with pytest.raises(UnknownDraft):
        store.load("missing")


@pytest.mark.parametrize("identifier", ["../escape", "with space", ""])
def test_a_malformed_identity_is_refused(store, identifier):
    with pytest.raises(InvalidDraftIdentifier):
        store.load(identifier)


def test_a_linked_draft_file_is_refused(store, record, workspace):
    store.directory.mkdir(parents=True)
    (store.directory / f"linked{DraftFile.SUFFIX}").symlink_to(workspace / "x.json")
    with pytest.raises(UnsafeStoragePath):
        store.save(DraftRecord(identifier="linked", document=record.document))


def test_a_linked_draft_directory_is_refused(store, record, workspace):
    target = workspace / "elsewhere"
    target.mkdir()
    store.directory.parent.mkdir(parents=True)
    store.directory.symlink_to(target)
    with pytest.raises(UnsafeStoragePath):
        store.save(record)


def test_a_saved_draft_is_written_whole_as_json(store, record):
    saved = store.save(record)
    path = store.directory / f"{saved.identifier}{DraftFile.SUFFIX}"
    assert json.loads(path.read_text(encoding="utf-8")) == record.document.to_json()
    assert [entry.name for entry in store.directory.iterdir()] == [path.name]
